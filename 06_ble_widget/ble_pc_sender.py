# -*- coding: utf-8 -*-
"""
ESP32 华硕笔记本状态信息监控副屏 - 低功耗蓝牙 (BLE) 极速发射服务
特性：
1. 深度对接华硕 G-Helper 体系：直读 ASUS ATKACPI 嵌入式控制器（CPU温度、风扇转速、性能模式）
2. NVIDIA NVML 显卡底层直读：毫秒级采集 GPU 温度、实时功耗 (W)、GPU 占用率
3. Windows Energy Meter RAPL / AIDA64 双轨采集 CPU Package 封装功耗 (W)
4. 游戏实时帧率 (FPS) 引擎：Windows ETW (Microsoft-Windows-DxgKrnl) + RTSS 共享内存 + AIDA64 多重采集
5. BLE 极速 GATT 广播推流，自动重连与无感恢复
"""

import asyncio
import ctypes
from ctypes import wintypes, byref, Structure, POINTER
import json
import mmap
import os
import re
import struct
import sys
import threading
import time
import winreg
import psutil
from bleak import BleakScanner, BleakClient

# ==================== Win32 基础接口 ====================
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

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
DEV_GPU_TEMP   = 0x00120097
DEV_PERF_MODE  = 0x00120075
DEV_CPU_FAN    = 0x00110013
DEV_GPU_FAN    = 0x00110014

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
                # INIT 调用
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

    def get_cpu_fan(self):
        f = self.device_get(DEV_CPU_FAN)
        if f is not None:
            raw = f & 0xFFFF
            if raw > 0 and raw < 150:
                return raw * 100
        return None

    def get_gpu_fan(self):
        f = self.device_get(DEV_GPU_FAN)
        if f is not None:
            raw = f & 0xFFFF
            if raw > 0 and raw < 150:
                return raw * 100
        return None

    def get_mode(self):
        m = self.device_get(DEV_PERF_MODE)
        modes = {0: "BALANCED", 1: "TURBO", 2: "SILENT", 3: "FULL", 4: "MANUAL"}
        if m is not None and m in modes:
            return modes[m]
        # 兜底从 G-Helper 配置文件读取
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


# ==================== 3. CPU 功耗 (RAPL / PDH / AIDA64) ====================
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
            # 常见 RAPL 路径
            for path in [
                r"\Energy Meter\Power",
                r"\Energy Meter(*)\Power",
                r"\能量计\功率",
                r"\Energy Meter\Power(Apu Power)",
                r"\Energy Meter\Power(RAPL_Package0_PKG)"
            ]:
                try:
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
                    return float(val)
            except Exception:
                pass
        return None


# ==================== 4. 游戏实时帧率 (FPS) 引擎 ====================
# 支持: 1. Windows ETW (DxgKrnl Present)  2. RTSS 共享内存  3. AIDA64 注册表

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8)
    ]
    def __init__(self, guid_str):
        super().__init__()
        import uuid
        u = uuid.UUID(guid_str)
        self.Data1 = u.time_low
        self.Data2 = u.time_mid
        self.Data3 = u.time_hi_version
        for i, b in enumerate(u.bytes[8:]):
            self.Data4[i] = b

class WNODE_HEADER(ctypes.Structure):
    _fields_ = [
        ("BufferSize", wintypes.ULONG),
        ("ProviderId", wintypes.ULONG),
        ("HistoricalContext", ctypes.c_ulonglong),
        ("TimeStamp", ctypes.c_ulonglong),
        ("Guid", GUID),
        ("ClientContext", wintypes.ULONG),
        ("Flags", wintypes.ULONG),
    ]

class EVENT_TRACE_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("Wnode", WNODE_HEADER),
        ("BufferSize", wintypes.ULONG),
        ("MinimumBuffers", wintypes.ULONG),
        ("MaximumBuffers", wintypes.ULONG),
        ("MaximumFileSize", wintypes.ULONG),
        ("LogFileMode", wintypes.ULONG),
        ("FlushTimer", wintypes.ULONG),
        ("EnableFlags", wintypes.ULONG),
        ("AgeLimit", wintypes.LONG),
        ("NumberOfBuffers", wintypes.ULONG),
        ("FreeBuffers", wintypes.ULONG),
        ("EventsLost", wintypes.ULONG),
        ("BuffersWritten", wintypes.ULONG),
        ("LogBuffersLost", wintypes.ULONG),
        ("RealTimeBuffersLost", wintypes.ULONG),
        ("LoggerThreadId", wintypes.HANDLE),
        ("LogFileNameOffset", wintypes.ULONG),
        ("LoggerNameOffset", wintypes.ULONG),
        ("LoggerName", ctypes.c_wchar * 1024),
        ("LogFileName", ctypes.c_wchar * 1024),
    ]

class EVENT_HEADER(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.USHORT),
        ("HeaderType", wintypes.USHORT),
        ("Flags", wintypes.USHORT),
        ("EventProperty", wintypes.USHORT),
        ("ThreadId", wintypes.ULONG),
        ("ProcessId", wintypes.ULONG),
        ("TimeStamp", ctypes.c_int64),
        ("ProviderId", GUID),
        ("Id", wintypes.USHORT),
        ("Version", ctypes.c_ubyte),
        ("Channel", ctypes.c_ubyte),
        ("Level", ctypes.c_ubyte),
        ("Opcode", ctypes.c_ubyte),
        ("Task", wintypes.USHORT),
        ("Keyword", ctypes.c_uint64),
        ("KernelTime", wintypes.ULONG),
        ("UserTime", wintypes.ULONG),
        ("ActivityId", GUID),
    ]

class EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("EventHeader", EVENT_HEADER),
        ("BufferContext", ctypes.c_ubyte * 4),
        ("ExtendedDataCount", wintypes.USHORT),
        ("UserDataLength", wintypes.USHORT),
        ("ExtendedData", ctypes.c_void_p),
        ("UserData", ctypes.c_void_p),
        ("UserContext", ctypes.c_void_p),
    ]

EVENT_RECORD_CALLBACK = ctypes.WINFUNCTYPE(None, ctypes.POINTER(EVENT_RECORD))

class EVENT_TRACE_LOGFILEW(ctypes.Structure):
    _fields_ = [
        ("LogFileName", wintypes.LPWSTR),
        ("LoggerName", wintypes.LPWSTR),
        ("CurrentTime", ctypes.c_int64),
        ("BuffersRead", wintypes.ULONG),
        ("ProcessTraceMode", wintypes.ULONG),
        ("CurrentEvent", EVENT_RECORD),
        ("LogfileHeader", ctypes.c_byte * 280),
        ("BufferCallback", ctypes.c_void_p),
        ("BufferSize", wintypes.ULONG),
        ("Filled", wintypes.ULONG),
        ("EventsLost", wintypes.ULONG),
        ("EventRecordCallback", EVENT_RECORD_CALLBACK),
        ("IsKernelTrace", wintypes.ULONG),
        ("Context", ctypes.c_void_p),
    ]

class FpsMonitor:
    def __init__(self):
        self.current_fps = 0
        self.target_pid = 0
        self.last_fg_pid = 0
        self.rolling_size = 360
        self.frame_times = [0] * self.rolling_size
        self.frame_head = 0
        self.frames_filled = 0
        self.session_handle = 0
        self.trace_handle = 0
        self.session_name = "Esp32BleFpsSession"
        self.qpc_freq = ctypes.c_int64(0)
        kernel32.QueryPerformanceFrequency(byref(self.qpc_freq))

        # 桌面黑名单进程（不当做游戏测 FPS）
        self.desktop_apps = {
            "explorer", "shellexperiencehost", "searchhost", "taskmgr", "devenv", "code",
            "chrome", "msedge", "firefox", "powershell", "pwsh", "cmd", "conhost", "windowsterminal"
        }

        # 启动后台线程监听
        self.running = True
        self.th_etw = threading.Thread(target=self._etw_worker, daemon=True)
        self.th_etw.start()
        self.th_poll = threading.Thread(target=self._fps_poll_loop, daemon=True)
        self.th_poll.start()

    def _get_foreground_pid(self):
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return 0, ""
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, byref(pid))
        pname = ""
        try:
            p = psutil.Process(pid.value)
            pname = p.name().lower().replace(".exe", "")
        except Exception:
            pass
        return pid.value, pname

    def _build_props(self):
        p = EVENT_TRACE_PROPERTIES()
        p.Wnode.BufferSize = ctypes.sizeof(EVENT_TRACE_PROPERTIES)
        p.Wnode.Flags = 0x00020000
        p.Wnode.ClientContext = 1 # QPC
        p.LogFileMode = 0x00000100 # REAL_TIME
        p.LoggerNameOffset = EVENT_TRACE_PROPERTIES.LoggerName.offset
        p.BufferSize = 8
        p.MinimumBuffers = 8
        p.MaximumBuffers = 16
        return p

    def _on_event_record(self, record_ptr):
        try:
            record = record_ptr.contents
            if record.EventHeader.Id != 184 and record.EventHeader.Id != 42:
                return
            pid = record.EventHeader.ProcessId
            if pid <= 0 or pid != self.target_pid:
                return
            
            ts = record.EventHeader.TimeStamp
            self.frame_times[self.frame_head] = ts
            self.frame_head = (self.frame_head + 1) % self.rolling_size
            if self.frames_filled < self.rolling_size:
                self.frames_filled += 1
        except Exception:
            pass

    def _etw_worker(self):
        try:
            # 停止旧会话
            stop_props = self._build_props()
            advapi32.ControlTraceW(0, self.session_name, byref(stop_props), 1)

            props = self._build_props()
            handle = ctypes.c_int64(0)
            hr = advapi32.StartTraceW(byref(handle), self.session_name, byref(props))
            if hr != 0:
                # 无管理员权限或已被占用
                return

            self.session_handle = handle.value
            provider_guid = GUID("802EC45A-1E99-4B83-9920-87C98277BA9D")
            # 启用 DxgKrnl
            advapi32.EnableTraceEx2(self.session_handle, byref(provider_guid), 1, 4, 0x0000000008000000, 0, 0, None)

            # 打开跟踪
            self._cb_delegate = EVENT_RECORD_CALLBACK(self._on_event_record)
            logfile = EVENT_TRACE_LOGFILEW()
            logfile.LoggerName = self.session_name
            logfile.ProcessTraceMode = 0x00000100 | 0x10000000 | 0x00001000
            logfile.EventRecordCallback = self._cb_delegate

            trace_handle = advapi32.OpenTraceW(byref(logfile))
            if trace_handle == -1 or trace_handle == 0:
                return
            self.trace_handle = trace_handle

            # 刷新定时器
            def flush_loop():
                while self.running and self.session_handle:
                    time.sleep(0.2)
                    p = self._build_props()
                    advapi32.ControlTraceW(self.session_handle, None, byref(p), 3) # FLUSH

            threading.Thread(target=flush_loop, daemon=True).start()

            handles = (ctypes.c_int64 * 1)(self.trace_handle)
            advapi32.ProcessTrace(handles, 1, None, None)
        except Exception:
            pass

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
        return None

    def _fps_poll_loop(self):
        while self.running:
            time.sleep(0.4)
            pid, pname = self._get_foreground_pid()

            # 1. 尝试 RTSS
            rtss_fps = self._read_rtss_fps()
            if rtss_fps is not None and rtss_fps > 0:
                self.current_fps = int(rtss_fps)
                continue

            # 2. 检查前台进程
            if pid != self.last_fg_pid:
                self.last_fg_pid = pid
                if pname in self.desktop_apps or pid <= 0:
                    self.target_pid = 0
                    self.current_fps = 0
                else:
                    self.target_pid = pid
                    self.frame_head = 0
                    self.frames_filled = 0

            # 3. 计算 ETW FPS
            if self.target_pid > 0 and self.frames_filled >= 2:
                qpc_now = ctypes.c_int64(0)
                kernel32.QueryPerformanceCounter(byref(qpc_now))
                freq = self.qpc_freq.value

                head = self.frame_head
                newest = self.frame_times[(head - 1 + self.rolling_size) % self.rolling_size]

                if (qpc_now.value - newest) > 3 * freq:
                    self.current_fps = 0
                else:
                    cutoff = newest - freq
                    count = 1
                    oldest = newest
                    for i in range(2, self.frames_filled + 1):
                        t = self.frame_times[(head - i + self.rolling_size) % self.rolling_size]
                        if t < cutoff:
                            break
                        oldest = t
                        count += 1
                    elapsed = (newest - oldest) / freq
                    if elapsed > 0:
                        self.current_fps = int(round((count - 1) / elapsed))
                    else:
                        self.current_fps = 0
            else:
                self.current_fps = 0

    def get_fps(self):
        return self.current_fps


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
    # 基础系统数据
    cpu_percent = int(psutil.cpu_percent(interval=None))
    mem_percent = int(psutil.virtual_memory().percent)

    # 1. 华硕 EC 读 CPU 温度、风扇与性能模式
    cpu_temp = acpi_reader.get_cpu_temp()
    fan_cpu = acpi_reader.get_cpu_fan()
    fan_gpu = acpi_reader.get_gpu_fan()
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
    if cpu_pwr is None:
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
        "fan_cpu": fan_cpu or 0,
        "fan_gpu": fan_gpu or 0,
        "time": time.strftime("%H:%M:%S")
    }

    return json.dumps(payload, separators=(',', ':'))


# ==================== 7. BLE 发送主循环 ====================
async def run_ble_sender():
    print("=" * 65)
    print("  ESP32 华硕副屏 - BLE 蓝牙极速发射器 (G-Helper & FPS 增强版)")
    print("=" * 65)
    print(f"[配置] 华硕 ATKACPI: {'已就绪' if acpi_reader.handle else '未就绪 (请以管理员身份运行)'}")
    print(f"[配置] NVIDIA NVML:  {'已就绪' if gpu_reader.available else '未检测到 NVIDIA 显卡'}")
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
                print("[成功] 蓝牙连接成功！开始以 0.3s 极速推流硬件状态与游戏帧率...\n")
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
