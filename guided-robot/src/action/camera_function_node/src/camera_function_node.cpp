#include "camera_function_node.hpp"

namespace ymrobot
{
    CameraFunctionNode::CameraFunctionNode() : Node("camera_function_node")
    {
        Init();
    }

    void CameraFunctionNode::Init()
    {
        InitParams();
        CreatePubSub();
        std::cout << "camera_function_node init successed" << std::endl;
    }

    void CameraFunctionNode::InitParams()
    {
        this->declare_parameter("image_sub_name", "");
        this->declare_parameter("cemera_action_server_name", "");
        this->declare_parameter("default_image_path", "");
        this->declare_parameter("video_default_path", "");
        this->declare_parameter("default_video_fps", 30);

        image_sub_name_ = this->get_parameter("image_sub_name").as_string();
        cemera_action_server_name_ = this->get_parameter("cemera_action_server_name").as_string();
        default_image_path_ = this->get_parameter("default_image_path").as_string();
        video_default_path_ = this->get_parameter("video_default_path").as_string();
        default_video_fps_ = this->get_parameter("default_video_fps").as_int();
    }

    void CameraFunctionNode::CreatePubSub()
    {
        image_sub_ = this->create_subscription<sensor_msgs::msg::Image>(image_sub_name_, 10, std::bind(&CameraFunctionNode::ImageSubCallback, this, std::placeholders::_1));
        camera_function_server_ = rclcpp_action::create_server<ymrobot_msgs::action::CameraFunction>(
            this,
            cemera_action_server_name_,
           std::bind(&CameraFunctionNode::CameraFunctionHandleGoal, this, std::placeholders::_1, std::placeholders::_2),
           std::bind(&CameraFunctionNode::CameraFunctionHandleCancel, this, std::placeholders::_1),
           std::bind(&CameraFunctionNode::CameraFunctionHandleAccepted, this, std::placeholders::_1)
        );
    }

    void CameraFunctionNode::ImageSubCallback(const sensor_msgs::msg::Image::SharedPtr msg)
    {
        // RCLCPP_INFO(this->get_logger(), "获取图像");
        try
        {
            cv::Mat image = cv_bridge::toCvCopy(msg, "bgr8")->image; // 将ROS图像消息转换为OpenCV图像格式

            if (image.empty())
            {
                RCLCPP_ERROR(this->get_logger(), "获取的图像为空");
                return;
            }

            // if (image.cols != 1920 || image.rows != 1080) {
            //     RCLCPP_WARN(this->get_logger(), "图像分辨率非1920x1080，当前为: %dx%d", image.cols, image.rows);
            // }
            //cv::imwrite("/home/ymrobot/image.jpg", image); // 保存图像
            // cv::imshow("高清图像", image);                 // 显示图像
            // cv::waitKey(1);                                // 等待1ms以刷新图像显示
        }
        catch (cv_bridge::Exception &e)
        {
            RCLCPP_ERROR(this->get_logger(), "图像转换失败: %s", e.what());
        }

        std::unique_lock<std::shared_mutex> l1(image_mutex_);
        last_image_ = msg;
    }

    rclcpp_action::GoalResponse CameraFunctionNode::CameraFunctionHandleGoal(const rclcpp_action::GoalUUID &, std::shared_ptr<const ymrobot_msgs::action::CameraFunction::Goal> goal)
    {
        RCLCPP_INFO(this->get_logger(), "收到相机功能请求");
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    rclcpp_action::CancelResponse CameraFunctionNode::CameraFunctionHandleCancel(const std::shared_ptr<GoalHandleSaveMedia> goal_handle)
    {
        RCLCPP_INFO(this->get_logger(), "收到取消请求");
        (void)goal_handle;
        return rclcpp_action::CancelResponse::ACCEPT;
    }

    void CameraFunctionNode::CameraFunctionHandleAccepted(const std::shared_ptr<GoalHandleSaveMedia> goal_handle)
    {
        std::thread{std::bind(&CameraFunctionNode::CameraFunctionExecuteMove, this, std::placeholders::_1), goal_handle}.detach();
    }

    void CameraFunctionNode::CameraFunctionExecuteMove(const std::shared_ptr<GoalHandleSaveMedia> goal_handle)
    {
        const auto goal = goal_handle->get_goal();                                          // 获取目标参数
        auto result = std::make_shared<ymrobot_msgs::action::CameraFunction::Result>();     // 创建结果对象
        auto feedback = std::make_shared<ymrobot_msgs::action::CameraFunction::Feedback>(); // 创建反馈对象

        // 获取最新图像（线程安全）
        sensor_msgs::msg::Image::SharedPtr image_msg;
        {
            std::shared_lock<std::shared_mutex> l1(image_mutex_); // 加锁
            if (!last_image_)
            {
                result->success = false;
                result->message = "尚未收到任何图像";
                goal_handle->succeed(result); // 返回失败结果
                return;
            }
            image_msg = last_image_; // 获取最新图像
        }

        try
        {
            cv::Mat frame = cv_bridge::toCvCopy(image_msg, "bgr8")->image;
            if (goal->camera_task_type == 0)
            {
                RCLCPP_INFO(this->get_logger(), "保存图片模式");
                // 保存多张图片模式
                int image_count = goal->number_of_photos; // 拍照数量
                int interval_sec = goal->photos_interval; // 时间去间隔ms
                // int interval_sec = 30;

                for (int i = 0; i < image_count && rclcpp::ok() && !goal_handle->is_canceling(); ++i)
                {
                    // 获取最新帧
                    {
                        std::shared_lock<std::shared_mutex> l1(image_mutex_);
                        if (!last_image_)
                            continue;
                        frame = cv_bridge::toCvCopy(last_image_, "bgr8")->image;
                    }

                    // 生成文件名
                    std::string image_path = GetFileName(default_image_path_, "image", "jpg", true); // 使用序号而不是时间戳

                    // 保存图片
                    if (!cv::imwrite(image_path, frame))
                    {
                        throw std::runtime_error("无法保存图片: " + image_path);
                    }

                    // 如果不是最后一张，等待间隔
                    if (i < image_count - 1 && interval_sec > 0)
                    {
                        std::cout << "等待 " << interval_sec << " 毫秒..." << std::endl;
                        rclcpp::sleep_for(std::chrono::milliseconds(interval_sec)); // 等待 interval_sec 毫秒
                    }
                }

                if (goal_handle->is_canceling())
                {
                    result->success = false;
                    result->message = "图片保存被取消";
                    goal_handle->canceled(result);
                }
                else
                {
                    result->success = true;
                    result->message = "成功保存 " + std::to_string(image_count) + " 张图片";
                    std::cout << "成功保存 " << image_count << " 张图片" << std::endl;
                    goal_handle->succeed(result);
                }

                return;
            }

            if (goal->camera_task_type == 1)
            {
                int duration_sec = goal->video_recording_time;
                cv::VideoWriter video_writer;
                int width = frame.cols;
                int height = frame.rows;

                // 初始化视频写入器
                std::cout <<"video_default_path_:" << video_default_path_ << std::endl;
                auto now = std::chrono::system_clock::now();
                auto now_ms = std::chrono::time_point_cast<std::chrono::milliseconds>(now);
                auto epoch = now_ms.time_since_epoch();
                auto value = std::chrono::duration_cast<std::chrono::milliseconds>(epoch);
                long long timestamp = value.count();
    
                // 将时间戳添加到文件名中
                video_default_path_ += "vedio_" + std::to_string(timestamp) +  ".avi" ;

                video_writer.open(video_default_path_, cv::VideoWriter::fourcc('X', 'V', 'I', 'D'), default_video_fps_, cv::Size(width, height));

                if (!video_writer.isOpened())
                {
                    throw std::runtime_error("无法打开视频写入器");
                }

                auto start_time = this->now();              // 记录开始时间
                rclcpp::Rate loop_rate(default_video_fps_); // 控制帧率

                // 录制循环
                while (rclcpp::ok() && !goal_handle->is_canceling())
                {
                    {
                        std::shared_lock<std::shared_mutex> l1(image_mutex_); // 加锁
                        if (!last_image_)
                            continue;
                        frame = cv_bridge::toCvCopy(last_image_, "bgr8")->image;
                    }
                    video_writer.write(frame); // 写入帧

                    // 计算并发送进度反馈
                    auto elapsed = (this->now() - start_time).seconds();
                    // float progress = std::min(1.0f, static_cast<float>(elapsed) / duration_sec);

                    // feedback->progress = progress;
                    // feedback->status = "录制中: " + std::to_string(static_cast<int>(elapsed)) +
                    //                    "秒 / " + std::to_string(duration_sec) + "秒";
                    // goal_handle->publish_feedback(feedback);

                    if (elapsed >= duration_sec)
                    {
                        break;
                    }
                    loop_rate.sleep(); // 控制帧率
                }
                video_writer.release();

                result->success = true;
                result->message = "视频录制成功";
                goal_handle->succeed(result); // 返回成功结果
            }
        }
        catch (const std::exception &e)
        {
            std::cerr << e.what() << '\n';
        }
    }

    std::string CameraFunctionNode::GetFileName(const std::string &dir, const std::string &prefix, const std::string &extension, bool use_timestamp)
    {
        std::string filename = dir + "/" + prefix;

        if (use_timestamp)
        {
            // 获取当前时间
            auto now = std::chrono::system_clock::now();
            auto now_ms = std::chrono::time_point_cast<std::chrono::milliseconds>(now);
            auto epoch = now_ms.time_since_epoch();
            auto value = std::chrono::duration_cast<std::chrono::milliseconds>(epoch);
            long long timestamp = value.count();

            // 将时间戳添加到文件名中
            filename += "_" + std::to_string(timestamp);
        }

        filename += "." + extension;
        return filename;
    }
}

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<ymrobot::CameraFunctionNode>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
