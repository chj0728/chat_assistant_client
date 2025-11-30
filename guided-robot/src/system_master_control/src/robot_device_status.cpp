#include "robot_device_status.hpp"
namespace ymrobot
{
    RobotDeviceStatus::RobotDeviceStatus()
    {
    }

    double RobotDeviceStatus::GetCpuUsage(const int &id_num)
    {
        std::string filename = "/proc/stat";
        std::ifstream file(filename);
        if (!file.is_open())
        {
            // std::cout << "Error: unable to open " << filename << std::endl;
            return -1;
        }

        std::string line;
        std::getline(file, line); // skip the first line

        // 读取cpuN部分
        std::string cpu_line;
        for (int i = 0; i <= id_num; i++)
        {
            std::getline(file, cpu_line);
        }

        std::istringstream iss(cpu_line);
        std::string token;
        long double user, nice, system, idle;
        iss >> token >> user >> nice >> system >> idle;

        // 计算CPU使用率
        double cpu_usage = ((user + nice + system) / (user + nice + system + idle)) * 100;

        return cpu_usage;
    }

    double RobotDeviceStatus::GetCpuTemperature()
    {
        std::string filename = "/sys/class/thermal/thermal_zone0/temp";
        std::ifstream file(filename);
        if (!file.is_open())
        {
            // std::cerr << "Error: unable to open " << filename << std::endl;
            return -1;
        }

        std::string line;
        std::getline(file, line);
        file.close();

        // 将温度数据从字符串转换为整数
        int temperature = std::stoi(line);

        // 将温度从毫度转换为摄氏度
        double temperature_celsius = temperature / 1000.0;

        return temperature_celsius;
    }

    double RobotDeviceStatus::GetMemoryUsage()
    {
        std::string filename = "/proc/meminfo";
        std::ifstream file(filename);
        if (!file.is_open())
        {
            // std::cerr << "Error: unable to open " << filename << std::endl;
            return -1;
        }

        std::string line;
        std::getline(file, line); // skip the first line

        // 读取MemTotal和MemFree
        long total_memory, free_memory;
        while (std::getline(file, line))
        {
            if (line.find("MemTotal") != std::string::npos)
            {
                std::istringstream iss(line);
                std::string token;
                iss >> token >> total_memory;
            }
            else if (line.find("MemFree") != std::string::npos)
            {
                std::istringstream iss(line);
                std::string token;
                iss >> token >> free_memory;
                break;
            }
        }

        file.close();

        // 计算内存使用率
        double memory_usage = ((total_memory - free_memory) / (double)total_memory) * 100;

        return memory_usage;
    }

    std::vector<std::string> RobotDeviceStatus::GetMp3FilesName(const std::string &mp3_path)
    {
        std::vector<std::string> file_names;
        DIR *dir = opendir(mp3_path.c_str());

        if (dir)
        {
            struct dirent *entry;
            while ((entry = readdir(dir)) != nullptr)
            {
                std::string name = entry->d_name;

                // 构造完整路径并验证文件类型‌:ml-citation{ref="4,5" data="citationList"}
                std::string full_path = mp3_path + "/" + name;
                struct stat stat_buf;
                if (stat(full_path.c_str(), &stat_buf) == 0 && S_ISREG(stat_buf.st_mode))
                {
                    // 去除扩展名‌:ml-citation{ref="1" data="citationList"}
                    size_t dot_pos = name.find_last_of('.');
                    if (dot_pos != std::string::npos && dot_pos > 0)
                    {
                        name = name.substr(0, dot_pos);
                    }
                    file_names.push_back(name);
                }
            }
            closedir(dir);
        }
        return file_names;
    }
}
