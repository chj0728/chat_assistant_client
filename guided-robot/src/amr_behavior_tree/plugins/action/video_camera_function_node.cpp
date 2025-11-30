/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 25-02-13.
 */
#include "amr_behavior_tree/plugins/action/video_camera_function_node.hpp"

namespace ymrobot
{
    VideoCameraFunctionNode::VideoCameraFunctionNode(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf) : nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::CameraFunction>(xml_tag_name, action_name,
                                                                                                                                                                                                                                conf)
    {
    }

    void VideoCameraFunctionNode::on_tick()
    {
        ymrobot_msgs::msg::ImageVideo image_vedio_msg;

        if (!getInput<ymrobot_msgs::msg::ImageVideo>("image_vedio_msg", image_vedio_msg))
        {
            throw BT::RuntimeError("[play_fixed_audio_node]Missing required input [play_fixed_audio_node]");
        }

        if(image_vedio_msg.camera_task_type == 0)
        {
            RCLCPP_INFO(node_->get_logger(), "[VideoCameraFunctionNode]执行拍照");
            goal_.camera_task_type = 0;
            goal_.number_of_photos = image_vedio_msg.number_of_photos;
            goal_.photos_interval = image_vedio_msg.photos_interval;
        }
        else if(image_vedio_msg.camera_task_type == 1)
        {
            goal_.camera_task_type = 1;
            goal_.video_recording_time = image_vedio_msg.video_recording_time;
        }
        else if(image_vedio_msg.camera_task_type == 2)
        {
            goal_.camera_task_type = 2;
            goal_.number_of_photos = image_vedio_msg.number_of_photos;
            goal_.photos_interval = image_vedio_msg.photos_interval;
            goal_.video_recording_time = image_vedio_msg.video_recording_time;
        }
        
    }

    BT::NodeStatus VideoCameraFunctionNode::on_aborted()
    {
        RCLCPP_ERROR(node_->get_logger(), "[VideoCameraFunctionNode]Failure.");
        return BT::NodeStatus::FAILURE;
    }

    BT::NodeStatus VideoCameraFunctionNode::on_success()
    {
        RCLCPP_INFO(node_->get_logger(), "[VideoCameraFunctionNode]Success.");
        return BT::NodeStatus::SUCCESS;
    }

}

#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
    BT::NodeBuilder builder = [](const std::string &name,
                                 const BT::NodeConfiguration &config)
    {
        return std::make_unique<ymrobot::VideoCameraFunctionNode>(name, "cemera_action_server", config);
    };

    factory.registerBuilder<ymrobot::VideoCameraFunctionNode>("VideoCameraFunctionNode", builder);
}