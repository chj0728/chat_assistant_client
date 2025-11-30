#include "audio_control_node.hpp"

#define AUDIO_CONTROL_TASK_RESULT 1

namespace ymrobot
{
    AudioControlNode::AudioControlNode() : Node("audio_control_node")
    {
        Init();
    }

    void AudioControlNode::Init()
    {
        InitParams();
        CreateActionServer();
    }

    void AudioControlNode::InitParams()
    {
        this->declare_parameter("modify_timbre_sub_name", ""); 
        this->declare_parameter("audio_action_server_name", "audio_control_server");
        this->declare_parameter("audio_control_action_name", "audio_control_action");
        this->declare_parameter("service_wait_over_time", 5);

        modify_timbre_sub_name_ = this->get_parameter("modify_timbre_sub_name").as_string();
        audio_action_server_name_ = this->get_parameter("audio_action_server_name").as_string();
        audio_control_action_name_ = this->get_parameter("audio_control_action_name").as_string();
        service_wait_over_time_ = this->get_parameter("service_wait_over_time").as_int();

        wait_service_time_ = 0;
        std::cout << "audio_control_node init params successed" << std::endl;
        std::cout << "audio_action_server_name_: " << audio_action_server_name_ << std::endl;
        std::cout << "audio_control_action_name_: " << audio_control_action_name_ << std::endl;
        std::cout << "service_wait_over_time_: " << service_wait_over_time_ << std::endl;
    }

    void AudioControlNode::CreateActionServer()
    {
        modify_timbre_sub_ = this->create_subscription<std_msgs::msg::String>(modify_timbre_sub_name_, 1, std::bind(&AudioControlNode::ModifyTimbreSubCallback, this, std::placeholders::_1));
        audio_control_client_ = this->create_client<ymrobot_msgs::srv::Audio>(audio_action_server_name_);
        audio_action_server_ = rclcpp_action::create_server<ymrobot_msgs::action::AudioControl>(
            this,
            audio_control_action_name_,
            std::bind(&AudioControlNode::AudioHandleGoal, this, std::placeholders::_1, std::placeholders::_2),
            std::bind(&AudioControlNode::AudioHandleCancel, this, std::placeholders::_1),
            std::bind(&AudioControlNode::AudioHandleAccepted, this, std::placeholders::_1));
    }

    rclcpp_action::GoalResponse AudioControlNode::AudioHandleGoal(const rclcpp_action::GoalUUID &, std::shared_ptr<const ymrobot_msgs::action::AudioControl::Goal> goal)
    {
        RCLCPP_INFO(this->get_logger(), "收到执行语音交互的请求");
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    rclcpp_action::CancelResponse AudioControlNode::AudioHandleCancel(const std::shared_ptr<GoalHandleAudio> goal_handle)
    {
        RCLCPP_INFO(this->get_logger(), "收到取消语音交互请求");
        (void)goal_handle;
        return rclcpp_action::CancelResponse::ACCEPT;
    }

    void AudioControlNode::AudioHandleAccepted(const std::shared_ptr<GoalHandleAudio> goal_handle)
    {
        std::thread(std::bind(&AudioControlNode::AudioExecuteMove, this, goal_handle)).detach();
    }

    void AudioControlNode::AudioExecuteMove(const std::shared_ptr<GoalHandleAudio> goal_handle)
    {
        auto goal = goal_handle->get_goal();
        auto result = std::make_shared<ymrobot_msgs::action::AudioControl::Result>();
        auto feedback = std::make_shared<ymrobot_msgs::action::AudioControl::Feedback>();
        auto audio_control_mode = goal->audio_task_type;
        auto audio_control_task_resquest = std::make_shared<ymrobot_msgs::srv::Audio::Request>();
        auto start_time = this->now();

        switch (audio_control_mode)
        {
        case 0:
        {
            RCLCPP_INFO(this->get_logger(), "语音交互任务: 播放固定音频： %s", goal->fixed_audio_name.c_str());
            audio_control_task_resquest->audio_task_type = 0;
            audio_control_task_resquest->fixed_audio_name = goal->fixed_audio_name;
            break;
        }
        default:
            break;
        }

        while (!audio_control_client_->wait_for_service(std::chrono::seconds(1)))
        {
            if (!rclcpp::ok())
            {
                RCLCPP_ERROR(this->get_logger(), "等待服务的过程中被打断...");
            }

            if (wait_service_time_ >= service_wait_over_time_)
            {
                RCLCPP_INFO(this->get_logger(), "等待语音交互服务端上线超时,超过 %d s", service_wait_over_time_);
                result->success = false;
                result->message = "语音服务端上线超时";
                goal_handle->abort(result);
                is_audio_control_task_successed_.store(AudioTaskResult::RUNNING);
                wait_service_time_ = 0;
                return;
            }

            wait_service_time_++;
            RCLCPP_INFO(this->get_logger(), "等待上臂服务端上线中");
        }
        wait_service_time_ = 0;

        audio_control_client_->async_send_request(audio_control_task_resquest, std::bind(&AudioControlNode::AudioControlCallBack, this, std::placeholders::_1));

        rclcpp::Rate rate(AUDIO_CONTROL_TASK_RESULT);
        while (rclcpp::ok())
        {
            auto current_time = this->now();
            auto elapsed_time = current_time - start_time;
            double total_elapsed_time_seconds = elapsed_time.seconds() + elapsed_time.nanoseconds() / 1e9;

            if (is_audio_control_task_successed_.load() == AudioTaskResult::SUCCESSED)
            {
                result->success = true;
                result->message = "语音交互任务成功";
                result->total_elapsed_time = total_elapsed_time_seconds;
                goal_handle->succeed(result);
                is_audio_control_task_successed_.store(AudioTaskResult::RUNNING);
                return;
            }
            else if (is_audio_control_task_successed_.load() == AudioTaskResult::FAILED)
            {
                result->success = false;
                result->message = "语音交互任务失败";
                result->total_elapsed_time = total_elapsed_time_seconds;
                goal_handle->abort(result);
                is_audio_control_task_successed_.store(AudioTaskResult::RUNNING);
                return;
            }
            else
            {
                feedback->message = "语音交互任务进行中";
                feedback->total_elapsed_time = total_elapsed_time_seconds;
                goal_handle->publish_feedback(feedback);
            }
            rate.sleep();
        }
    }

    void AudioControlNode::ModifyTimbreSubCallback(const std_msgs::msg::String::SharedPtr msg)
    {
        std::cout << "修改音色： " << msg->data << std::endl;
    }

    void AudioControlNode::AudioControlCallBack(rclcpp::Client<ymrobot_msgs::srv::Audio>::SharedFuture result_future)
    {
        auto audio_control_result = result_future.get()->success;
        if (audio_control_result)
        {
            RCLCPP_INFO(logger_, "语音交互任务成功");
            is_audio_control_task_successed_.store(AudioTaskResult::SUCCESSED);
        }
        else
        {
            RCLCPP_INFO(logger_, "语音交互任务失败");
            is_audio_control_task_successed_.store(AudioTaskResult::FAILED);
        }
    }
}

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<ymrobot::AudioControlNode>());
    rclcpp::shutdown();
    return 0;
}