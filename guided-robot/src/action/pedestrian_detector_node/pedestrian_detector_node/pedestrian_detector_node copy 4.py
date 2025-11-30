#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup, MutuallyExclusiveCallbackGroup
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import numpy as np
from deepface import DeepFace
import os
import time
import json
from std_msgs.msg import String
from geometry_msgs.msg import Point
from scipy.spatial.distance import cosine
from concurrent.futures import ThreadPoolExecutor
import threading
from queue import Queue
import concurrent.futures


class PedestrianFaceMatcher(Node):
    def __init__(self):
        super().__init__('pedestrian_face_matcher')
        
        # 使用可重入回调组，允许回调并行执行
        self.callback_group = ReentrantCallbackGroup()
        
        # 参数声明
        self.declare_parameters(
            namespace='',
            parameters=[
                ('face_db_path', '/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/face/face_data'),
                ('pedestrian_model.prototxt', '/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/pedestrian_deploy.prototxt'),
                ('pedestrian_model.weights', '/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/pedestrian_model.caffemodel'),
                ('face_model.prototxt', '/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/deploy.prototxt'),
                ('face_model.weights', '/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/res10_300x300_ssd_iter_140000.caffemodel'),
                ('pedestrian_confidence_threshold', 0.5),
                ('face_confidence_threshold', 0.7),
                ('similarity_threshold', 0.5),
                ('deepface_model', 'VGG-Face'),
                ('distance_metric', 'cosine'),
                ('enable_face_matching', True),
                ('publish_debug_image', True),
                ('max_workers', 4)  # 线程池大小
            ]
        )
        
        # 加载参数
        self.load_parameters()
        
        # 初始化模型
        self.load_models()
        
        # 初始化人脸数据库
        self.face_db = self.load_face_database()
        
        # 初始化CV桥
        self.bridge = CvBridge()
        
        # 线程安全队列
        self.image_queue = Queue(maxsize=5)
        self.face_match_queue = Queue(maxsize=5)
        
        # 线程锁
        self.depth_lock = threading.Lock()
        self.latest_depth = None
        
        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        # 订阅图像话题
        self.color_sub = self.create_subscription(
            Image,
            '/camera/color/image_raw',
            self.image_callback,
            10,
            callback_group=self.callback_group)
            
        self.depth_sub = self.create_subscription(
            Image,
            '/camera/depth/image_raw',
            self.depth_callback,
            10,
            callback_group=self.callback_group)
        
        # 创建发布者
        if self.publish_debug_image:
            self.debug_pub = self.create_publisher(Image, 'pedestrian_face/debug_image', 10)
            
        self.match_pub = self.create_publisher(String, 'pedestrian_face/match_result', 10)
        self.face_position_pub = self.create_publisher(Point, 'pedestrian_face/face_position', 10)
        
        # 启动处理线程
        self.processing_thread = threading.Thread(target=self.process_images)
        self.processing_thread.daemon = True
        self.processing_thread.start()
        
        self.matching_thread = threading.Thread(target=self.process_face_matches)
        self.matching_thread.daemon = True
        self.matching_thread.start()
        
        self.get_logger().info('Pedestrian and Face Matcher node initialized with multi-threading')

    def load_parameters(self):
        """加载所有参数"""
        self.face_db_path = self.get_parameter('face_db_path').value
        self.pedestrian_prototxt = self.get_parameter('pedestrian_model.prototxt').value
        self.pedestrian_weights = self.get_parameter('pedestrian_model.weights').value
        self.face_prototxt = self.get_parameter('face_model.prototxt').value
        self.face_weights = self.get_parameter('face_model.weights').value
        self.pedestrian_thresh = self.get_parameter('pedestrian_confidence_threshold').value
        self.face_thresh = self.get_parameter('face_confidence_threshold').value
        self.similarity_thresh = self.get_parameter('similarity_threshold').value
        self.deepface_model = self.get_parameter('deepface_model').value
        self.distance_metric = self.get_parameter('distance_metric').value
        self.enable_face_matching = self.get_parameter('enable_face_matching').value
        self.publish_debug_image = self.get_parameter('publish_debug_image').value
        self.max_workers = self.get_parameter('max_workers').value
        
        # 设置DeepFace权重路径
        os.environ['DEEPFACE_HOME'] = "/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/weight/"

    def load_models(self):
        """加载行人检测和人脸检测模型"""
        try:
            # 行人检测模型
            self.pedestrian_net = cv2.dnn.readNetFromCaffe(
                self.pedestrian_prototxt, 
                self.pedestrian_weights)
            
            # 人脸检测模型
            self.face_net = cv2.dnn.readNetFromCaffe(
                self.face_prototxt, 
                self.face_weights)
                
            self.get_logger().info("Models loaded successfully")
        except Exception as e:
            self.get_logger().error(f"Failed to load models: {str(e)}")
            raise

    def load_face_database(self):
        """加载人脸数据库"""
        face_db = []
        if not os.path.exists(self.face_db_path):
            self.get_logger().warning(f"Face database path not found: {self.face_db_path}")
            return face_db
            
        for file in os.listdir(self.face_db_path):
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                path = os.path.join(self.face_db_path, file)
                try:
                    # 生成特征向量
                    embedding = DeepFace.represent(
                        img_path=path, 
                        model_name=self.deepface_model)[0]["embedding"]
                    label = os.path.splitext(file)[0]
                    face_db.append({"label": label, "embedding": embedding})
                    self.get_logger().info(f"Loaded face: {label}")
                except Exception as e:
                    self.get_logger().error(f"Error processing {path}: {e}")
        
        self.get_logger().info(f"Loaded {len(face_db)} faces from database")
        return face_db

    def depth_callback(self, msg):
        """处理深度图像"""
        try:
            # 转换深度图像消息为OpenCV格式
            depth_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            with self.depth_lock:
                self.latest_depth = depth_image
        except Exception as e:
            self.get_logger().error(f'Error processing depth image: {str(e)}')

    def image_callback(self, msg):
        """图像回调函数 - 只负责将图像放入队列"""
        try:
            if self.image_queue.full():
                self.get_logger().warn("Image queue full, dropping frame")
                return
                
            # 转换ROS图像消息为OpenCV格式
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            
            # 获取当前深度图像
            with self.depth_lock:
                current_depth = self.latest_depth.copy() if self.latest_depth is not None else None
            
            # 将图像和深度图放入队列
            self.image_queue.put((cv_image, current_depth))
            
        except Exception as e:
            self.get_logger().error(f'Error in image callback: {str(e)}')

    def process_images(self):
        """图像处理线程"""
        while rclpy.ok():
            try:
                cv_image, depth_image = self.image_queue.get()
                
                # 使用线程池异步处理
                future = self.executor.submit(self.process_single_image, cv_image, depth_image)
                future.add_done_callback(self.handle_processing_result)
                
            except Exception as e:
                self.get_logger().error(f'Error in processing thread: {str(e)}')

    def process_single_image(self, cv_image, depth_image):
        """处理单张图像"""
        debug_image = cv_image.copy()
        results = {
            "pedestrians": [],
            "debug_image": debug_image if self.publish_debug_image else None
        }
        
        # 1. 行人检测
        pedestrians = self.detect_pedestrians(cv_image)
        results["pedestrian_count"] = len(pedestrians)
        
        for pedestrian in pedestrians:
            startX, startY, endX, endY = pedestrian["box"]
            
            # 绘制行人框
            cv2.rectangle(debug_image, (startX, startY), (endX, endY), (0, 255, 255), 2)
            cv2.putText(debug_image, f"Person: {pedestrian['confidence']:.2f}", 
                       (startX, startY - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            
            # 2. 人脸检测
            faces = self.detect_faces(cv_image, pedestrian["box"])
            
            for face in faces:
                faceX, faceY, faceEndX, faceEndY = face["box"]
                
                # 绘制人脸框
                cv2.rectangle(debug_image, (faceX, faceY), (faceEndX, faceEndY), (0, 255, 0), 2)
                
                # 计算人脸中心坐标
                centerX = (faceX + faceEndX) // 2
                centerY = (faceY + faceEndY) // 2
                
                # 深度信息
                distance = 0.0
                if depth_image is not None and 0 <= centerY < depth_image.shape[0] and 0 <= centerX < depth_image.shape[1]:
                    distance_mm = depth_image[centerY, centerX]
                    if distance_mm > 0:
                        distance = float(distance_mm) / 1000.0  # 转换为米
                        cv2.putText(debug_image, f"{distance:.2f}m", 
                                   (faceX, faceEndY + 20), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                
                # 准备人脸匹配任务
                if self.enable_face_matching and self.face_db:
                    match_task = {
                        "face_roi": face["roi"],
                        "position": {
                            "x": centerX,
                            "y": centerY,
                            "z": distance
                        },
                        "box": (faceX, faceY, faceEndX, faceEndY)
                    }
                    results["pedestrians"].append(match_task)
        
        return results

    def handle_processing_result(self, future):
        """处理图像处理结果"""
        try:
            results = future.result()
            
            # 发布调试图像
            if self.publish_debug_image and results["debug_image"] is not None:
                debug_msg = self.bridge.cv2_to_imgmsg(results["debug_image"], encoding='bgr8')
                self.debug_pub.publish(debug_msg)
            
            # 提交人脸匹配任务
            for pedestrian in results["pedestrians"]:
                if self.face_match_queue.full():
                    self.get_logger().warn("Face match queue full, dropping task")
                    continue
                self.face_match_queue.put(pedestrian)
                
        except Exception as e:
            self.get_logger().error(f'Error handling processing result: {str(e)}')

    def detect_pedestrians(self, cv_image):
        """检测图像中的行人"""
        (h, w) = cv_image.shape[:2]
        blob = cv2.dnn.blobFromImage(
            cv2.resize(cv_image, (300, 300)), 
            1.0, 
            (300, 300),
            (104.0, 177.0, 123.0))
        
        self.pedestrian_net.setInput(blob)
        detections = self.pedestrian_net.forward()
        
        pedestrians = []
        for i in range(0, detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            
            if confidence > self.pedestrian_thresh:
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                (startX, startY, endX, endY) = box.astype("int")
                
                # 确保边界框在图像范围内
                startX, startY = max(0, startX), max(0, startY)
                endX, endY = min(w - 1, endX), min(h - 1, endY)
                
                pedestrians.append({
                    "box": (startX, startY, endX, endY),
                    "confidence": confidence
                })
                
        return pedestrians

    def detect_faces(self, cv_image, pedestrian_box):
        """在行人区域内检测人脸"""
        (startX, startY, endX, endY) = pedestrian_box
        pedestrian_roi = cv_image[startY:endY, startX:endX]
        
        if pedestrian_roi.size == 0:
            return []
            
        (h, w) = pedestrian_roi.shape[:2]
        blob = cv2.dnn.blobFromImage(
            cv2.resize(pedestrian_roi, (300, 300)), 
            1.0, 
            (300, 300),
            (104.0, 177.0, 123.0))
        
        self.face_net.setInput(blob)
        detections = self.face_net.forward()
        
        faces = []
        for i in range(0, detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            
            if confidence > self.face_thresh:
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                (faceX, faceY, faceEndX, faceEndY) = box.astype("int")
                
                # 转换为原始图像坐标
                faceX += startX
                faceY += startY
                faceEndX += startX
                faceEndY += startY
                
                # 确保边界框在图像范围内
                faceX, faceY = max(0, faceX), max(0, faceY)
                faceEndX, faceEndY = min(cv_image.shape[1] - 1, faceEndX), min(cv_image.shape[0] - 1, faceEndY)
                
                faces.append({
                    "box": (faceX, faceY, faceEndX, faceEndY),
                    "confidence": confidence,
                    "roi": cv_image[faceY:faceEndY, faceX:faceEndX]
                })
                
        return faces

    def process_face_matches(self):
        """人脸匹配线程"""
        while rclpy.ok():
            try:
                match_task = self.face_match_queue.get()
                
                # 使用线程池异步处理
                future = self.executor.submit(self.match_single_face, match_task)
                future.add_done_callback(self.handle_match_result)
                
            except Exception as e:
                self.get_logger().error(f'Error in matching thread: {str(e)}')

    def match_single_face(self, match_task):
        """匹配单个人脸"""
        try:
            label, distance = self.match_face(match_task["face_roi"])
            return {
                "label": label,
                "distance": distance,
                "position": match_task["position"],
                "box": match_task["box"]
            }
        except Exception as e:
            self.get_logger().error(f"Face matching error: {str(e)}")
            return None

    def handle_match_result(self, future):
        """处理人脸匹配结果"""
        try:
            result = future.result()
            if result is None:
                return
                
            label = result["label"]
            distance = result["distance"]
            
            if label and distance < self.similarity_thresh:
                # 发布匹配结果
                result_msg = String()
                result_msg.data = json.dumps({
                    "label": label,
                    "distance": float(distance),
                    "position": result["position"]
                })
                self.match_pub.publish(result_msg)
                
                # 发布人脸位置
                position_msg = Point()
                position_msg.x = float(result["position"]["x"])
                position_msg.y = float(result["position"]["y"])
                position_msg.z = float(result["position"]["z"])
                self.face_position_pub.publish(position_msg)
                
        except Exception as e:
            self.get_logger().error(f'Error handling match result: {str(e)}')

    def match_face(self, face_roi):
        """匹配人脸"""
        try:
            # 提取目标图片的特征向量
            target_embedding = DeepFace.represent(
                img_path=face_roi, 
                model_name=self.deepface_model)[0]["embedding"]
            
            # 比较目标图片与数据库中每张人脸的相似度
            min_distance = float("inf")
            matched_label = None
            for face in self.face_db:
                if self.distance_metric == "cosine":
                    distance = cosine(target_embedding, face["embedding"])
                else:
                    distance = euclidean(target_embedding, face["embedding"])
                
                if distance < min_distance:
                    min_distance = distance
                    matched_label = face["label"]

            return matched_label, min_distance
        except Exception as e:
            self.get_logger().error(f"Face matching error: {str(e)}")
            return None, None

def main(args=None):
    rclpy.init(args=args)
    
    try:
        # 创建节点
        node = PedestrianFaceMatcher()
        
        # 使用多线程执行器
        executor = MultiThreadedExecutor(num_threads=4)
        executor.add_node(node)
        
        try:
            executor.spin()
        finally:
            executor.shutdown()
            node.destroy_node()
            
    finally:
        rclpy.shutdown()

if __name__ == '__main__':
    main()