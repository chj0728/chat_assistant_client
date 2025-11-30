#include "relocation_node.hpp"

namespace ymrobot
{
    RelocationNode::RelocationNode() : Node("relocation_node")
    {
        Init();
    }

    void RelocationNode::Init()
    {
        InitParams();
        CreateActionServer();
    }

    void RelocationNode::InitParams()
    {
        RCLCPP_INFO(this->get_logger(), "初始化参数");
        this->declare_parameter<std::string>("relcation_action_str", "relcation_action");
        this->declare_parameter<std::string>("relocalizer_task_srv_name", "relocalizer_task_srv");
        this->declare_parameter<std::string>("re_pcd_srv_name", "re_pcd_srv");
        this->declare_parameter<std::string>("maps_dir", "/home/ymrobot/ymrobot_ws/src/ymrobot/ymrobot_map/maps");

        relcation_action_str_ = this->get_parameter("relcation_action_str").as_string();
        relocalizer_task_srv_name_ = this->get_parameter("relocalizer_task_srv_name").as_string();
        re_pcd_srv_name_ = this->get_parameter("re_pcd_srv_name").as_string();
        maps_dir_ = this->get_parameter("maps_dir").as_string();
    }

    void RelocationNode::CreateActionServer()
    {
        map_mode_pub_ = this->create_publisher<std_msgs::msg::UInt8>("map_mode", 1);
        nav2_map_client_ = this->create_client<nav2_msgs::srv::LoadMap>("map_server/load_map");
        reloclizer_client_ = this->create_client<ymrobot_msgs::srv::SlamTaskManage>(relocalizer_task_srv_name_);
        reloclizer_pcd_client_ = this->create_client<interface::srv::Relocalize>(re_pcd_srv_name_);
        // 创建重定位Action服务
        relcation_action_server_ = rclcpp_action::create_server<RelocationAction>(
            this,
            relcation_action_str_, // 服务名称
            std::bind(&RelocationNode::HandleGoal, this, std::placeholders::_1, std::placeholders::_2),
            std::bind(&RelocationNode::HandleCancel, this, std::placeholders::_1),
            std::bind(&RelocationNode::HandleAccepted, this, std::placeholders::_1));
    }

    bool RelocationNode::IsMapFileExist(const std::string &path)
    {
        std::ifstream file(path);
        return file.good();
    }

    bool RelocationNode::LoadMap(const std::string &map_yaml_path)
    {
        RCLCPP_INFO(this->get_logger(), "[TaskGuidance]: 加载地图");
        std_msgs::msg::UInt8 map_mode;
        map_mode.data = 2;
        map_mode_pub_->publish(map_mode);

        auto request = std::make_shared<nav2_msgs::srv::LoadMap::Request>();
        request->map_url = map_yaml_path;
        auto future = nav2_map_client_->async_send_request(request);

        future.wait();

        if (future.get()->result == nav2_msgs::srv::LoadMap::Response::RESULT_SUCCESS)
        {
            RCLCPP_INFO(this->get_logger(), "地图加载成功");
            return true;
        }
        else
        {
            RCLCPP_ERROR(this->get_logger(), "地图加载失败，错误信息");
            return false;
        }
    }

    int srv_count = 0;
    bool RelocationNode::StartLocalizerSlam(const std::string &pcd_path)
    {
        RCLCPP_INFO(logger_, "pcd地图地址: %s", pcd_path.c_str());
        auto request = std::make_shared<ymrobot_msgs::srv::SlamTaskManage::Request>();
        auto slam_task_action = ymrobot_msgs::msg::SlamCommand();

        request->task = "relocalize"; // slam_task_action.relocalize
        request->action = "start";
        auto future = reloclizer_client_->async_send_request(request);
        future.wait();
        if (future.get()->success)
        {
            RCLCPP_INFO(logger_, "启动本地化SLAM成功");
        }
        else
        {
            RCLCPP_ERROR(logger_, "启动本地化SLAM失败，错误信息:%s", future.get()->message.c_str());
            return false;
        }
        
        /*下面设置初始化pose 、 加载pcd地址。暂时屏蔽*/
        // auto request2 = std::make_shared<interface::srv::Relocalize::Request>();
        // request2->pcd_path = std::move(pcd_path);
        // request2->x = 0.0;
        // request2->y = 0.0;
        // request2->z = 0.0;
        // request2->yaw = 0.0;
        // request2->pitch = 0.0;
        // request2->roll = 0.0;

        // while (!reloclizer_pcd_client_->wait_for_service(std::chrono::seconds(1)))
        // {
        //     if (srv_count > 10)
        //     {
        //         RCLCPP_INFO(logger_, "重定位,pcd初始化服务端超时，超过10s");
        //         srv_count = 0;
        //         break;
        //     }
        //     ++srv_count;
        //     RCLCPP_INFO(logger_, "Waiting for service to be available...");
        // }

        // srv_count = 0;
        // auto future2 = reloclizer_pcd_client_->async_send_request(request2);
        // future2.wait();
        // if (future2.get()->success)
        // {
        //     RCLCPP_INFO(logger_, "重定位成功");
        //     return true;
        // }
        // else
        // {
        //     RCLCPP_ERROR(logger_, "重定位失败，错误信息:%s", future2.get()->message.c_str());
        //     return false;
        // }
    }

    rclcpp_action::GoalResponse RelocationNode::HandleGoal(const rclcpp_action::GoalUUID &uuid, std::shared_ptr<const RelocationAction::Goal> goal)
    {
        RCLCPP_INFO(this->get_logger(), "Received goal request");
        // 这里可以根据 goal 进行一些检查和处理
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    void RelocationNode::HandleAccepted(const std::shared_ptr<GoalHandleRelocation> goal_handle)
    {
        std::thread{std::bind(&RelocationNode::Execute, this, goal_handle)}.detach();
    }

    rclcpp_action::CancelResponse RelocationNode::HandleCancel(const std::shared_ptr<GoalHandleRelocation> goal_handle)
    {
        RCLCPP_INFO(this->get_logger(),"[HandleCancel]Task is cancel and stop robot");
        return rclcpp_action::CancelResponse::ACCEPT;
    }

    void RelocationNode::Execute(const std::shared_ptr<GoalHandleRelocation> goal_handle)
    {
        RCLCPP_INFO(logger_, "开始重定位任务");

        // 从目标获取命令
        const auto task = goal_handle->get_goal();
        if(task->map_name.empty())
        {
            RCLCPP_ERROR(logger_, "无效的任务命令或参数");
            auto result = std::make_shared<RelocationAction::Result>();
            result->success = false;
            goal_handle->abort(result);
            return;
        }

        std::string map_file = task->map_name;
        std::string map_file_path = maps_dir_ + "/" + map_file + "/map.yaml";
        std::string pcd_file_path = maps_dir_ + "/" + map_file + "/map.pcd";

        RCLCPP_INFO(logger_, "开始加载地图任务,地图文件地址为:%s", map_file_path.c_str());

        // 检查地图文件是否存在
        if (!IsMapFileExist(map_file_path))
        {
            RCLCPP_ERROR(logger_, "地图文件不存在. 地图文件地址为：%s", map_file_path.c_str());
            auto result = std::make_shared<RelocationAction::Result>();
            result->success = false;
            goal_handle->abort(result);
            return;
        }

        // 加载地图文件
        if (!LoadMap(map_file_path))
        {
            RCLCPP_ERROR(logger_, "加载地图失败. 地图文件地址为：%s", map_file_path.c_str());
            auto result = std::make_shared<RelocationAction::Result>();
            result->success = false;
            goal_handle->abort(result);
            return;
        }

        RCLCPP_INFO(logger_, "开始重定位任务");

        // 启动定位任务
        if (!StartLocalizerSlam(pcd_file_path))
        {
            RCLCPP_ERROR(logger_, "启动定位失败");
            auto result = std::make_shared<RelocationAction::Result>();
            result->success = false;
            goal_handle->abort(result);
            return;
        }

        // 如果一切成功，返回结果
        auto result = std::make_shared<RelocationAction::Result>();
        result->success = true;
        goal_handle->succeed(result);
        RCLCPP_INFO(logger_, "重定位任务完成");
    }
} // namespace name

int main(int argc, char *argv[])
{
    /* 初始化ROS2 */
    rclcpp::init(argc, argv);

    rclcpp::spin(std::make_shared<ymrobot::RelocationNode>());

    rclcpp::shutdown();
    return 0;
}
