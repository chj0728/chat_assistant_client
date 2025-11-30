/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 25-02-13.
 */
#include "amr_behavior_tree/plugins/action/voice_interaction.hpp"

namespace ymrobot
{
    VoiceInteractionNode::VoiceInteractionNode(const std::string &service_node_name,
                                               const BT::NodeConfiguration &conf)
        : BT::SyncActionNode(service_node_name, conf)
    {
        node_ = rclcpp::Node::make_shared("voice_interaction_node");
        audio_control_client_ = node_->create_client<ymrobot_msgs::srv::Audio>("audio_control_action_srv");
        auido_update_pub_ = node_->create_publisher<ymrobot_msgs::msg::UpdateList>("update_list", 10);
    }

    // VoiceInteractionNode::VoiceInteractionNode(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf) : nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::AudioControl>(xml_tag_name, action_name,
    //                                                                                                                                                                                                                       conf)
    // {
    //     node_ = rclcpp::Node::make_shared("voice_interaction_node");
    //     audio_control_client_ = node_->create_client<ymrobot_msgs::srv::Audio>("audio_control_action_srv");
    //     auido_update_pub_ = node_->create_publisher<ymrobot_msgs::msg::UpdateList>("update_list", 10);
    // }

    BT::NodeStatus VoiceInteractionNode::tick()
    {
        //audio_control_client_ = node_->create_client<ymrobot_msgs::srv::Audio>("/audio_control_action_srv");
        int audio_task_type_str;
        std::string fixed_audio_name_str;
        std::string synthetic_audio_txt_str;
        std::string synthetic_audio_title_str;
        std::string delete_fixed_audio_str;
        ymrobot_msgs::msg::VoiceMessage voice_message;

        getInput("voice_message", voice_message);
        audio_task_type_str = voice_message.audio_task_type;

        if (audio_task_type_str == 0)
        {
            // goal_.audio_task_type = 0;
            // goal_.fixed_audio_name = voice_message.fixed_audio_name;
            // RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]播放固定音频 : %s", voice_message.fixed_audio_name.c_str());
            std::cout <<"**********请求播放固定音频" << std::endl;
            
            auto audio_srv_msg_req = std::make_shared<ymrobot_msgs::srv::Audio::Request>();
            audio_srv_msg_req->audio_task_type = 0;
            audio_srv_msg_req->fixed_audio_name = voice_message.fixed_audio_name;

            auto reuslt_future = audio_control_client_->async_send_request(audio_srv_msg_req);
            // reuslt_future.wait();

            // if (reuslt_future.get()->success)
            // {
            //     RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]:播放固定音频成功");
            //     return BT::NodeStatus::SUCCESS;
            // }
            // else
            // {
            //     RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]:播放固定音频失败");
            //     return BT::NodeStatus::FAILURE;
            // }

            RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]:播放固定音频成功");
            return BT::NodeStatus::SUCCESS;
        }
        else if (audio_task_type_str == 1)
        {
            // synthetic_audio_title_str = voice_message.synthetic_audio_title;
            // synthetic_audio_txt_str = voice_message.synthetic_audio_txt;
            // goal_.audio_task_type = 1;
            // goal_.synthetic_audio_title = synthetic_audio_title_str;
            // goal_.synthetic_audio_txt = synthetic_audio_txt_str;
            // RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]执行文字转语音(合成音频) : %s", synthetic_audio_title_str.c_str());
            std::cout <<"**********请求合成音频" << std::endl;
            
            auto audio_srv_msg_req = std::make_shared<ymrobot_msgs::srv::Audio::Request>();
            audio_srv_msg_req->audio_task_type = 1;
            audio_srv_msg_req->synthetic_audio_title = voice_message.synthetic_audio_title;
            audio_srv_msg_req->synthetic_audio_txt = voice_message.synthetic_audio_txt;
            audio_srv_msg_req->timbre = voice_message.timbre;
            std::cout <<"音色： "<<voice_message.timbre<<std::endl;
            std::cout <<"synthetic_audio_txt "<<voice_message.synthetic_audio_txt<<std::endl;
            std::cout <<"synthetic_audio_title "<<voice_message.synthetic_audio_title<<std::endl;
            auto reuslt_future = audio_control_client_->async_send_request(audio_srv_msg_req);

            RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]:合成音频成功");
            ymrobot_msgs::msg::UpdateList update_list_msg;
            update_list_msg.code = ymrobot_msgs::msg::UpdateList::AUDIO;
            auido_update_pub_->publish(update_list_msg);
            return BT::NodeStatus::SUCCESS;
   
            // if (reuslt_future.get()->success)
            // {
            //     RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]:合成音频成功");
            //     setStatus(BT::NodeStatus::SUCCESS);
            //     ymrobot_msgs::msg::UpdateList update_list_msg;
            //     update_list_msg.code = ymrobot_msgs::msg::UpdateList::AUDIO;
            //     auido_update_pub_->publish(update_list_msg);
            //     setStatus(BT::NodeStatus::SUCCESS);
            // }
            // else
            // {
            //     RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]:合成音频失败");
            //     setStatus(BT::NodeStatus::FAILURE);
            // }
        }
        else if (audio_task_type_str == 2)
        {
            // delete_fixed_audio_str = voice_message.delete_fixed_audio;
            // goal_.audio_task_type = 2;
            // goal_.delete_fixed_audio = delete_fixed_audio_str;
            // RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]删掉固定音频 : %s", delete_fixed_audio_str.c_str());
        }
        else if (audio_task_type_str == 3)
        {
            // goal_.audio_task_type = 3;

            auto audio_srv_msg_req = std::make_shared<ymrobot_msgs::srv::Audio::Request>();
            audio_srv_msg_req->audio_task_type = 3;

            auto reuslt_future = audio_control_client_->async_send_request(audio_srv_msg_req);
            // reuslt_future.wait();
            return BT::NodeStatus::SUCCESS;

            // if (reuslt_future.get()->success)
            // {
            //     RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]:上传对话记录日志成功");
            //     return BT::NodeStatus::SUCCESS;
            // }
            // else
            // {
            //     RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]:上传对话记录日志失败");
            //     return BT::NodeStatus::FAILURE;
            // }
        }
        else if (audio_task_type_str == 4)
        {
            std::cout <<"**********请求播放在线音频" << std::endl;
            // goal_.audio_task_type = 4;
            // goal_.play_online_audio = voice_message.play_online_audio;
            auto audio_srv_msg_req = std::make_shared<ymrobot_msgs::srv::Audio::Request>();
            audio_srv_msg_req->audio_task_type = 4;
            audio_srv_msg_req->play_online_audio = voice_message.play_online_audio;
            audio_srv_msg_req->timbre = voice_message.timbre;
            RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]播放在线音频: %s", voice_message.play_online_audio.c_str());
            auto reuslt_future = audio_control_client_->async_send_request(audio_srv_msg_req);
            return BT::NodeStatus::SUCCESS;
            // reuslt_future.wait();

            // if(reuslt_future.get()->success)
            // {
            //     RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]:播放在线音频成功");
            //     return BT::NodeStatus::SUCCESS;
            // }
            // else
            // {
            //     RCLCPP_INFO(node_->get_logger(), "[VoiceInteractionNode]:播放在线音频失败");
            //     return BT::NodeStatus::FAILURE;
            // }
        }
    }
}

#include "behaviortree_cpp_v3/bt_factory.h"

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<ymrobot::VoiceInteractionNode>("VoiceInteractionNode");
}