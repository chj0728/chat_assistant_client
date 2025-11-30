#ifndef EU_PLANET_H
#define EU_PLANET_H

#ifdef __cplusplus
extern "C"{
#endif

#ifndef EXTERNFUNC
#ifdef WIN32
#define EXTERNFUNC __declspec(dllexport)
#else
#define EXTERNFUNC
#endif
#endif

#define PLANET_SUCCESS                 (0)     /**< 执行成功 */
#define PLANET_FAILED_ERRORDEVIECTYPE  (1)     /**< 执行失败，不支持的设备类型 */
#define PLANET_FAILED_DEVICEDISABLED   (2)     /**< 执行失败，设备不存在 */
#define PLANET_FAILED_SETFAILED        (3)     /**< 执行失败，写入控制器数据失败 */
#define PLANET_FAILED_MAXBYTESLIMIT    (4)     /**< 执行失败，发送的字节数超出限制 */
#define PLANET_FAILED_NORECEIVE        (5)     /**< 执行失败，没有接收到回应数据 */
#define PLANET_FAILED_UNKNOW           (100)   /**< 执行失败，未知错误 */

/*!
    设备类型
*/
enum planet_DeviceType
{
    planet_DeviceType_USBCAN2 = 4,             /**< 创芯USB转CAN设备 */
    planet_DeviceType_Canable = 11             /**< 意优canable设备 */
};

/*!
    波特率
*/
enum planet_Baudrate
{
    planet_Baudrate_500 = 500,     /**< 波特率500 */
    planet_Baudrate_1000 = 1000    /**< 波特率1000 */
};

/*!
    发送数据回调函数
    \param id 电机id
    \param data can数据
    \param size 数据长度
*/
typedef void (*planet_SendCallFunc)(int id, const unsigned char *data, int size);

/*!
    接收数据回调函数
    \param id 电机id
    \param data can数据
    \param size 数据长度
*/
typedef void (*planet_ReceiveCallFunc)(int id, const unsigned char *data, int size);

/*!
    设置发送数据回调函数，可以通过该函数捕获实际发送的can数据
    \param callFunc 回调函数地址
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setSendCallFunction(planet_SendCallFunc callFunc);

/*!
    设置接收数据回调函数，可以通过该函数捕获实际接收的can数据
    \param callFunc 回调函数地址
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setReceiveCallFunction(planet_ReceiveCallFunc callFunc);

/*!
    初始化dll，调用其他函数前，必须先调用该函数进行初始化，初始化成功后设备自动打开
    \param devType 设备类型
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param channel 通道，该参数只针对创芯设备生效，设置0或1
    \param baudrate 波特率
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_initDLL(planet_DeviceType devType,int devIndex,int channel,planet_Baudrate baudrate);

/*!
    关闭设备，释放资源，成功初始化设备后，需要在程序结束时调用该函数
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_freeDLL(int devIndex);

/*!
    获得电机心跳状态
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param heartbeat 存放读取的心跳状态
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getHeartbeat(int devIndex, int id, bool *heartbeat, int timeOut = 100);

/*!
    获得电机序列号
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param serialNum 存放读取的电机序列号
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getSerialNumber(int devIndex, int id, unsigned *serialNum, int timeOut = 100);

/*!
    获得硬件版本号
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param hdVersion 存放读取的硬件版本号
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getHardwareVersion(int devIndex, int id, unsigned *hdVersion, int timeOut = 100);

/*!
    获得电机固件版本号
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param fmVersion 存放读取的固件版本号
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getFirmwareVersion(int devIndex, int id, unsigned *fmVersion, int timeOut = 100);

/*!
    获得电机电流值（q值）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param current 存放读取的电流值（q值）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getCurrent(int devIndex, int id, float *current, int timeOut = 100);

/*!
    获得电机速度（rpm）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param velocity 存放读取的电机速度（rpm）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getVelocity(int devIndex, int id, float *velocity, int timeOut = 100);

/*!
    获得电机位置（°）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param position 存放读取的电机位置（°）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getPosition(int devIndex, int id, float *position, int timeOut = 100);

/*!
    获得目标电流值（q值）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param current 存放读取的目标电流值（q值）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getTargetCurrent(int devIndex, int id, float *current, int timeOut = 2);

/*!
    设置目标电流值（q值）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param current 目标电流值（q值）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setTargetCurrent(int devIndex, int id, float current, int timeOut = 100);

/*!
    获得电机目标速度（rpm）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param velocity 存放读取的电机目标速度（rpm）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getTargetVelocity(int devIndex, int id, float *velocity, int timeOut = 100);

/*!
    设置电机目标速度（rpm）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param velocity 电机目标速度（rpm）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setTargetVelocity(int devIndex, int id, float velocity, int timeOut = 100);

/*!
    获得电机目标位置（°）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param position 存放读取的电机目标位置（°）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getTargetPosition(int devIndex, int id, float *position, int timeOut = 100);

/*!
    设置电机目标位置（°），该函数不适用于位置模式，位置模式下设置电机目标位置 参见:quick_setTargetPosition
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param position 电机目标位置（°）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setTargetPosition(int devIndex, int id, float position, int timeOut = 100);

/*!
    设置电机目标位置（°），该函数用于位置模式，实现快写，无需等待控制器返回确认，可以快速连续设置，实现轨迹规划
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param position 电机目标位置（°）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_quick_setTargetPosition(int devIndex, int id, float position);

/*!
    获得电机目标加速度（rpm/s）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param acc 存放读取的电机目标加速度（rpm/s）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getTargetAcceleration(int devIndex, int id, float *acc, int timeOut = 100);

/*!
    设置电机目标加速度（rpm/s）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param acc 电机目标加速度(rpm/s)
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setTargetAcceleration(int devIndex, int id, float acc, int timeOut = 100);

/*!
    获得电机目标减速度（rpm/s）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param dec 存放读取的电机目标减速度（rpm/s）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getTargetDeceleration(int devIndex, int id, float *dec, int timeOut = 100);


/*!
    设置电机目标减速度（rpm/s）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param dec 电机目标减速度（rpm/s）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setTargetDeceleration(int devIndex, int id, float dec, int timeOut = 100);

/*!
    获得电机控制模式
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param mode 存放读取的电机控制模式,模式如下:
        1:	轮廓位置控制模式
        3:	速度模式
        4:	电流模式
        5:	位置模式
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getMode(int devIndex, int id, int *mode, int timeOut = 100);

/*!
    设置电机控制模式
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param mode 电机模式，模式如下:
        1:	轮廓位置控制模式
        3:	速度模式
        4:	电流模式
        5:	位置模式
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setMode(int devIndex, int id, int mode, int timeOut = 100);

/*!
    获得电机使能状态
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param enable 存放读取的电机使能状态
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getEnabled(int devIndex, int id, bool *enable, int timeOut = 100);

/*!
    设置电机使能状态
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param enable 电机使能状态
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setEnabled(int devIndex, int id, bool enable, int timeOut = 100);

/*!
    获得电机停止状态
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param state 存放读取的电机停止状态
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getStopRunState(int devIndex, int id, bool *state, int timeOut = 100);

/*!
    设置电机停止状态
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param state 电机停止状态
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setStopRunState(int devIndex, int id, bool state, int timeOut = 100);

/*!
    获得电机的警告
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param alert 存放读取的电机警告
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getAlert(int devIndex, int id, int *alert, int timeOut = 100);

/*!
    获得电机的电子齿轮比
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param ratio 存放读取的电机电子齿轮比
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getElectronicGearRatio(int devIndex, int id, float *ratio, int timeOut = 100);

/*!
    获得电机的电压（V）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param voltage 存放读取的电机电压（V）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getVoltage(int devIndex, int id, float *voltage, int timeOut = 100);

/*!
    获得电机的保护电压（V）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param voltage 存放读取的电机保护电压（V）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getProtectedVoltage(int devIndex, int id, float *voltage, int timeOut = 100);

/*!
    设置电机的保护电压（V）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param voltage 电机保护电压（V）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setProtectedVoltage(int devIndex, int id, float voltage, int timeOut = 100);

/*!
    获得电机的温度（℃）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param tem 存放读取的电机温度（℃）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getTemperature(int devIndex, int id, float *tem, int timeOut = 100);

/*!
    获得电机的保护温度（℃）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param protectedTem 存放读取的电机保护温度（℃）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getProtectedTemperature(int devIndex, int id, float *protectedTem, int timeOut = 100);

/*!
    设置电机保护温度（℃）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param tem 保护温度（℃）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setProtectedTemperature(int devIndex, int id, float tem, int timeOut = 100);

/*!
    获得电机恢复温度（℃）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param recoveryTem 存放读取的电机恢复温度（℃）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getRecoveryTemperature(int devIndex, int id, float *recoveryTem, int timeOut = 100);

/*!
    设置电机恢复温度（℃）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param tem 存放读取的电机恢复温度（℃）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setRecoveryTemperature(int devIndex, int id, float tem, int timeOut = 100);

/*!
    获得电流环p值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param p 存放读取的电流环p值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getPOfCurrentLoop(int devIndex, int id, unsigned *p, int timeOut = 100);

/*!
    设置电流环p值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param 电流环p值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setPOfCurrentLoop(int devIndex, int id, unsigned p, int timeOut = 100);

/*!
    获得电流环i值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param i 存放读取的电流环i值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getIOfCurrentLoop(int devIndex, int id, unsigned *i, int timeOut = 100);

/*!
    设置电流环i值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param i 存放读取的电流环i值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setIOfCurrentLoop(int devIndex, int id, unsigned i, int timeOut = 100);

/*!
    获得速度环p值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param p 存放读取的速度环p值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getPOfVelocityLoop(int devIndex, int id, unsigned *p, int timeOut = 100);

/*!
    设置速度环p值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param p 速度环p值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setPOfVelocityLoop(int devIndex, int id, unsigned p, int timeOut = 100);

/*!
    获得速度环i值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param i 存放读取的速度环i值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getIOfVelocityLoop(int devIndex, int id, unsigned *i, int timeOut = 100);

/*!
    设置速度环i值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param i 速度环i值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setIOfVelocityLoop(int devIndex, int id, unsigned i, int timeOut = 100);

/*!
    获得位置环p值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param p 存放读取的位置环p值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getPOfPositionLoop(int devIndex, int id, unsigned *p, int timeOut = 100);

/*!
    设置位置环p值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param p 位置环p值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setPOfPositionLoop(int devIndex, int id, unsigned p, int timeOut = 100);

/*!
    获得位置环i值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param i 存放读取的位置环i值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getIOfPositionLoop(int devIndex, int id, unsigned *i, int timeOut = 100);

/*!
    设置位置环i值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param i 位置环i值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setIOfPositionLoop(int devIndex, int id, unsigned i, int timeOut = 100);

/*!
    获得力矩环积分限制
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param limit 存放读取的积分限制
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getIntegralLimit(int devIndex, int id, float *limit, int timeOut = 100);

/*!
    设置力矩环积分限制
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param limit 积分限制
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setIntegralLimit(int devIndex, int id, float limit, int timeOut = 100);

/*!
    获得电机最大电流值（q值）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param current 存放读取的电机最大电流值（q值）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getMaxCurrent(int devIndex, int id, float *current, int timeOut = 100);

/*!
    设置电机最大电流值（q值）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param current 最大电流值（q值）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setMaxCurrent(int devIndex, int id, float current, int timeOut = 100);

/*!
    获得电机最大速度值（rpm）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param current 存放读取的电机最大速度值（rpm）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getMaxVelocity(int devIndex, int id, float *velocity, int timeOut = 100);

/*!
    设置电机最大速度值（rpm）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param velocity 最大速度值（rpm）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setMaxVelocity(int devIndex, int id, float velocity, int timeOut = 100);

/*!
    获得速度梯形曲线的最大速度（rpm）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param velocity 存放读取的速度梯形曲线最大速度（rpm）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getMaxVelocityOfVelocityLadderCurve(int devIndex, int id, float *velocity, int timeOut = 100);

/*!
    设置速度梯形曲线的最大速度（rpm）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param velocity 速度梯形曲线的最大速度（rpm）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setMaxVelocityOfVelocityLadderCurve(int devIndex, int id, float velocity, int timeOut = 100);

/*!
    获得速度梯形曲线的最大加速度（rpm/s）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param acc 存放读取的速度梯形曲线的最大加速度（rpm/s）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getMaxAccelerationOfVelocityLadderCurve(int devIndex, int id, float *acc, int timeOut = 100);

/*!
    设置速度梯形曲线的最大加速度（rpm/s）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param acc 最大加速度（rpm/s）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setMaxAccelerationOfVelocityLadderCurve(int devIndex, int id, float acc, int timeOut = 100);

/*!
    获得速度梯形曲线的最大减速度（rpm/s）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param dec 存放读取的速度梯形曲线的最大减速度（rpm/s）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getMaxDecelerationOfVelocityLadderCurve(int devIndex, int id, float *dec, int timeOut = 100);

/*!
    设置速度梯形曲线的最大减速度（rpm/s）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param dec 最大减速度（rpm/s）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setMaxDecelerationOfVelocityLadderCurve(int devIndex, int id, float dec, int timeOut = 100);

/*!
    获得位置梯形曲线的最大速度（rpm）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param dec 存放读取的位置梯形曲线最大速度（rpm）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getMaxVelocityOfPositionLadderCurve(int devIndex, int id, float *dec, int timeOut = 100);

/*!
    设置位置梯形曲线的最大速度（rpm）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param velocity 最大速度（rpm）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setMaxVelocityOfPositionLadderCurve(int devIndex, int id, float velocity, int timeOut = 100);

/*!
    获得位置梯形曲线的最大加速度（rpm/s）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param acc 存放读取的位置梯形曲线的最大加速度（rpm/s）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getMaxAccelerationOfPositionLadderCurve(int devIndex, int id, float *acc, int timeOut = 100);

/*!
    设置位置梯形曲线的最大加速度（rpm/s）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param acc 最大加速度（rpm/s）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setMaxAccelerationOfPositionLadderCurve(int devIndex, int id, float acc, int timeOut = 100);

/*!
    获得位置梯形曲线的最大减速度（rpm/s）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param dec 存放读取的位置梯形曲线最大减速度（rpm/s）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getMaxDecelerationOfPositionLadderCurve(int devIndex, int id, float *dec, int timeOut = 100);

/*!
    设置位置梯形曲线的最大减速度（rpm/s）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param dec 最大减速度（rpm/s）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setMaxDecelerationOfPositionLadderCurve(int devIndex, int id, float dec, int timeOut = 100);

/*!
    获得电机限位状态
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param state 存放读取的限位状态
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getLimitState(int devIndex, int id, bool *state, int timeOut = 100);

/*!
    设置电机的限位状态
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param state 电机限位状态
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setLimitState(int devIndex, int id, bool state, int timeOut = 100);

/*!
    获得电机最大位置（°）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param position 存放读取的电机最大位置（°）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getMaxPosition(int devIndex, int id, float *position, int timeOut = 100);

/*!
    设置电机最大位置（°）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param position 最大位置（°）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setMaxPosition(int devIndex, int id, float position, int timeOut = 100);

/*!
    获得电机最小位置（°）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param position 存放读取的电机最小位置（°）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getMinPosition(int devIndex, int id, float *position, int timeOut = 100);

/*!
    设置电机最小位置（°）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param position 最小位置（°）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setMinPosition(int devIndex, int id, float position, int timeOut = 100);

/*!
    获得电机的位置偏置（原始数据，没有进行q24转换）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param offset 存放读取的电机的位置偏置（原始数据，没有进行q24转换
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getOriginPositionOffset(int devIndex, int id, float *offset, int timeOut = 100);

/*!
    获得电机的位置偏置（°）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param offset 存放读取的电机的位置偏置（°）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getPositionOffset(int devIndex, int id, float *offset, int timeOut = 100);

/*!
    设置电机的位置偏置（°）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param position 电机的位置偏置（°）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setPositionOffset(int devIndex, int id, float position, int timeOut = 100);

/*!
    获得上电时刻单圈位置范围值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param range 存放读取的单圈范围值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getSingleLapPositionRange(int devIndex, int id, int *range, int timeOut = 100);

/*!
    设置电机上电时刻的单圈位置范围值
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param range 单圈范围值
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setSingleLapPositionRange(int devIndex, int id, int range, int timeOut = 100);

/*!
    获得电机的波特率
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param baudrate 存放读取的电机波特率
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_getCanBaudrate(int devIndex, int id, int *baudrate, int timeOut = 100);

/*!
    设置电机的波特率
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param baudrate 电机波特率
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setCanBaudrate(int devIndex, int id, int baudrate, int timeOut = 100);

/*!
    设置电机的id（范围是1~255）
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 原先电机id
    \param id 新的电机id
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setID(int devIndex, int id, int newId, int timeOut = 100);

/*!
    保存控制器参数，当前修改的控制器参数，重新上电后仍然生效
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_saveParas(int devIndex, int id, int timeOut = 100);

/*!
    发送can数据，数据长度不能超过8
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param sendData 将要发送的can数据
    \param sendLength can数据长度（不超过8位）
    \param timeOut 函数执行后，等待timeOut毫秒来接收执行结果
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_writeData(int devIndex, int id, unsigned char *sendData, int sendLength);

/*!
    设置手指位置
    \param devIndex 设备索引，第一个设备设置为0，第二个设备设置为1，以此类推
    \param id 电机id
    \param subId 手指id
    \param position 手指目标位置
    \param velocity 手指速度
    \return 执行成功返回CAN_SUCCESS，失败返回其他
*/
EXTERNFUNC int planet_setFingerPosition(int devIndex, int id, int subId, unsigned position, unsigned velocity);
#ifdef __cplusplus
}
#endif

#endif // EU_PLANET_H
