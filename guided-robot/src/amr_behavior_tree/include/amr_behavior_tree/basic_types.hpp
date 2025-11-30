#pragma once

#include <memory>
#include <string>

#include "behaviortree_cpp_v3/basic_types.h"

namespace BT {
template <>
uint8_t convertFromString<uint8_t>(StringView str) {
  return static_cast<uint8_t>(std::atoi(str.data()));
}
}  // namespace BT

namespace ymrobot {

namespace amr_bt {}

}  // namespace ymrobot
