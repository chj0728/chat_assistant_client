/*巡逻巡检*/

#include <vector>
#include <memory>
#include <string>

#include "nav2_util/geometry_utils.hpp"
#include "nav2_util/robot_utils.hpp"
#include "behaviortree_cpp_v3/action_node.h"

#include <ymrobot_msgs/msg/task.hpp>
#include <ymrobot_msgs/msg/image_video.hpp>
#include <rclcpp/rclcpp.hpp>

namespace ymrobot
{

  class OnSiteInspectionNode : public BT::SyncActionNode
  {
  public:
    OnSiteInspectionNode(const std::string &xml_tag_name,
                    const BT::NodeConfiguration &conf);

    static BT::PortsList providedPorts()
    {
      return {
          BT::InputPort<ymrobot_msgs::msg::Task>("current_task", "当前任务"),

          BT::OutputPort<std::string>("the_number_of_cycles", "循环次数"),
          BT::OutputPort<std::vector<std::string>>("mark_nav_target_list", "标记目标点列表"),
          BT::OutputPort<std::vector<std::string>>("audio_list", "音频列表"),
          BT::OutputPort<std::vector<std::string>>("fixed_up_action_list", "固定上肢动作列表"),
          BT::OutputPort<std::vector<ymrobot_msgs::msg::ImageVideo>>("image_video_message_list", "图像视频消息列表"),
          BT::OutputPort<std::string>("is_audio_played_throughout_the_entire_process", "是否全程播放音频"),
          BT::OutputPort<std::string>("full_audio_name", "全程音频文件名"),
          BT::OutputPort<std::string>("is_the_entire_process_recorded", "是否全程录制"),
          BT::OutputPort<std::vector<std::string>>("is_activate_the_nearby_point", "是否激活附近点"),
          BT::OutputPort<std::vector<std::string>>("nearby_point_radius", "就近点距离"),
      };
    }

  private:
    BT::NodeStatus tick() override;
  private:
    rclcpp::Logger logger_{rclcpp::get_logger("traverse_guidance_node")};
  };

}
