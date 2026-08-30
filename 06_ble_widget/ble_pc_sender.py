# -*- coding: utf-8 -*-
"""
ESP32 华硕笔记本状态信息监控副屏 - 低功耗蓝牙 (BLE) 极速发射服务 (G-Helper 协同版)
特性：
1. 深度对接华硕 G-Helper 体系：直读 ASUS ATKACPI 嵌入式控制器（CPU温度、性能模式）
2. NVIDIA NVML 显卡底层直读：毫秒级采集 GPU 温度、实时功耗 (W)、GPU 占用率
3. Windows Energy Meter RAPL 采集 CPU Package 封装功耗 (W)
4. 多源游戏 FPS 读取：支持 RTSS (RivaTuner) / AIDA64，绝不抢占或冲突 G-Helper 自身的 ETW 会话
5. BLE 极速 GATT 广播推流，自动重连与无感恢复
"""

import asyncio
import ctypes
from ctypes import wintypes, byref, Structure
import json
import mmap
import os
import re
import struct
import sys
import time
import winreg
import psutil
from bleak import BleakScanner, BleakClient

# ==================== Win32 基础接口 ====================
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

# 强制 UTF-8 输出
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# BLE UUID
SERVICE_UUID        = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"


# ==================== 1. 华硕 ASUS ATKACPI 直读 ====================
ATKACPI_DEVICE = r"\\.\ATKACPI"
CONTROL_CODE   = 0x0022240C
DSTS           = 0x53545344
INIT           = 0x54494E49
DEV_CPU_TEMP   = 0x00120094
DEV_PERF_MODE  = 0x00120075

kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p,
                                     wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                     ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
kernel32.DeviceIoControl.restype = wintypes.BOOL

class AsusAcpiReader:
    def __init__(self):
        self.handle = None
        self._init_handle()

    def _init_handle(self):
        try:
            self.handle = kernel32.CreateFileW(
                ATKACPI_DEVICE, 0x80000000 | 0x40000000, 1 | 2, None, 3, 0x80, None)
            if not self.handle or self.handle == ctypes.c_void_p(-1).value:
                self.handle = None
            else:
                buf = struct.pack("<II", INIT, 8) + b"\x00" * 8
                out = ctypes.create_string_buffer(16)
                ret = wintypes.DWORD(0)
                kernel32.DeviceIoControl(self.handle, CONTROL_CODE, buf, len(buf), out, 16, byref(ret), None)
        except Exception:
            self.handle = None

    def device_get(self, device_id):
        if not self.handle:
            return None
        try:
            args = struct.pack("<I", device_id) + b"\x00" * 4
            buf = struct.pack("<II", DSTS, len(args)) + args
            out = ctypes.create_string_buffer(16)
            ret = wintypes.DWORD(0)
            ok = kernel32.DeviceIoControl(self.handle, CONTROL_CODE, buf, len(buf), out, 16, byref(ret), None)
            if ok:
                val = struct.unpack("<i", out.raw[:4])[0] - 65536
                return val
        except Exception:
            pass
        return None

    def get_cpu_temp(self):
        t = self.device_get(DEV_CPU_TEMP)
        if t is not None and 10 <= t <= 120:
            return t
        return None

    def get_mode(self):
        m = self.device_get(DEV_PERF_MODE)
        modes = {0: "BALANCED", 1: "TURBO", 2: "SILENT", 3: "FULL", 4: "MANUAL"}
        if m is not None and m in modes:
            return modes[m]
        try:
            cfg_path = os.path.expandvars(r'%APPDATA%\GHelper\config.json')
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    return modes.get(cfg.get("performance_mode", 0), "BALANCED")
        except Exception:
            pass
        return "BALANCED"


# ==================== 2. NVIDIA NVML 直读 ====================
class nvmlUtilization_t(Structure):
    _fields_ = [('gpu', ctypes.c_uint), ('memory', ctypes.c_uint)]

class GpuReader:
    def __init__(self):
        self.available = False
        try:
            self.nvml = ctypes.CDLL('nvml.dll')
            if self.nvml.nvmlInit_v2() == 0:
                self.handle = ctypes.c_void_p()
                if self.nvml.nvmlDeviceGetHandleByIndex_v2(0, byref(self.handle)) == 0:
                    self.available = True
        except Exception:
            self.available = False

    def read(self):
        if not self.available:
            return None, None, None
        try:
            temp = ctypes.c_uint()
            power = ctypes.c_uint()
            util = nvmlUtilization_t()
            self.nvml.nvmlDeviceGetTemperature(self.handle, 0, byref(temp))
            self.nvml.nvmlDeviceGetPowerUsage(self.handle, byref(power))
            self.nvml.nvmlDeviceGetUtilizationRates(self.handle, byref(util))
            return temp.value, power.value / 1000.0, util.gpu
        except Exception:
            return None, None, None


# ==================== 3. CPU 功耗 (RAPL / PDH) ====================
class CpuPowerReader:
    def __init__(self):
        self.pdh_query = None
        self.pdh_counter = None
        self._init_pdh()

    def _init_pdh(self):
        try:
            import win32pdh
            self.win32pdh = win32pdh
            hq = win32pdh.OpenQuery()
            for inst in ["RAPL_Package0_PKG", "Apu Power", "CPU Power", "Socket Power", "Current Socket Power"]:
                try:
                    path = f"\\Energy Meter({inst})\\Power"
                    hc = win32pdh.AddEnglishCounter(hq, path)
                    self.pdh_query = hq
                    self.pdh_counter = hc
                    win32pdh.CollectQueryData(hq)
                    break
                except Exception:
                    continue
        except Exception:
            self.pdh_query = None

    def read(self):
        if self.pdh_query and self.pdh_counter:
            try:
                self.win32pdh.CollectQueryData(self.pdh_query)
                _, val = self.win32pdh.GetFormattedCounterValue(self.pdh_counter, self.win32pdh.PDH_FMT_DOUBLE)
                if val > 0:
                    if val > 500:
                        return val / 1000.0
                    return val
            except Exception:
                pass
        return None


# ==================== 4. RTSS / AIDA64 FPS 读取 ====================
class FpsMonitor:
    def _read_rtss_fps(self):
        try:
            shm = mmap.mmap(-1, 1024*64, 'Global\\RTSSSharedMemoryV2', access=mmap.ACCESS_READ)
            sig = shm.read(4)
            if sig == b'RTSS':
                shm.seek(32)
                fps = struct.unpack('<I', shm.read(4))[0]
                return fps
        except Exception:
            pass
        return 0

    def get_fps(self):
        return self._read_rtss_fps()


# ==================== 5. AIDA64 注册表兜底读取 ====================
def read_aida64_fallback():
    data = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\FinalWire\AIDA64\SensorValues")
        num = winreg.QueryInfoKey(key)[1]
        items = []
        for i in range(num):
            n, v, _ = winreg.EnumValue(key, i)
            items.append((str(n).upper(), str(v)))
        winreg.CloseKey(key)

        def get_val(keywords, lo, hi):
            for n, v in items:
                if any(k in n for k in keywords):
                    m = re.search(r"[-+]?\d+\.?\d*", v)
                    if m:
                        val = float(m.group())
                        if lo <= val <= hi:
                            return val
            return None

        data["cpu_temp"] = get_val(["TCPUPKG", "CPU PACKAGE", "CPU 封装", "VALUE.TCPU"], 15, 115)
        data["cpu_pwr"]  = get_val(["PCPUPKG", "CPU PACKAGE POWER", "CPU 封装功耗", "PACKAGE POWER"], 0, 500)
        data["gpu_temp"] = get_val(["TGPU1", "VALUE.TGPU", "GPU 温度"], 15, 115)
        data["gpu_pwr"]  = get_val(["PGPU1", "VALUE.PGPU", "GPU 功耗"], 0, 500)
        data["gpu_usage"] = get_val(["GPU UTILIZATION", "GPU 使用率", "GPU 负载", "UGPU"], 0, 100)
        data["fps"] = get_val(["FPS", "VALUE.FPS", "RFPS"], 0, 500)
    except Exception:
        pass
    return data


# ==================== 6. 数据汇聚与 JSON 打包 ====================
acpi_reader = AsusAcpiReader()
gpu_reader = GpuReader()
cpu_power_reader = CpuPowerReader()
fps_monitor = FpsMonitor()

def get_stats_json():
    cpu_percent = int(psutil.cpu_percent(interval=None))
    mem_percent = int(psutil.virtual_memory().percent)

    # 1. 华硕 EC 读 CPU 温度与性能模式
    cpu_temp = acpi_reader.get_cpu_temp()
    mode = acpi_reader.get_mode()

    # 2. NVML 读 GPU
    gpu_temp, gpu_pwr, gpu_usage = gpu_reader.read()

    # 3. CPU 功耗
    cpu_pwr = cpu_power_reader.read()

    # 4. 游戏实时帧率 (FPS)
    fps = fps_monitor.get_fps()

    # 5. AIDA64 兜底补充
    aida = read_aida64_fallback()
    if cpu_temp is None:
        cpu_temp = aida.get("cpu_temp", 0)
    if cpu_pwr is None or cpu_pwr <= 0:
        cpu_pwr = aida.get("cpu_pwr", 0)
    if gpu_temp is None:
        gpu_temp = aida.get("gpu_temp", 0)
    if gpu_pwr is None:
        gpu_pwr = aida.get("gpu_pwr", 0)
    if gpu_usage is None:
        gpu_usage = aida.get("gpu_usage", -1)
    if fps <= 0 and aida.get("fps"):
        fps = int(aida["fps"])

    payload = {
        "fps": int(fps) if fps else 0,
        "cpu": cpu_percent,
        "mem": mem_percent,
        "cpu_temp": int(round(cpu_temp)) if cpu_temp else 0,
        "cpu_pwr": int(round(cpu_pwr)) if cpu_pwr else 0,
        "gpu_temp": int(round(gpu_temp)) if gpu_temp else 0,
        "gpu_pwr": int(round(gpu_pwr)) if gpu_pwr else 0,
        "gpu_usage": int(round(gpu_usage)) if gpu_usage is not None and gpu_usage >= 0 else -1,
        "mode": mode,
        "time": time.strftime("%H:%M:%S")
    }

    return json.dumps(payload, separators=(',', ':'))


# ==================== 7. BLE 发送主循环 ====================
async def run_ble_sender():
    print("=" * 65)
    print("  ESP32 华硕副屏 - BLE 蓝牙极速发射器 (G-Helper 协同版)")
    print("=" * 65)
    print(f"[配置] 华硕 ATKACPI: {'已就绪' if acpi_reader.handle else '未就绪 (请以管理员身份运行)'}")
    print(f"[配置] NVIDIA NVML:  {'已就绪' if gpu_reader.available else '未检测到 NVIDIA 显卡'}")
    print(f"[配置] CPU 功耗引擎: {'已连接 RAPL' if cpu_power_reader.pdh_query else 'AIDA64 兜底'}")
    print(f"[配置] 性能模式:     {acpi_reader.get_mode()}")
    print("=" * 65)

    while True:
        print("\n[搜索] 正在搜索蓝牙副屏 [ESP32-Dashboard]...")
        try:
            device = await BleakScanner.find_device_by_name("ESP32-Dashboard", timeout=6.0)
        except Exception as e:
            print(f"[错误] 蓝牙扫描失败: {e}")
            await asyncio.sleep(3)
            continue

        if not device:
            print("[提示] 未发现设备，请确保 ESP32 已通电并在广播中，3 秒后重试...")
            await asyncio.sleep(3)
            continue

        print(f"[发现] 找到蓝牙副屏！设备地址: {device.address}")
        print("[连接] 正在建立 BLE GATT 连接...")

        try:
            async with BleakClient(device) as client:
                print("[成功] 蓝牙连接成功！开始以 0.3s 极速推流硬件状态...\n")
                while client.is_connected:
                    raw_json = get_stats_json()
                    await client.write_gatt_char(CHARACTERISTIC_UUID, raw_json.encode('utf-8'), response=False)
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
