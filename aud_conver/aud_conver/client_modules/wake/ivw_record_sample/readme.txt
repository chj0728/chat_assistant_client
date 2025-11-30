
g++ -std=c++11 -g -Wall -I/home/fish/realtime_conversation/src/client_modules/wake/include -fPIC -shared linuxrec.o ivw_record_sample.o speech_recognizer.o wakeup.o -o /home/fish/realtime_conversation/src/client_modules/wake/bin/wakeup.so -L/home/fish/realtime_conversation/src/client_modules/wake/libs -laikit -lrt -ldl -lpthread -lasound
export LD_LIBRARY_PATH=/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/client_modules/wake/libs:$LD_LIBRARY_PATH
export LD_LIBRARY_PATH=/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/client_modules/wake/bin:$LD_LIBRARY_PATH

echo "export DASHSCOPE_API_KEY='sk-1ee75c04bb3c4cfbb5a7f624b8cbfbb2'" >> ~/.bashrc

1、进入sample/ivw_record_sample目录，修改ivw_record_sample.cpp，将appid、appKey、appSecret写入demo；

3、设置环境变量：# export LD_LIBRARY_PATH=../libs:$LD_LIBRARY_PATH

5、执行  make 编译文件

