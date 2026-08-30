# 阶段 6：电脑端 BLE 发送服务 (基于 Bleak)
# 用法：直接运行 python ble_pc_sender.py
# 功能：自动扫描名为 "ESP32-Dashboard" 的低功耗蓝牙设备，建立连接并以 0.3s 周期发送实时电脑状态数据

import asyncio
import json
import time
import re
import psutil
import winreg
from bleak import BleakScanner, BleakClient

# 与 ESP32 端完全一致的 UUID
SERVICE_UUID        = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"

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

def get_stats_json():
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
    # 生成紧凑单行 JSON 字符串
    return json.dumps(data, separators=(',', ':'))

import sys

# 强制标准输出使用 UTF-8 编码，防止 Windows 默认 GBK 终端报错
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

async def run_ble_sender():
    print("=" * 60)
    print("  ESP32 桌面副屏 - 低功耗蓝牙 (BLE) 极速发射器")
    print("=" * 60)
    
    while True:
        print("\n[搜索] 正在搜索附近的蓝牙副屏设备 [ESP32-Dashboard]...")
        try:
            device = await BleakScanner.find_device_by_name("ESP32-Dashboard", timeout=6.0)
        except Exception as e:
            print(f"[错误] 蓝牙扫描失败: {e}")
            print("请检查电脑蓝牙是否已开启！3 秒后重试...")
            await asyncio.sleep(3)
            continue
        
        if not device:
            print("[提示] 未发现设备，请确保 ESP32 已烧录并在通电广播中，3 秒后重试...")
            await asyncio.sleep(3)
            continue

        print(f"[发现] 找到蓝牙副屏！设备地址: {device.address}")
        print("[连接] 正在建立 BLE GATT 连接...")

        try:
            async with BleakClient(device) as client:
                print("[成功] 蓝牙连接成功！开始以 0.3s 极速推流硬件状态...\n")
                
                while client.is_connected:
                    payload = get_stats_json()
                    await client.write_gatt_char(CHARACTERISTIC_UUID, payload.encode('utf-8'), response=False)
                    await asyncio.sleep(0.3)
                    
        except Exception as e:
            print(f"[警告] 蓝牙连接中断: {e}，准备重新自动连接...")
            await asyncio.sleep(2)

if __name__ == "__main__":
    try:
        asyncio.run(run_ble_sender())
    except KeyboardInterrupt:
        print("\n[退出] 已退出 BLE 数据发射服务。")
    except Exception as e:
        print(f"\n[异常崩溃] 错误信息: {e}")
        input("\n按回车键退出...")
