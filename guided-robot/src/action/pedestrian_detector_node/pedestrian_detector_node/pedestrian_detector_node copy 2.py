#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge
import cv2
import os
import time
from deepface import DeepFace
from scipy.spatial.distance import cosine, euclidean
import threading
import yaml

class PedestrianVIPDetector(Node):
    def __init__(self):
        """行人检测与VIP识别节点初始化"""
        super().__init__('pedestrian_detector_node')
        self.callback_group = ReentrantCallbackGroup()  # 使用 Reentrant 回调组支持并行处理
        self.image_lock = threading.Lock()  # 初始化线程锁
        self.bridge = CvBridge()  # 初始化 CV Bridge，用于图像格式转换

        # 从 YAML 配置文件加载参数
        self.declare_parameter('config_file', '')
        config_file = self.get_parameter('config_file').value
        if not config_file:
            self.get_logger().error("未指定配置文件路径！")
            raise ValueError("必须提供参数配置文件路径")
        self.load_parameters_from_yaml(config_file)

        # 初始化人脸数据库（仅当启用VIP识别时加载）
        self.face_database = []
        if self.enable_vip:
            self.load_face_database()

        # 初始化 OpenCV DNN 人脸检测模型
        self.net = cv2.dnn.readNetFromCaffe(
            "/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/deploy.prototxt",
            "/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/res10_300x300_ssd_iter_140000.caffemodel")

        # 订阅彩色图像与深度图像话题
        self.color_sub = self.create_subscription(
            Image,
            '/camera/color/image_raw',
            self.color_callback,
            10,
            callback_group=self.callback_group)

        # 发布检测结果
        self.detection_pub = self.create_publisher(
            Image, 'face_detection/output', 10)  # 发布人脸检测结果
        self.greeting_pub = self.create_publisher(String, 'greeting', 10)  # 发布欢迎消息

        # 定时器，用于执行检测循环
        self.timer = self.create_timer(
            1.0 / self.detection_frequency,
            self.detection_loop,
            callback_group=self.callback_group)

        self.get_logger().info('行人检测与VIP识别节点初始化完成')

    def load_parameters_from_yaml(self, config_file):
        """从 YAML 文件加载参数"""
        try:
            with open(config_file, 'r') as f:
                params = yaml.safe_load(f)

            node_params = params.get('pedestrian_detector_node', {}).get('ros__parameters', {})
            self.attraction_distance = node_params.get('attraction_distance', 2.0)  # 招揽距离
            self.enable_vip = node_params.get('enable_vip_recognition', True)  # 是否启用VIP识别
            self.face_db_path = node_params.get(
                'face_database_path', '/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/face')  # 人脸数据库路径
            self.detection_frequency = node_params.get('detection_frequency', 1.0)  # 检测频率
            self.vip_threshold = node_params.get('vip_recognition_threshold', 0.5)  # VIP识别阈值
            self.welcome_msg = node_params.get('welcome_message', '欢迎光临')  # 欢迎语
            self.get_logger().info(f"参数加载成功：VIP识别阈值: {self.vip_threshold}")

        except Exception as e:
            self.get_logger().error(f"加载配置文件失败: {str(e)}")
            raise

    def load_face_database(self):
        """加载人脸数据库"""
        if not os.path.exists(self.face_db_path):
            self.get_logger().error(f"人脸数据库路径不存在: {self.face_db_path}")
            return

        self.get_logger().info("开始加载人脸数据库...")
        try:
            for file in os.listdir(self.face_db_path):
                if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    image_path = os.path.join(self.face_db_path, file)
                    try:
                        # 使用 DeepFace 提取特征向量
                        embedding = DeepFace.represent(
                            img_path=image_path, model_name="VGG-Face")[0]["embedding"]
                        label = os.path.splitext(file)[0]
                        self.face_database.append({"label": label, "embedding": embedding})
                    except Exception as e:
                        self.get_logger().error(f"处理文件 {file} 时出错: {e}")

            self.get_logger().info(f"人脸数据库加载完成，共 {len(self.face_database)} 张人脸")
        except Exception as e:
            self.get_logger().error(f"加载人脸数据库出错: {str(e)}")

    def find_most_similar_face(self, target_image):
        """找到与目标图像最相似的人脸"""
        try:
            # 提取目标图像的特征向量
            target_embedding = DeepFace.represent(
                img_path=target_image, model_name="VGG-Face")[0]["embedding"]

            # 比较数据库中每个人脸的相似度
            min_distance = float('inf')
            matched_label = None
            for face in self.face_database:
                distance = cosine(target_embedding, face["embedding"])  # 使用余弦距离
                if distance < min_distance:
                    min_distance = distance
                    matched_label = face["label"]

            return matched_label, min_distance
        except Exception as e:
            self.get_logger().error(f"匹配人脸时出错: {e}")
            return None, None

    def color_callback(self, msg):
        """处理彩色图像回调"""
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            self.latest_color = cv_image
        except Exception as e:
            self.get_logger().error(f"处理彩色图像出错: {e}")

    def detection_loop(self):
        """检测主循环"""
        if self.latest_color is None:
            return

        try:
            # 使用 OpenCV 检测人脸
            h, w = self.latest_color.shape[:2]
            blob = cv2.dnn.blobFromImage(self.latest_color, 1.0, (300, 300), (104.0, 177.0, 123.0))
            self.net.setInput(blob)
            detections = self.net.forward()

            for i in range(detections.shape[2]):
                confidence = detections[0, 0, i, 2]
                if confidence > self.detection_confidence:
                    # 检测到人脸
                    box = detections[0, 0, i, 3:7] * [w, h, w, h]
                    x1, y1, x2, y2 = box.astype("int")
                    face_img = self.latest_color[y1:y2, x1:x2]

                    if self.enable_vip:
                        # 尝试匹配VIP
                        matched_label, distance = self.find_most_similar_face(face_img)
                        if matched_label and distance < self.vip_threshold:
                            self.get_logger().info(f"检测到VIP: {matched_label} (距离: {distance:.4f})")
                            self.greeting_pub.publish(String(data=f"{self.welcome_msg}, {matched_label}!"))

        except Exception as e:
            self.get_logger().error(f"检测过程中出错: {e}")


def main(args=None):
    rclpy.init(args=args)
    node = PedestrianVIPDetector()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
