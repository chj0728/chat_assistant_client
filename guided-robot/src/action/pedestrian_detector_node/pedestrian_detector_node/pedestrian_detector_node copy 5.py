import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from deepface import DeepFace
import cv2
import numpy as np
import os
from threading import Thread
from scipy.spatial.distance import cosine

os.environ['DEEPFACE_HOME'] = "/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/weight/"  # 替换为实际路径，例如 "~/.deepface/weights/"
class PedestrianFaceMatcher(Node):
    def __init__(self):
        super().__init__('pedestrian_detector_node')
        
        # 初始化参数
        self.bridge = CvBridge()
        self.latest_image = None
        self.face_db = []

        # 加载人脸数据库
        self.face_db = self.load_face_database(
            "/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/face/face_data"
        )
        self.get_logger().info(f"人脸数据库加载完成，共计 {len(self.face_db)} 张人脸")

        # 初始化DNN人脸检测模型
        self.net = cv2.dnn.readNetFromCaffe(
            "/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/deploy.prototxt",
            "/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/res10_300x300_ssd_iter_140000.caffemodel"
        )

        # 订阅图像话题
        self.image_sub = self.create_subscription(
            Image,
            '/camera/color/image_raw',
            self.image_callback,
            10
        )

        # 设置1Hz的定时器进行检测
        self.timer = self.create_timer(1.0, self.detect_pedestrian)
        self.get_logger().info("行人检测和人脸匹配节点已初始化")

    def load_face_database(self, folder):
        """加载人脸数据库，将每张图片转换为特征向量"""
        self.get_logger().info("开始加载人脸数据库...")
        face_db = []
        for file in os.listdir(folder):
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                path = os.path.join(folder, file)
                try:
                    embedding = DeepFace.represent(
                        img_path=path, model_name="VGG-Face"
                    )[0]["embedding"]
                    label = os.path.splitext(file)[0]
                    face_db.append({"label": label, "embedding": embedding})
                except Exception as e:
                    self.get_logger().error(f"加载人脸失败：{path}, 错误信息：{e}")
        self.get_logger().info(f"人脸数据库加载完成，共计 {len(face_db)} 张人脸")
        return face_db

    def image_callback(self, msg):
        """接收图像并存储最新数据"""
        try:
            self.latest_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f"图像转换失败：{e}")

    def detect_pedestrian(self):
        """检测行人并进行人脸匹配"""
        if self.latest_image is None:
            self.get_logger().warning("未接收到图像数据")
            return

        image = self.latest_image.copy()
        (h, w) = image.shape[:2]

        # 构建Blob用于人脸检测
        blob = cv2.dnn.blobFromImage(
            cv2.resize(image, (300, 300)),
            1.0,
            (300, 300),
            (104.0, 177.0, 123.0)
        )
        self.net.setInput(blob)
        detections = self.net.forward()

        # 遍历检测结果
        for i in range(0, detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence > 0.7:
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                (startX, startY, endX, endY) = box.astype("int")

                # 提取人脸区域并进行相似度匹配
                face_roi = image[startY:endY, startX:endX]
                if face_roi.size > 0:
                    Thread(target=self.match_face, args=(face_roi,)).start()

                # 绘制检测框
                cv2.rectangle(image, (startX, startY), (endX, endY), (0, 255, 0), 2)

        # 显示检测结果
        cv2.imshow("Pedestrian Detection", image)
        cv2.waitKey(1)
        # output_path = "/home/ymrobot/ros2_ws_guidance/detection_result.jpg"
        # cv2.imwrite(output_path, image)
        # self.get_logger().info(f"Detection result saved to {output_path}")

    def match_face(self, face_image):
        """进行人脸相似度匹配"""
        try:
            embedding = DeepFace.represent(
                img_path=face_image, model_name="VGG-Face"
            )[0]["embedding"]
            min_distance = float("inf")
            matched_label = None

            for face in self.face_db:
                distance = cosine(embedding, face["embedding"])
                if distance < min_distance:
                    min_distance = distance
                    matched_label = face["label"]

            if matched_label is not None:
                self.get_logger().info(f"匹配到最相似的人脸：{matched_label}, 距离：{min_distance:.4f}")
            else:
                self.get_logger().info("未找到匹配的人脸")

        except Exception as e:
            self.get_logger().error(f"人脸匹配失败：{e}")


def main(args=None):
    rclpy.init(args=args)
    node = PedestrianFaceMatcher()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
