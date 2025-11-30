
#include <vector>
#include <memory>
#include <string>

#include "nav2_util/geometry_utils.hpp"
#include "nav2_util/robot_utils.hpp"
#include "behaviortree_cpp_v3/action_node.h"

#include <ymrobot_msgs/msg/task.hpp>
#include <rclcpp/rclcpp.hpp>

namespace ymrobot
{

  class TraverseNavPose : public BT::SyncActionNode
  {
  public:
    TraverseNavPose(const std::string &xml_tag_name,
                    const BT::NodeConfiguration &conf);

    static BT::PortsList providedPorts()
    {
      return {
          BT::InputPort<ymrobot_msgs::msg::Task>("current_task", "当前任务"),

          BT::OutputPort<std::string>("the_number_of_cycles", "循环次数"),
          BT::OutputPort<std::vector<std::string>>("mark_nav_target_list", "标记目标点列表"),
          BT::OutputPort<std::vector<std::string>>("audio_list", "音频列表"),
          BT::OutputPort<std::vector<std::string>>("fixed_up_action_list", "固定上肢动作列表"),
          BT::OutputPort<std::vector<std::string>>("is_skip_list", "是否要跳过列表"),
          BT::OutputPort<std::vector<std::string>>("is_activate_the_nearby_point", "是否激活就近点"),
          BT::OutputPort<std::vector<std::string>>("nearby_point_radius", "就近点范围"),
          BT::OutputPort<std::string>("task_id", "任务id"),
      };
    }

  private:
    BT::NodeStatus tick() override;
  private:
    rclcpp::Logger logger_{rclcpp::get_logger("traverse_guidance_node")};
  };

}
