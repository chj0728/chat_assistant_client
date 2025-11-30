#include "robot_pose_manager_action_node.hpp"

namespace ymrobot
{
    rclcpp_action::GoalResponse RobotPoseManagerActionNode::HandleGoal(const rclcpp_action::GoalUUID &uuid, std::shared_ptr<const ymrobot_msgs::action::PoseManager::Goal> goal)
    {
        (void)uuid;
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    void RobotPoseManagerActionNode::InitPoseData()
    {
        // 初始化csv文件
        if (pose_manager_csv_adress_.empty())
        {
            RCLCPP_ERROR(this->get_logger(), "file_path is empty");
            return;
        }

        if (!std::filesystem::exists(pose_manager_csv_adress_))
        {
            std::ofstream file(pose_manager_csv_adress_);
            if (!file.is_open())
            {
                RCLCPP_ERROR(this->get_logger(), "Failed to create file");
                return;
            }
            file.close();

            std::vector<std::vector<std::string>> data = {{}};
            sql_manager_.WriteCSVWithHeaders(pose_manager_csv_adress_, pose_name_headers_, data , false);
        }
        else
        {
            RCLCPP_INFO(this->get_logger(), "Pose manager csv file already exists");
        }
    }

    void RobotPoseManagerActionNode::HandleAccepted(const std::shared_ptr<GoalHandlePoseManager> goal_handle)
    {
        std::thread{std::bind(&RobotPoseManagerActionNode::Execute, this, goal_handle)}.detach();
    }

    rclcpp_action::CancelResponse RobotPoseManagerActionNode::HandleCancel(const std::shared_ptr<GoalHandlePoseManager> goal_handle)
    {
        (void)goal_handle;
        return rclcpp_action::CancelResponse::ACCEPT;
    }

    void RobotPoseManagerActionNode::Execute(const std::shared_ptr<GoalHandlePoseManager> goal_handle)
    {
        auto goal = goal_handle->get_goal();
        auto result = std::make_shared<ymrobot_msgs::action::PoseManager::Result>();

        auto pose_describe = goal->pose_describe;
        auto pose_name = goal->pose_name;
        auto pose_manager_type = goal->pose_manager_type;
        auto map_name = goal->map_name;

        if (pose_manager_type == "record")
        {
            RecordCurrentRobotPose(pose_name, map_name, pose_describe, pose_manager_csv_adress_);
            result->success = true;
            result->message = "成功记录当前机器人位姿";
            goal_handle->succeed(result);
        }
        else if (pose_manager_type == "delect")
        {
            DelectPose(pose_name, pose_manager_csv_adress_);
            result->success = true;
            result->message = "成功删除位姿: " + pose_name;
            goal_handle->succeed(result);
        }
    }

    void RobotPoseManagerActionNode::RecordCurrentRobotPose(const std::string &pose_name, const std::string &map_name, const std::string &pose_describe, const std::string &pose_manager_csv_adress)
    {
        std::vector<std::vector<std::string>> data;
        auto robot_pose = GetCurrentPose();
        std::string x = std::to_string(robot_pose.pose.position.x);
        std::string y = std::to_string(robot_pose.pose.position.y);
        std::string z = std::to_string(robot_pose.pose.position.z);
        std::string rx = std::to_string(robot_pose.pose.orientation.x);
        std::string ry = std::to_string(robot_pose.pose.orientation.y);
        std::string rz = std::to_string(robot_pose.pose.orientation.z);
        std::string rw = std::to_string(robot_pose.pose.orientation.w);

        data[0].push_back(pose_name);
        data[0].push_back(map_name);
        data[0].push_back(pose_describe);
        data[0].push_back(x);
        data[0].push_back(y);
        data[0].push_back(z);
        data[0].push_back(rx);
        data[0].push_back(ry);
        data[0].push_back(rz);
        data[0].push_back(rw);

        sql_manager_.WriteCSVWithHeaders(pose_manager_csv_adress, pose_name_headers_, data , true);

        auto update_msg = ymrobot_msgs::msg::UpdateList();
        update_msg.code == ymrobot_msgs::msg::UpdateList::POSE_MANAGER;
        update_list_pub_->publish(update_msg);
    }

    void RobotPoseManagerActionNode::DelectPose(const std::string &pose_name, const std::string &pose_manager_csv_adress)
    {
        if (sql_manager_.DeleteRowsByColumn(pose_manager_csv_adress, 0, pose_name))
        {
            RCLCPP_INFO(this->get_logger(), "成功删除位姿: %s", pose_name.c_str());
        }
        else
        {
            RCLCPP_INFO(this->get_logger(), "无法删除位姿: %s", pose_name.c_str());
        }
    }

    geometry_msgs::msg::PoseStamped RobotPoseManagerActionNode::GetCurrentPose()
    {
        geometry_msgs::msg::PoseStamped robot_pose;

        try
        {
            // 获取机器人当前位置和姿态 (map 坐标系下)
            geometry_msgs::msg::TransformStamped transform = tf_buffer_->lookupTransform(
                "map", "base_link", rclcpp::Time(0), std::chrono::seconds(1));

            // 将 transform 转换成 PoseStamped
            robot_pose.header.stamp = this->get_clock()->now();
            robot_pose.header.frame_id = "map";
            robot_pose.pose.position.x = transform.transform.translation.x;
            robot_pose.pose.position.y = transform.transform.translation.y;
            robot_pose.pose.position.z = transform.transform.translation.z;
            robot_pose.pose.orientation = transform.transform.rotation;

            // 打点，保存位置和姿态
            // points_.push_back(robot_pose);   // 之前的版本
            // std::cout << "保存的点位，x , y: " << robot_pose.pose.position.x << " " << robot_pose.pose.position.y << std::endl;
        }
        catch (const tf2::TransformException &ex)
        {
            RCLCPP_WARN(this->get_logger(), "无法获取机器人的位置和姿态： %s", ex.what());
            robot_pose.header.stamp = this->get_clock()->now();
            robot_pose.header.frame_id = "map";
            robot_pose.pose.position.x = 0.0;
            robot_pose.pose.position.y = 0.0;
            robot_pose.pose.position.z = 0.0;
            robot_pose.pose.orientation.w = 0.0;
            robot_pose.pose.orientation.x = 0.0;
            robot_pose.pose.orientation.y = 0.0;
            robot_pose.pose.orientation.z = 0.0;
        }

        return robot_pose;
    }

    RobotPoseManagerActionNode::RobotPoseManagerActionNode() : Node("robot_pose_manager_action_node")
    {
        Init();
    }

    void RobotPoseManagerActionNode::Init()
    {
        InitParams();
        InitPoseData();
        CreatePubSub();
    }

    void RobotPoseManagerActionNode::InitParams()
    {
        this->declare_parameter("pose_manager_action_name", "/ymrobot/pose_manager_action_server");
        this->declare_parameter("pose_manager_csv_adress", "/home/ymrobot/ymrobot_ws/src/ymrobot/ymrobot_msgs/ymrobot_msgs/pose_manager.csv");
        this->declare_parameter("save_pose_str","");
        this->declare_parameter("delete_pose_str","");

        pose_manager_action_name_ = this->get_parameter("pose_manager_action_name").as_string();
        pose_manager_csv_adress_ = this->get_parameter("pose_manager_csv_adress").as_string();
        save_pose_str_ = this->get_parameter("save_pose_str").as_string();
        delete_pose_str_ = this->get_parameter("delete_pose_str").as_string();

        pose_name_headers_ = {"pose_name", "map_name", "pose_describe", "x", "y", "z", "rx", "ry", "rz", "rw"};
    }

    void RobotPoseManagerActionNode::CreatePubSub()
    {
        update_list_pub_ = this->create_publisher<ymrobot_msgs::msg::UpdateList>(update_list_topic_name_, 1);
        pose_manager_action_server_ = rclcpp_action::create_server<ymrobot_msgs::action::PoseManager>(
            this,
            pose_manager_action_name_,
            std::bind(&RobotPoseManagerActionNode::HandleGoal, this, std::placeholders::_1, std::placeholders::_2),
            std::bind(&RobotPoseManagerActionNode::HandleCancel, this, std::placeholders::_1),
            std::bind(&RobotPoseManagerActionNode::HandleAccepted, this, std::placeholders::_1));
    }
}

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<ymrobot::RobotPoseManagerActionNode>());
    rclcpp::shutdown();
    return 0;
}