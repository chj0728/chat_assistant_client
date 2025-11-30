#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.parameter import Parameter
from sensor_msgs.msg import Image
from std_msgs.msg import String
from std_msgs.msg import Bool
from cv_bridge import CvBridge
import cv2
import numpy as np
import face_recognition
import os
import time
import threading
import yaml
from concurrent.futures import ThreadPoolExecutor


class PedestrianVIPDetector(Node):
    def __init__(self):
        super().__init__('pedestrian_detector_node')
        self.image_lock = threading.Lock()  # 初始化线程锁
        self.callback_group = ReentrantCallbackGroup()  # 使用Reentrant回调组允许回调并行执行

        print("pedestrian_detector_node初始化")
        # 从YAML文件加载参数
        # self.declare_parameter('config_file', '')
        # config_file = self.get_parameter('config_file').value
        # if not config_file:
        #     self.get_logger().error("未指定参数配置文件路径!")
        #     raise ValueError("必须提供参数配置文件路径")

        config_file = "/home/ymrobot/ros2_ws_guidance/src/guided-robot/src/action/pedestrian_detector_node/config/pedestrian_detector_node.yaml"

        self.load_parameters_from_yaml(config_file)

        # 初始化线程池
        self.thread_pool = ThreadPoolExecutor(max_workers=4)

        # 初始化人脸数据库  如果开启vip识别的话 那么需要加载人脸数据库
        self.face_encodings = []
        self.face_labels = []
        if self.enable_vip:
            self.load_face_database()

        print("参数配置文件路径:", config_file)
        self.net = cv2.dnn.readNetFromCaffe(self.prototxt_file_adress,self.caffemodel_file_adress) # 初始化DNN人脸检测器

        # 初始化CV桥
        self.bridge = CvBridge()

        # 图像缓存
        self.latest_color = None
        self.latest_depth = None
        self.image_lock = threading.Lock()

        # 订阅图像话题
        self.color_sub = self.create_subscription(
            Image,
            '/camera/color/image_raw',
            self.color_callback,
            10,
            callback_group=self.callback_group)

        self.depth_sub = self.create_subscription(
            Image,
            '/camera/depth/image_raw',
            self.depth_callback,
            10,
            callback_group=self.callback_group)
        
        self.is_open_active_wake_up_sub = self.create_subscription(
            Bool,
            '/is_open_active_wake_up',
            self.is_open_active_wake_up_sub_callback,
            10,
            callback_group=self.callback_group)

        # 创建发布者
        self.detection_pub = self.create_publisher(
            Image, 'face_detection/output', 10) # 发布人脸检测结果
        self.greeting_pub = self.create_publisher(String, 'greeting', 10) #  发布欢迎信息

        # 创建定时器
        self.timer = self.create_timer(
            1.0/self.detection_frequency,
            self.detection_loop,
            callback_group=self.callback_group)

        # 状态变量
        self.last_detected_person = None  # 上次检测到的人脸
        self.last_detection_time = None  # 上次检测的时间

        self.get_logger().info('行人检测与VIP识别节点初始化完成')

    def load_parameters_from_yaml(self, config_file):
        """
        从YAML文件加载参数到类的属性中
        :param config_file: YAML配置文件路径
        """
        try:
            # 打开并读取 YAML 文件
            with open(config_file, 'r') as file:
                config = yaml.safe_load(file)

            # 获取 'ros__parameters' 下的参数
            parameters = config.get('pedestrian_detector_node', {}).get('ros__parameters', {})

            # 将参数加载到类的属性中
            self.attraction_distance = parameters.get('attraction_distance', 2.5)
            self.enable_active_wake_up = parameters.get('enable_active_wake_up', True)   # 是否开启主动唤醒
            self.enable_vip = parameters.get('enable_vip_recognition', False)
            self.face_db_path = parameters.get('face_database_path', "/path/to/face/database")
            self.welcome_msg = parameters.get('welcome_message', "欢迎光临")
            self.detection_frequency = parameters.get('detection_frequency', 1.0)
            self.detection_confidence = parameters.get('detection_confidence', 0.7)
            self.vip_threshold = parameters.get('vip_recognition_threshold', 0.6)
            self.prototxt_file_adress = parameters.get('prototxt_file_adress', "")
            self.caffemodel_file_adress = parameters.get('caffemodel_file_adress', "")
            self.enable_initiate_solicitation = parameters.get('enable_initiate_solicitation', False)

            # 打印加载结果供调试
            self.get_logger().info(f"加载参数成功: {parameters}")

        except FileNotFoundError:
            self.get_logger().error(f"参数配置文件未找到: {config_file}")
            raise
        except yaml.YAMLError as e:
            self.get_logger().error(f"解析 YAML 文件失败: {e}")
            raise

    def load_face_database(self):
        """加载人脸数据库"""
        if not os.path.exists(self.face_db_path):
            self.get_logger().error(f"人脸数据库路径不存在: {self.face_db_path}")
            return

        self.get_logger().info("正在加载人脸数据库...")
        start_time = time.time()

        try:
            for file in os.listdir(self.face_db_path):
                if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    path = os.path.join(self.face_db_path, file)
                    self.process_face_image(path, file)

                    # try:
                    #     # 使用线程池并行加载图像
                    #     future = self.thread_pool.submit(
                    #         self.process_face_image, path, file)
                    #     # 注意: 这里简化处理，实际应该收集所有future并等待完成
                    # except Exception as e:
                    #     self.get_logger().error(f"提交人脸处理任务出错: {str(e)}")

            elapsed = time.time() - start_time
            self.get_logger().info(
                f"人脸数据库加载完成，共 {len(self.face_labels)} 张人脸，耗时 {elapsed:.2f} 秒")
        except Exception as e:
            self.get_logger().error(f"加载人脸数据库出错: {str(e)}")

    def process_face_image(self, path, filename):
        """处理单个人脸图像"""
        try:
            image = face_recognition.load_image_file(path)
            face_locations = face_recognition.face_locations(image)
            if len(face_locations) == 0:
                self.get_logger().warning(f"未检测到人脸: {path}")
                return

            encoding = face_recognition.face_encodings(
                image, known_face_locations=face_locations)[0]

            # 使用锁保护共享数据
            with self.image_lock:
                self.face_encodings.append(encoding)
                self.face_labels.append(os.path.splitext(filename)[0])

        except Exception as e:
            self.get_logger().error(f"处理图像 {path} 时出错: {str(e)}")

    def color_callback(self, msg):
        """处理彩色图像回调"""
        if self.enable_active_wake_up:
            try:
                cv_image = self.bridge.imgmsg_to_cv2(
                    msg, desired_encoding='bgr8')
                with self.image_lock:
                    self.latest_color = cv_image
            except Exception as e:
                self.get_logger().error(f'处理彩色图像出错: {str(e)}')

    def depth_callback(self, msg):
        """处理深度图像回调"""
        if self.enable_active_wake_up:
            try:
                depth_image = self.bridge.imgmsg_to_cv2(
                    msg, desired_encoding='passthrough')
                with self.image_lock:
                    self.latest_depth = depth_image
            except Exception as e:
                self.get_logger().error(f'处理深度图像出错: {str(e)}')

    def is_open_active_wake_up_sub_callback(self, msg):
        """主动唤醒回到函数"""
        self.enable_active_wake_up = msg
        if self.enable_active_wake_up:
            self.get_logger().info("主动唤醒开启")
            self.modify_yaml_parameter("enable_active_wake_up", True)
        else:
            self.get_logger().info("主动唤醒关闭")
            self.modify_yaml_parameter("enable_active_wake_up", False)
        # self.modify_yaml_parameter("enable_pedestrian_detection", )
        self.get_logger().info("修改参数成功")
        
    def modify_yaml_parameter(self, parameter_name, new_value):
        """
        修改 YAML 配置文件中的参数值
        :param parameter_name: 要修改的参数名
        :param new_value: 新值
        """
        config_file = "/home/ymrobot/ros2_ws_guidance/src/guided-robot/src/action/pedestrian_detector_node/config/pedestrian_detector_node.yaml"
        self.get_logger().info(f"config_file: {config_file}")
        if not config_file:
            self.get_logger().error("未指定参数配置文件路径!")
            return False

        try:
            # 读取现有配置文件
            with open(config_file, 'r',encoding='utf-8') as file:
                config = yaml.safe_load(file)
            
            # 检查参数路径是否存在
            if 'pedestrian_detector_node' not in config:
                config['pedestrian_detector_node'] = {}
            if 'ros__parameters' not in config['pedestrian_detector_node']:
                config['pedestrian_detector_node']['ros__parameters'] = {}
            
            # 修改参数值
            config['pedestrian_detector_node']['ros__parameters'][parameter_name] = new_value
            
            # 写回文件
            with open(config_file, 'w') as file:
                yaml.dump(config, file, default_flow_style=False)
            
            self.get_logger().info(f"成功修改参数 {parameter_name} 为 {new_value}")
            return True
            
        except Exception as e:
            self.get_logger().error(f"修改YAML文件出错: {str(e)}")
            return False

    def detection_loop(self):
        """定时检测循环"""
        if not self.enable_active_wake_up:
            return

        # 获取最新图像
        with self.image_lock:
            if self.latest_color is None or self.latest_depth is None:
                return

            color_img = self.latest_color.copy()
            depth_img = self.latest_depth.copy()

        # 在另一个线程中执行检测
        self.thread_pool.submit(
            self.detect_and_recognize, color_img, depth_img)

    def detect_and_recognize(self, color_img, depth_img):
        """执行检测和识别逻辑"""
        try:
            # 人脸检测
            (h, w) = color_img.shape[:2]
            blob = cv2.dnn.blobFromImage(
                cv2.resize(color_img, (300, 300)),
                1.0,
                (300, 300),
                (104.0, 177.0, 123.0))

            self.net.setInput(blob)
            detections = self.net.forward()

            person_detected = False
            detected_distance = float('inf')

            # 处理检测结果
            for i in range(0, detections.shape[2]):
                confidence = detections[0, 0, i, 2]

                if confidence > self.detection_confidence:
                    box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                    (startX, startY, endX, endY) = box.astype("int")

                    # 计算人脸中心坐标
                    centerX = (startX + endX) // 2
                    centerY = (startY + endY) // 2

                    # 检查距离
                    if 0 <= centerY < depth_img.shape[0] and 0 <= centerX < depth_img.shape[1]:
                        distance_mm = depth_img[centerY, centerX]
                        if distance_mm > 0:
                            distance_m = distance_mm / 1000.0
                            detected_distance = min(
                                detected_distance, distance_m)
                            person_detected = True

                            # 绘制检测框
                            color = (0, 255, 0)
                            cv2.rectangle(
                                color_img, (startX, startY), (endX, endY), color, 2)
                            
                            #play mp3

                            # VIP识别
                            if self.enable_vip and len(self.face_encodings) > 0:
                                face_img = color_img[startY:endY, startX:endX]
                                face_encoding = self.recognize_face(face_img)

                                if face_encoding is not None:
                                    distances = face_recognition.face_distance(
                                        self.face_encodings, face_encoding)
                                    min_index = np.argmin(distances)
                                    min_distance = distances[min_index]
                                    self.get_logger().info(f"****vip最小距离: {min_distance:.2f}")
                                    if min_distance <= self.vip_threshold:
                                        vip_name = self.face_labels[min_index]
                                        greeting = f"欢迎VIP客户 {vip_name}!"
                                        self.publish_greeting(greeting)
                                            # 保存检测到的VIP图像
                                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                                        filename = f"vip_{vip_name}_{timestamp}.jpg"
                                        filepath = os.path.join(
                                            "/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/mp3", filename)
                                        # 保存原始图像和裁剪的人脸图像
                                        cv2.imwrite(filepath, color_img)
                                        face_filepath = os.path.join(
                                            "/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/mp3", f"face_{filename}")
                                        cv2.imwrite(face_filepath, face_img)
                                        self.get_logger().info(
                                            f"已保存VIP图像到: {filepath}")
                                    else:
                                        self.publish_greeting(self.welcome_msg)
                                else:
                                    self.publish_greeting(self.welcome_msg)
                            else:
                                self.publish_greeting(self.welcome_msg)

            # 发布检测结果图像
            if person_detected:
                self.last_detected_person = True
                self.last_detection_time = self.get_clock().now()

                if detected_distance <= self.attraction_distance:
                    self.get_logger().info(
                        f"检测到人在招揽距离内: {detected_distance:.2f}m")
                else:
                    self.get_logger().info(
                        f"检测到人但距离较远: {detected_distance:.2f}m")

            # 发布检测结果图像
            try:
                result_msg = self.bridge.cv2_to_imgmsg(
                    color_img, encoding='bgr8')
                self.detection_pub.publish(result_msg)
            except Exception as e:
                self.get_logger().error(f"发布检测结果图像出错: {str(e)}")

        except Exception as e:
            self.get_logger().error(f"检测和识别过程中出错: {str(e)}")

    def recognize_face(self, face_img):
        """识别人脸并返回特征编码"""
        try:
            rgb_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_img)
            if len(face_locations) == 0:
                return None

            return face_recognition.face_encodings(rgb_img, known_face_locations=face_locations)[0]
        except Exception as e:
            self.get_logger().error(f"人脸识别出错: {str(e)}")
            return None

    def publish_greeting(self, message):
        """发布问候语"""
        msg = String()
        msg.data = message
        self.greeting_pub.publish(msg)
        self.get_logger().info(f"发布问候语: {message}")


def main(args=None):
    rclpy.init(args=args)

    try:
        # 使用多线程执行器
        executor = MultiThreadedExecutor()
        detector = PedestrianVIPDetector()
        executor.add_node(detector)

        try:
            executor.spin()
        finally:
            executor.shutdown()
            detector.destroy_node()
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
