#include <iostream>
#include <fstream>
#include <mutex>
#include <unistd.h>
#include <fstream>
#include <sstream>
#include <mntent.h>
#include <vector>
#include <dirent.h>
#include <algorithm>
#include <dirent.h>
#include <sys/stat.h>

namespace ymrobot
{
    class RobotDeviceStatus
    {
    public:
        RobotDeviceStatus();
        //~RobotDeviceStatus();

        double GetCpuUsage(const int &id_num);
        double GetCpuTemperature();
        double GetMemoryUsage();
        double GetDiskUsage();
        std::vector<std::string> GetMp3FilesName(const std::string &mp3_path);
        // 获取电机信息
        // 获取电信息
    };
}