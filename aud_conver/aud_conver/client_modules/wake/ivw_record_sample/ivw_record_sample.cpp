#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <atomic>
#include <signal.h>
#include <fcntl.h>
#include <termios.h>
#include "speech_recognizer.h"
#include "aikit_biz_api.h"
#include "aikit_constant.h"
#include "aikit_biz_config.h"

using namespace std;
using namespace AIKIT;

static const char *ABILITY = "e867a88f2";

// 全局退出标志
std::atomic<bool> exit_flag(false);

// 当有识别结果时的回调
extern "C" void OnOutput(AIKIT_HANDLE* handle, const AIKIT_OutputData* output) {
    // 当有结果输出时被调用
    // 1) 打印一些基本信息
    // 2) 将结果写入 ivw_result.txt
    printf("OnOutput abilityID :%s\n", handle->abilityID);
    printf("OnOutput key:%s\n", output->node->key);
    printf("OnOutput value:%s\n", (char*)output->node->value);

    if (output->node != nullptr && output->node->value != nullptr) {
        // FILE *fin = fopen("ivw_result.txt", "ab");
        // if (fin == nullptr) {
        //     printf("文件打开失败！\n");
        //     return;
        // }
        // fwrite(output->node->value, sizeof(char), output->node->len, fin);
        // fwrite("\n", sizeof(char), 1, fin);
        // fclose(fin);

        // 任何识别结果都设置退出标志
        printf("检测到语音内容，准备退出程序。\n");
        exit_flag.store(true);
    }
}

extern "C" void OnEvent(AIKIT_HANDLE* handle, AIKIT_EVENT eventType, const AIKIT_OutputEvent* eventValue) {
    // 当引擎内部发生事件（如唤醒成功、音频结束等）时被调用
    // 此处简单打印事件类型
    printf("OnEvent:%d\n", eventType);
}

extern "C" void OnError(AIKIT_HANDLE* handle, int32_t err, const char* desc) {
    // 当处理过程出错时被调用
    // 此处简单打印错误码
    printf("OnError:%d\n", err);
}

// 启动语音识别的函数（仅麦克风输入）
extern "C" void demo_mic(int keywordfiles_count) {
    printf("开始录音并监听麦克风输入...\n");
    int errcode;

    struct speech_rec ivw;
    printf("初始化识别器...\n");
    errcode = sr_init(&ivw, keywordfiles_count, SR_MIC);
    if (errcode) {
        printf("语音识别初始化失败\n");
        return;
    }
    errcode = sr_start_listening(&ivw);
    if (errcode) {
        printf("开始监听失败 %d\n", errcode);
        sr_uninit(&ivw);
        return;
    }

    // 设置终端为非缓冲模式和不回显
    struct termios oldt, newt;
    tcgetattr(STDIN_FILENO, &oldt); // 获取当前终端设置
    newt = oldt;
    newt.c_lflag &= ~(ICANON | ECHO); // 禁用缓冲和回显
    tcsetattr(STDIN_FILENO, TCSANOW, &newt);

    // 设置文件描述符为非阻塞
    int flags = fcntl(STDIN_FILENO, F_GETFL, 0);
    fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK);

    while (!exit_flag.load()) // 监控退出标志
    {
        // 检查是否有输入（尽管我们不需要用户输入来停止）
        char buf[1];
        ssize_t bytes = read(STDIN_FILENO, buf, sizeof(buf));
        if (bytes > 0) {
            // 如果接收到任何输入（例如 Ctrl+C），可以选择退出
            printf("检测到输入，准备退出程序。\n");
            exit_flag.store(true);
            break;
        }

        usleep(100000); // 休眠100ms，避免占用过高CPU
    }

    errcode = sr_stop_listening(&ivw);
    if (errcode) {
        printf("停止监听失败 %d\n", errcode);
    }

    sr_uninit(&ivw);

    // 恢复终端设置
    tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
}

// 初始化并启动语音识别引擎的函数
extern "C" void start_speech_recognition(const char* resource_path) {
    // 配置 AIKIT 引擎
    exit_flag.store(false);  // 确保 exit_flag 为 false
    AIKIT_Configurator::builder()
        .app()
            .appID("1098a678")
            .apiSecret("ZmI1Y2NjZjY5ODYzZjExYWIwOTlhNWEy")
            .apiKey("3b2ed90172f1807672b1b28cf8c26828")
            .workDir("./")
        .auth()
            .authType(0)
            .ability(ABILITY);
        

    // 注册回调
    AIKIT_Callbacks cbs = {OnOutput, OnEvent, OnError};
    AIKIT_RegisterAbilityCallback(ABILITY, cbs);

    // 初始化引擎
    int ret = AIKIT_Init();
    if (ret != 0) {
        printf("AIKIT_Init failed:%d\n", ret);
        return;
    }

    //

    // 初始化引擎
    ret = AIKIT_EngineInit(ABILITY, nullptr);
    if (ret != 0) {
        printf("AIKIT_EngineInit failed:%d\n", ret);
        AIKIT_UnInit();  // 确保在失败时卸载 SDK
        return;
    }

    // 加载关键字文件数据
    AIKIT_CustomData customData;
    customData.key = "key_word";
    customData.index = 0;
    customData.from = AIKIT_DATA_PTR_PATH;
    customData.value = (void *)resource_path;  // 关键字文件路径
    customData.len = strlen(resource_path);
    customData.next = nullptr;
    customData.reserved = nullptr;

    printf("AIKIT_LoadData 开始!\n");
    ret = AIKIT_LoadData(ABILITY, &customData);
    printf("AIKIT_LoadData 结束!\n");

    if (ret != 0) {
        printf("加载关键字数据失败\n");
        AIKIT_UnInit();  // 卸载 SDK
        return;
    }

    // 语音识别演示: 识别麦克风音频
    printf("语音识别演示: 识别麦克风音频\n");
    demo_mic(1);  // 使用一个唤醒词

    // 卸载关键字数据
    AIKIT_UnLoadData(ABILITY, "key_word", 0);

    // 卸载引擎和 SDK
    AIKIT_EngineUnInit(ABILITY);
    AIKIT_UnInit();
}