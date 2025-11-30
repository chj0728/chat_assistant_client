import os
import time
import zipfile
import requests
import hashlib
import logging
import sys

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 参数配置
LOG_DIR = '/home/ymrobot/ros2_ws_guidance/ros2_logs.backup'  # 日志源目录
TEMP_DIR = '/home/ymrobot/YMZZ202500001'  # 临时工作目录
UPLOAD_URL = 'http://124.71.181.16:8080/robot/robotLog/upload'  # 上传接口
MAX_RETRIES = 3  # 上传重试次数
NETWORK_CHECK_URL = 'http://www.baidu.com'  # 网络检查地址
NETWORK_CHECK_TIMEOUT = 5  # 网络检查超时时间
AUTH_TOKEN = '1567dd85997a4c62b4c88eb4139923dd'  # 授权token
ROBOT_ID = 'YMZZ202500001'  # 机器人ID（新增常量）

def is_network_available():
    """检查网络是否可用"""
    try:
        response = requests.get(NETWORK_CHECK_URL, timeout=NETWORK_CHECK_TIMEOUT)
        return True
    except requests.exceptions.RequestException:
        logging.warning("Network is not available")
        return False

def check_log_dir():
    """检查日志目录是否存在"""
    if os.path.exists(LOG_DIR) and os.path.isdir(LOG_DIR):
        logging.info(f"Log directory exists: {LOG_DIR}")
        return True
    else:
        logging.error(f"Log directory does not exist: {LOG_DIR}")
        return False

def get_latest_log_folder():
    """获取最新时间的日志文件夹"""
    try:
        # 列出所有日志文件夹（只包含符合时间戳格式的文件夹）
        log_folders = [f for f in os.listdir(LOG_DIR) if f.isdigit() and len(f) == 14]
        
        if not log_folders:
            logging.error("No valid timestamp-named log folders found")
            return None
        
        # 按时间戳排序，获取最新的文件夹
        latest_folder = sorted(log_folders, reverse=True)[0]
        latest_folder_path = os.path.join(LOG_DIR, latest_folder)
        
        logging.info(f"Latest log folder found: {latest_folder_path}")
        return latest_folder_path
    except Exception as e:
        logging.error(f"Error finding latest log folder: {str(e)}")
        return None

def compress_logs(log_folder_path):
    """压缩指定的日志文件夹为zip文件"""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    zip_path = os.path.join(TEMP_DIR, f"logs_{timestamp}.zip")
    
    logging.info(f"Compressing logs from {log_folder_path} to {zip_path}...")
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(log_folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, log_folder_path)
                    zipf.write(file_path, arcname)
        
        logging.info(f"Compression completed: {zip_path}")
        return zip_path
    except Exception as e:
        logging.error(f"Compression failed: {str(e)}")
        return None

def generate_signature(timestamp):
    """生成签名: md5(robotId + timestamp + token)"""
    print("当前时间戳： ",timestamp)
    sign_str = f"{ROBOT_ID}{timestamp}{AUTH_TOKEN}"
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

def upload_file(file_path):
    """通过HTTP上传文件（更新签名逻辑）"""
    timestamp = str(int(time.time() * 1000))  # 当前毫秒时间戳
    sign = generate_signature(timestamp)
    
    try:
        with open(file_path, 'rb') as f:
            files = {
                'file': (os.path.basename(file_path), f, 'application/octet-stream'),
            }
            
            data = {
                'robotId': ROBOT_ID,
                'timestamp': timestamp,
                'sign': sign
            }
            
            for attempt in range(MAX_RETRIES):
                try:
                    response = requests.post(
                        UPLOAD_URL,
                        files=files,
                        data=data,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        logging.info("Upload completed successfully!")
                        logging.info(f"Server response: {response.text}")
                        return True
                    else:
                        logging.error(f"Upload failed with status code: {response.status_code}, response: {response.text}")
                        if attempt == MAX_RETRIES - 1:
                            return False
                        time.sleep(5)
                        
                except requests.exceptions.RequestException as e:
                    logging.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt == MAX_RETRIES - 1:
                        return False
                    time.sleep(5)
            
    except Exception as e:
        logging.error(f"Upload failed: {str(e)}")
        return False

def trigger_upload_on_startup():
    """上电启动时自动触发上传"""
    logging.info("System powered on, checking network availability...")
    
    max_retries = 5
    retry_interval = 30
    
    for attempt in range(max_retries):
        if is_network_available():
            logging.info("Network is available, checking log directory...")
            if check_log_dir():
                logging.info("Log directory exists, starting upload process...")
                process_and_upload()
                return
            else:
                logging.error("Log directory check failed, aborting upload")
                return
        else:
            logging.warning(f"Network is not available, retrying in {retry_interval} seconds...")
            time.sleep(retry_interval)
    
    logging.error("Failed to establish network connection after multiple retries")

def process_and_upload():
    """处理流程：获取最新日志文件夹->压缩->上传->清理"""
    try:
        # 获取最新日志文件夹
        latest_log_folder = get_latest_log_folder()
        if not latest_log_folder:
            logging.error("Failed to find latest log folder")
            return
        
        # 压缩日志文件夹
        zip_path = compress_logs(latest_log_folder)
        if not zip_path:
            logging.error("Failed to create zip file")
            return
        
        # 上传压缩文件
        if upload_file(zip_path):
            try:
                os.remove(zip_path)
                logging.info(f"Successfully deleted temp file: {zip_path}")
            except Exception as e:
                logging.error(f"Failed to delete temp file {zip_path}: {str(e)}")
        else:
            logging.warning("Upload failed, keeping zip file for retry")
    except Exception as e:
        logging.error(f"Error in process_and_upload: {str(e)}")

if __name__ == '__main__':
    # 创建临时目录
    os.makedirs(TEMP_DIR, exist_ok=True)
    logging.info(f"Using temp directory: {TEMP_DIR}")
    
    # 触发上传
    trigger_upload_on_startup()
    # 任务完成后退出脚本
    sys.exit(0)