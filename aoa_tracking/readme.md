功能包试图根据aoa模块的数据、云迹底盘的数据，计算目标相对云迹底盘在地图上的坐标，从而计算目标在地图上的坐标，让底盘移动跟踪目标；
1. 项目运行命令： ros2 run aoa_tracking aoa_tracking_node
2. 云迹底盘数据发布： ros2 launch cloud_water_chassis_node cloud_water_chassis_node.launch.py
3.      
    开启模拟串口命令：sudo socat -d -d pty,raw,echo=0,link=/dev/ttyUSB0 pty,raw,echo=0,link=/dev/ttyUSB1
    串口测试数据发布： python3 send_test.py
若是出现串口数据无法发送，说明共享内存已满，清除现有的共享内存资源：
    # 清理可能残留的共享内存段
    sudo rm -f /dev/shm/*
    sudo ipcs -m | awk '$6==0 {print $2}' | xargs -I {} sudo ipcrm -m {}

    # 或者重启共享内存服务
    sudo service rpcbind restart
    sudo service nfs-common restart
目前效果尚不可知，具体效果还需上机验证，改一下串口，测试时小心

