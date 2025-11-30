#include "log_update_node.hpp"

namespace ymrobot
{
    LogUploader::LogUploader() : Node("log_update_node")
    {
        Init();
    }

    void LogUploader::Init()
    { 
        InitParams();
        CreateSubActions();
    }

    void LogUploader::InitParams()
    { 
        this->declare_parameter("log_dir", "");
        this->declare_parameter("temp_dir", "");
        this->declare_parameter("upload_url", "");
        this->declare_parameter("network_check_url", "");
        this->declare_parameter("auth_token", "");
        this->declare_parameter("robot_id", "");
        this->declare_parameter("max_retries", 5);
        this->declare_parameter("network_check_timeout", 8);
        this->declare_parameter("retry_interval", 5);

        log_dir_ = this->get_parameter("log_dir").as_string();
        temp_dir_ = this->get_parameter("temp_dir").as_string();
        upload_url_ = this->get_parameter("upload_url").as_string();
        network_check_url_ = this->get_parameter("network_check_url").as_string();
        auth_token_ = this->get_parameter("auth_token").as_string();
        robot_id_ = this->get_parameter("robot_id").as_string();
        max_retries_ = this->get_parameter("max_retries").as_int();
        network_check_timeout_ = this->get_parameter("network_check_timeout").as_int();
        retry_interval_ = this->get_parameter("retry_interval").as_int();
    }

    void LogUploader::CreateSubActions()
    {
        upload_image_task_sub_ = this->create_subscription<std_msgs::msg::String>(image_update_topic_name_, 1, std::bind(&LogUploader::upload_image_task_callback, this, std::placeholders::_1));
    }

    void LogUploader::UploadFileTask(const std::string &file_path)
    {
        for (int attempt = 0; attempt < max_retries_; ++attempt)
        {
            if (is_network_available())
            {
                RCLCPP_INFO(this->get_logger(), "网络可用，检查日志目录...");
                if (check_log_dir())
                {
                    RCLCPP_INFO(this->get_logger(), "日志目录存在，开始上传流程...");
                    upload_file(file_path);
                    return;
                }
                else
                {
                    RCLCPP_ERROR(this->get_logger(), "日志目录检查失败，终止上传");
                    return;
                }
            }
            else
            {
                RCLCPP_WARN(this->get_logger(), "网络不可用，%d秒后重试...", retry_interval_);
                std::this_thread::sleep_for(std::chrono::seconds(retry_interval_));
            }
        }

        RCLCPP_ERROR(this->get_logger(), "多次重试后仍无法建立网络连接");
    }

    void LogUploader::trigger_upload_on_startup()
    {
        RCLCPP_INFO(this->get_logger(), "系统上电启动，检查网络可用性...");

        const int max_retries = 5;  // 最大重试次数
        const int retry_interval = 30; // 重试间隔

        // 循环检查网络可用性
        for (int attempt = 0; attempt < max_retries; ++attempt)
        {
            if (is_network_available())
            {
                RCLCPP_INFO(this->get_logger(), "网络可用，检查日志目录...");
                if (check_log_dir())
                {
                    RCLCPP_INFO(this->get_logger(), "日志目录存在，开始上传流程...");
                    process_and_upload();
                    return;
                }
                else
                {
                    RCLCPP_ERROR(this->get_logger(), "日志目录检查失败，终止上传");
                    return;
                }
            }
            else
            {
                RCLCPP_WARN(this->get_logger(), "网络不可用，%d秒后重试...", retry_interval);
                std::this_thread::sleep_for(std::chrono::seconds(retry_interval));
            }
        }

        RCLCPP_ERROR(this->get_logger(), "多次重试后仍无法建立网络连接");
    }

    void LogUploader::process_and_upload()
    {
        try
        {
            // 1. 获取最新日志文件夹
            std::string latest_log_folder = get_latest_log_folder();
            if (latest_log_folder.empty())
            {
                RCLCPP_ERROR(this->get_logger(), "获取最新日志文件夹失败");
                return;
            }

            // 2. 压缩日志文件夹
            std::string zip_path = compress_logs(latest_log_folder);
            if (zip_path.empty())
            {
                RCLCPP_ERROR(this->get_logger(), "创建zip文件失败");
                return;
            }

            // 3. 上传压缩文件
            if (upload_file(zip_path))
            {
                // 上传成功，删除临时文件
                try
                {
                    fs::remove(zip_path);
                    RCLCPP_INFO(this->get_logger(), "成功删除临时文件: %s", zip_path.c_str());
                }
                catch (const std::exception &e)
                {
                    RCLCPP_ERROR(this->get_logger(), "删除临时文件 %s 失败: %s",
                                 zip_path.c_str(), e.what());
                }
            }
            else
            {
                RCLCPP_WARN(this->get_logger(), "上传失败，保留zip文件以便重试");
            }
        }
        catch (const std::exception &e)
        {
            RCLCPP_ERROR(this->get_logger(), "处理上传过程中出错: %s", e.what());
        }
    }

    bool LogUploader::is_network_available()
    {
        CURL *curl = curl_easy_init();
        if (!curl)
        {
            RCLCPP_ERROR(this->get_logger(), "CURL初始化失败");
            return false;
        }

        // 设置CURL选项
        curl_easy_setopt(curl, CURLOPT_URL, network_check_url_.c_str());
        curl_easy_setopt(curl, CURLOPT_NOBODY, 1L); // 使用HEAD请求
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, network_check_timeout_);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L); // 禁用SSL验证

        // 执行请求
        CURLcode res = curl_easy_perform(curl);
        curl_easy_cleanup(curl);

        if (res == CURLE_OK)
        {
            return true;
        }
        else
        {
            RCLCPP_WARN(this->get_logger(), "网络检查失败: %s", curl_easy_strerror(res));
            return false;
        }
    }

    bool LogUploader::check_log_dir()
    {
        if (fs::exists(log_dir_) && fs::is_directory(log_dir_))
        {
            RCLCPP_INFO(this->get_logger(), "日志目录存在: %s", log_dir_.c_str());
            return true;
        }
        else
        {
            RCLCPP_ERROR(this->get_logger(), "日志目录不存在: %s", log_dir_.c_str());
            return false;
        }
    }

    std::string LogUploader::get_latest_log_folder()
    {
        try
        {
            std::vector<std::string> log_folders;

            // 遍历日志目录，找出所有符合时间戳格式的文件夹
            for (const auto &entry : fs::directory_iterator(log_dir_))
            {
                if (entry.is_directory())
                {
                    std::string folder_name = entry.path().filename().string();
                    // 检查是否是14位数字的时间戳格式
                    if (folder_name.length() == 14 &&
                        std::all_of(folder_name.begin(), folder_name.end(), ::isdigit))
                    {
                        log_folders.push_back(entry.path().string());
                    }
                }
            }

            if (log_folders.empty())
            {
                RCLCPP_ERROR(this->get_logger(), "未找到有效的时间戳命名的日志文件夹");
                return "";
            }

            // 按文件夹名称(时间戳)排序，获取最新的
            std::sort(log_folders.begin(), log_folders.end(), std::greater<std::string>());
            RCLCPP_INFO(this->get_logger(), "找到最新日志文件夹: %s", log_folders[0].c_str());
            return log_folders[0];
        }
        catch (const std::exception &e)
        {
            RCLCPP_ERROR(this->get_logger(), "查找最新日志文件夹时出错: %s", e.what());
            return "";
        }
    }

    std::string LogUploader::compress_logs(const std::string &log_folder_path)
    {
        std::string timestamp = get_current_timestamp();
        std::string zip_path = temp_dir_ + "/logs_" + timestamp + ".zip";

        RCLCPP_INFO(this->get_logger(), "正在压缩日志从 %s 到 %s...",
                    log_folder_path.c_str(), zip_path.c_str());

        // 创建zip文件
        int err = 0;
        zip_t *zip = zip_open(zip_path.c_str(), ZIP_CREATE | ZIP_TRUNCATE, &err);
        if (!zip)
        {
            RCLCPP_ERROR(this->get_logger(), "无法创建zip文件: %s, 错误码: %d",
                         zip_path.c_str(), err);
            return "";
        }

        try
        {
            // 遍历日志文件夹中的所有文件
            for (const auto &entry : fs::recursive_directory_iterator(log_folder_path))
            {
                if (entry.is_regular_file())
                {
                    std::string file_path = entry.path().string();
                    std::string arcname = fs::relative(entry.path(), log_folder_path).string();

                    // 将文件添加到zip中
                    zip_source_t *source = zip_source_file(zip, file_path.c_str(), 0, 0);
                    if (source == nullptr || zip_file_add(zip, arcname.c_str(), source, ZIP_FL_ENC_UTF_8) < 0)
                    {
                        zip_source_free(source);
                        RCLCPP_ERROR(this->get_logger(), "无法添加文件到zip: %s", file_path.c_str());
                        zip_close(zip);
                        return "";
                    }
                }
            }

            zip_close(zip);
            RCLCPP_INFO(this->get_logger(), "压缩完成: %s", zip_path.c_str());
            return zip_path;
        }
        catch (const std::exception &e)
        {
            zip_close(zip);
            RCLCPP_ERROR(this->get_logger(), "压缩失败: %s", e.what());
            return "";
        }
    }

    std::string LogUploader::generate_signature(const std::string &timestamp)
    {
        std::string sign_str = robot_id_ + timestamp + auth_token_;
        return md5_hash(sign_str);
    }

    bool LogUploader::upload_file(const std::string &file_path)
    {
        std::string timestamp = std::to_string(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch())
                .count());
        std::string sign = generate_signature(timestamp);

        CURL *curl = curl_easy_init();
        if (!curl)
        {
            RCLCPP_ERROR(this->get_logger(), "CURL初始化失败");
            return false;
        }

        // 准备表单数据
        curl_mime *mime = curl_mime_init(curl);
        curl_mimepart *part = curl_mime_addpart(mime);

        // 添加文件部分
        curl_mime_name(part, "file");
        curl_mime_filedata(part, file_path.c_str());

        // 添加其他表单字段
        part = curl_mime_addpart(mime);
        curl_mime_name(part, "robotId");
        curl_mime_data(part, robot_id_.c_str(), CURL_ZERO_TERMINATED);

        part = curl_mime_addpart(mime);
        curl_mime_name(part, "timestamp");
        curl_mime_data(part, timestamp.c_str(), CURL_ZERO_TERMINATED);

        part = curl_mime_addpart(mime);
        curl_mime_name(part, "sign");
        curl_mime_data(part, sign.c_str(), CURL_ZERO_TERMINATED);

        // 设置CURL选项
        curl_easy_setopt(curl, CURLOPT_URL, upload_url_.c_str());
        curl_easy_setopt(curl, CURLOPT_MIMEPOST, mime);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);

        // 响应数据处理
        std::string response_string;
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_string);

        // 重试机制
        for (int attempt = 0; attempt < max_retries_; ++attempt)
        {
            CURLcode res = curl_easy_perform(curl);

            if (res == CURLE_OK)
            {
                long response_code;
                curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &response_code);

                if (response_code == 200)
                {
                    RCLCPP_INFO(this->get_logger(), "上传成功完成!");
                    RCLCPP_INFO(this->get_logger(), "服务器响应: %s", response_string.c_str());
                    curl_mime_free(mime);
                    curl_easy_cleanup(curl);
                    return true;
                }
                else
                {
                    RCLCPP_ERROR(this->get_logger(), "上传失败，状态码: %ld, 响应: %s",
                                 response_code, response_string.c_str());
                }
            }
            else
            {
                RCLCPP_WARN(this->get_logger(), "尝试 %d 失败: %s",
                            attempt + 1, curl_easy_strerror(res));
            }

            if (attempt < max_retries_ - 1)
            {
                std::this_thread::sleep_for(std::chrono::seconds(5));
            }
        }

        curl_mime_free(mime);
        curl_easy_cleanup(curl);
        return false;
    }

    std::string LogUploader::get_current_timestamp()
    {
        auto now = std::chrono::system_clock::now();
        auto in_time_t = std::chrono::system_clock::to_time_t(now);

        std::tm tm_buf;
        localtime_r(&in_time_t, &tm_buf);

        char buffer[80];
        strftime(buffer, sizeof(buffer), "%Y%m%d_%H%M%S", &tm_buf);
        return std::string(buffer);
    }

    size_t LogUploader::write_callback(void *contents, size_t size, size_t nmemb, void *userp)
    {
        ((std::string *)userp)->append((char *)contents, size * nmemb);
        return size * nmemb;
    }

    std::string LogUploader::md5_hash(const std::string &input)
    {
        unsigned char digest[MD5_DIGEST_LENGTH];
        MD5((unsigned char *)input.c_str(), input.length(), digest);

        char mdString[33];
        for (int i = 0; i < 16; i++)
            sprintf(&mdString[i * 2], "%02x", (unsigned int)digest[i]);

        return std::string(mdString);
    }

    void LogUploader::LogUpdateExecuteMove(const std::shared_ptr<GoalHandleLogUpdate> goal_handle)
    {
        auto  goal = goal_handle->get_goal();
        auto result = std::make_shared<ymrobot_msgs::action::LogUpdate::Result>();

        std::string log_file_name = goal->log_file_path;

        trigger_upload_on_startup();
        result->success = true;
        goal_handle->succeed(result);
    }

    void LogUploader::upload_image_task_callback(const std_msgs::msg::String::SharedPtr msg)
    {
        RCLCPP_INFO(this->get_logger(), "收到图片上传任务,上传图像路径: %s", msg->data.c_str());
        std::string image_file_adress = image_file_dir_ + msg->data;

        if (!fs::exists(image_file_adress))
        {
            RCLCPP_ERROR(this->get_logger(), "图片文件不存在: %s", image_file_adress.c_str());
            return;
        }
        UploadFileTask(image_file_adress);
    }
}

int main(int argc, char** argv) {
    // 初始化ROS2
    rclcpp::init(argc, argv);
    
    // 创建LogUploader节点实例
    auto log_uploader = std::make_shared<ymrobot::LogUploader>();
    
    // 触发上传流程
    // log_uploader->trigger_upload_on_startup();
    
    // 保持节点运行
    rclcpp::spin(log_uploader);
    
    // 关闭ROS2
    rclcpp::shutdown();
    return 0;
}