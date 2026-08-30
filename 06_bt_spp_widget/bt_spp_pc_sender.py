# 阶段 6：经典蓝牙串口数据发射服务 (基于 PySerial)
# 优点：100% 绕开 Windows WinRT 损坏的 BLE 驱动，走系统标准蓝牙虚拟串口，极度稳定

import sys
import time
import json
import re
import psutil
import winreg
import serial
import serial.tools.list_ports

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def read_aida64_sensors():
    """从 Windows 注册表读取 AIDA64 的 CPU/GPU 温度与功耗"""
    cpu_temp = None
    cpu_power = None
    gpu_temp = None
    gpu_power = None
    gpu_usage = None

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\FinalWire\AIDA64\SensorValues")
        num_values = winreg.QueryInfoKey(key)[1]

        all_items = []
        for i in range(num_values):
            name, val, _ = winreg.EnumValue(key, i)
            all_items.append((str(name).upper(), str(val)))
        winreg.CloseKey(key)

        def first_number(val_str, lo, hi):
            m = re.search(r"[-+]?\d+\.?\d*", val_str)
            if m:
                num = float(m.group())
                if lo <= num <= hi:
                    return num
            return None

        # 1. CPU Package 温度
        for name_upper, val_str in all_items:
            if any(k in name_upper for k in ["TCPUPKG", "CPU PACKAGE", "CPU 封装", "PACKAGE"]):
                num = first_number(val_str, 15, 115)
                if num is not None:
                    cpu_temp = num
                    break
        if cpu_temp is None:
            for name_upper, val_str in all_items:
                if name_upper.startswith("VALUE.TCPU"):
                    num = first_number(val_str, 15, 115)
                    if num is not None:
                        cpu_temp = num
                        break

        # 2. CPU Package 功耗 (W)
        for name_upper, val_str in all_items:
            if any(k in name_upper for k in ["PCPUPKG", "CPU PACKAGE POWER", "CPU 封装功耗", "PACKAGE POWER"]):
                num = first_number(val_str, 0, 500)
                if num is not None:
                    cpu_power = num
                    break

        # 3. GPU 温度: 优先精确匹配 TGPU1/TGPU2 这类温度字段
        #    (避免误抓 SGPU1USEDDYMEM 显存占用、TGPU1MEM 显存温度等干扰项)
        for name_upper, val_str in all_items:
            if re.match(r"^VALUE\.TGPU\d+$", name_upper):
                num = first_number(val_str, 15, 115)
                if num is not None:
                    gpu_temp = num
                    break
        if gpu_temp is None:  # 兜底: 关键词模糊匹配 (排除内存/频率/总线类字段)
            for name_upper, val_str in all_items:
                if any(k in name_upper for k in ["图形处理器", "TGPU", "GPU", "显卡"]):
                    if not any(b in name_upper for b in ["MEM", "CLK", "USED", "BUSTYP", "HOTSPOT", "12VHPWR"]):
                        num = first_number(val_str, 15, 115)
                        if num is not None:
                            gpu_temp = num
                            break

        # 4. GPU 功耗: 优先精确匹配 PGPU1/PGPU2 这类功耗字段
        #    (避免误抓 PGPU112VHPWR 供电接口功耗)
        for name_upper, val_str in all_items:
            if re.match(r"^VALUE\.PGPU\d+$", name_upper):
                num = first_number(val_str, 0, 800)
                if num is not None:
                    gpu_power = num
                    break
        if gpu_power is None:  # 兜底: Intel 核显 GT CORES 命名
            for name_upper, val_str in all_items:
                if any(k in name_upper for k in ["GT CORES", "GT CORE", "CPU GT", "PGT"]):
                    num = first_number(val_str, 0, 800)
                    if num is not None:
                        gpu_power = num
                        break

        # 5. GPU 占用率 (AIDA64 部分机器不导出此字段, 读不到则返回 None -> 副屏显示空白)
        for name_upper, val_str in all_items:
            if any(k in name_upper for k in ["GPU UTILIZATION", "GPU 使用率", "GPU 负载", "UGPU", "GPU1UTIL", "GPUUTIL"]):
                num = first_number(val_str, 0, 100)
                if num is not None:
                    gpu_usage = int(num)
                    break
    except Exception:
        pass

    return {
        "cpu_temp": cpu_temp,
        "cpu_pwr": cpu_power,
        "gpu_temp": gpu_temp,
        "gpu_pwr": gpu_power,
        "gpu_usage": gpu_usage
    }

def get_stats_payload():
    cpu = int(psutil.cpu_percent(interval=None))
    mem = int(psutil.virtual_memory().percent)
    sensors = read_aida64_sensors()
    
    data = {
        "cpu": cpu,
        "mem": mem,
        "cpu_temp": sensors["cpu_temp"] or 0,
        "cpu_pwr": sensors["cpu_pwr"] or 0,
        "gpu_temp": sensors["gpu_temp"] or 0,
        "gpu_pwr": sensors["gpu_pwr"] or 0,
        "gpu_usage": sensors["gpu_usage"] if sensors["gpu_usage"] is not None else -1,
        "time": time.strftime("%H:%M:%S")
    }
    return json.dumps(data, separators=(',', ':')) + "\n"

def main():
    print("=" * 60)
    print("  ESP32 桌面副屏 - 经典蓝牙串口发射器 (SPP 稳健版)")
    print("=" * 60)
    
    # 查找可用蓝牙串口
    ports = list(serial.tools.list_ports.comports())
    bt_ports = [p.device for p in ports if "Bluetooth" in p.description or "BTHENUM" in p.hwid or "蓝牙" in p.description]
    
    print("\n当前系统检测到的所有串口:")
    for p in ports:
        print(f"  -> {p.device}: {p.description}")

    target_port = None
    if bt_ports:
        target_port = bt_ports[0]
        print(f"\n[提示] 自动选择蓝牙串口: {target_port}")
    else:
        print("\n[提示] 请先在 Windows 蓝牙设置中配对 [ESP32-Dashboard]")
        target_port = input("请输入 ESP32 对应的蓝牙 COM 口 (如 COM5): ").strip().upper()

    if not target_port:
        print("未指定端口，程序退出。")
        return

    print(f"\n[连接] 正在打开蓝牙串口 {target_port} ...")
    while True:
        try:
            with serial.Serial(target_port, 115200, timeout=1) as ser:
                print(f"[成功] 蓝牙串口 {target_port} 已连接！开始以 0.3s 推流...\n")
                while True:
                    payload = get_stats_payload()
                    ser.write(payload.encode('utf-8'))
                    time.sleep(0.3)
        except Exception as e:
            print(f"[警告] 连接中断: {e}，2 秒后重试...")
            time.sleep(2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[退出] 已退出服务。")
