#!/usr/bin/env python3
import serial
import time
import sys

def send_fixed_aoa_frame(port_name):
    try:
        # 打开串口
        ser = serial.Serial(
            port=port_name,
            baudrate=115200,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1
        )
        
        print(f"Connected to {port_name}, sending fixed AOA data frame...")
        
        # 你提供的完整帧数据（十六进制）
        fixed_frame = bytes([
            0xFF, 0xFF, 0xFF, 0xFF,  # 4字节连续的FF表示消息开始
            0x00, 0x25,              # 2B表示消息长度
            0x00, 0x0B,              # 2B表示消息流水号
            0x20, 0x01,              # 2B命令码
            0x01, 0x00,              # 2B协议版本目前固定0x0100
            0x00, 0x00, 0xAA, 0xA2,  # 4B基站ID
            0x00, 0x00, 0xAA, 0xA1,  # 4B标签ID
            0x00, 0x00, 0x00, 0x64,  # 4B标签与基站之间的距离
            0x00, 0x1E,              # 2B标签与基站方位角
            0x00, 0x00,              # 2B标签与基站间仰角
            0x12, 0x34,              # 2B标签的状态
            0x00, 0x0B,              # 2B测距序号
            0x00, 0x00, 0x00, 0x00,  # 4B预留
            0x5A         # 1B该字节前所有字节的异或校验
        ])
        
        # 在帧末尾添加换行符
        frame_with_newline = fixed_frame + b'\n'
        
        frame_count = 1
        print("Starting to send fixed AOA data frames... Press Ctrl+C to stop")
        print("Frame format: FF FF FF FF 00 25 00 0B 20 01 01 00 00 00 00 00 AA A2 00 00 AA A1 00 00 00 19 00 12 FF CA 12 34 00 0B 00 00 00 00 1E")
        print("-" * 100)
        
        while True:
            # 发送数据帧（带换行符）
            ser.write(frame_with_newline)
            
            # 打印发送的信息
            hex_str = ' '.join(f'{b:02X}' for b in fixed_frame)
            print(f"Frame #{frame_count}:")
            print(f"  Raw: {hex_str} 0A")  # 0A是换行符的十六进制
            print(f"  Total length: {len(frame_with_newline)} bytes (37 + 1 newline)")
            print(f"  Checksum byte: 0x1E (last byte before newline)")
            print("-" * 100)
            
            frame_count += 1
            time.sleep(1)  # 每秒发送一帧
                
    except KeyboardInterrupt:
        print("\nStopping sender...")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Serial port closed")

def verify_frame_structure():
    """验证帧结构"""
    print("Frame structure verification:")
    print("=" * 80)
    
    frame = bytes([
        0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x25, 0x00, 0x0B,
        0x20, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
        0xAA, 0xA2, 0x00, 0x00, 0xAA, 0xA1, 0x00, 0x00,
        0x00, 0x19, 0x00, 0x12, 0xFF, 0xCA, 0x12, 0x34,
        0x00, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x1E
    ])
    
    # 解析帧结构
    print("Frame breakdown:")
    print(f"Header (4B): {' '.join(f'{b:02X}' for b in frame[0:4])}")
    print(f"Length (2B): {' '.join(f'{b:02X}' for b in frame[4:6])}")
    print(f"Sequence (2B): {' '.join(f'{b:02X}' for b in frame[6:8])}")
    print(f"Command (2B): {' '.join(f'{b:02X}' for b in frame[8:10])}")
    print(f"Version (2B): {' '.join(f'{b:02X}' for b in frame[10:12])}")
    print(f"Base ID (4B): {' '.join(f'{b:02X}' for b in frame[12:16])}")
    print(f"Tag ID (4B): {' '.join(f'{b:02X}' for b in frame[16:20])}")
    print(f"Distance (4B): {' '.join(f'{b:02X}' for b in frame[20:24])}")
    print(f"Azimuth (2B): {' '.join(f'{b:02X}' for b in frame[24:26])}")
    print(f"Elevation (2B): {' '.join(f'{b:02X}' for b in frame[26:28])}")
    print(f"Status (2B): {' '.join(f'{b:02X}' for b in frame[28:30])}")
    print(f"RangingSeq (2B): {' '.join(f'{b:02X}' for b in frame[30:32])}")
    print(f"Reserved (4B): {' '.join(f'{b:02X}' for b in frame[32:36])}")
    print(f"Checksum (1B): {frame[36]:02X}")
    print(f"Total length: {len(frame)} bytes")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        verify_frame_structure()
    else:
        port = "/dev/ttyUSB1"
        if len(sys.argv) > 1 and sys.argv[1] != "verify":
            port = sys.argv[1]
        
        print("Fixed AOA Data Frame Sender")
        print("=" * 80)
        send_fixed_aoa_frame(port)