# 阶段 5：g-helper 数据桥接服务（路线 A）
# 用法：先 pip install psutil pywin32，然后【管理员身份】运行  python 05_ghelper_bridge.py
# 验证：浏览器打开 http://127.0.0.1:8080 能看到 JSON（含 mode / fan_cpu / fan_gpu）
# 自检：python 05_ghelper_bridge.py --test    （打印各传感器原始值后退出）
#
# 数据来源（与 g-helper 同源，协议见项目内 g-helper/app/AsusACPI.cs、HardwareControl.cs）：
#   1. CPU 温度 / 性能模式 / 风扇转速 / 电池放电：华硕 ATKACPI（\\.\ATKACPI + DeviceIoControl，
#      直读笔记本 EC 寄存器。需要管理员权限 + ASUS System Control Interface 驱动，本机已装）
#   2. CPU 功耗：Windows 性能计数器 "Energy Meter\Power"（Intel RAPL / AMD APU 能量计）
#   3. GPU 温度/功耗/占用：nvidia-smi
#   4. 兜底：AIDA64 注册表直读（勾选"启用写入注册表"并保持后台运行时才可用）
#
# 注意：与 03_pc_server.py 共用 8080 端口，先停掉旧的再跑本脚本。

import json, os, re, struct, subprocess, sys, time, ctypes, winreg
from ctypes import wintypes
from http.server import HTTPServer, BaseHTTPRequestHandler
import psutil

# ==================== 华硕 ATKACPI 底层（与 g-helper AsusACPI.cs 协议完全一致） ====================
ATKACPI_DEVICE = r"\\.\ATKACPI"
CONTROL_CODE   = 0x0022240C
DSTS = 0x53545344   # "STSD"：读设备
DEVS = 0x53564544   # "DEVS"：写设备
INIT = 0x54494E49   # "INIT"：初始化接口

# 设备 ID（g-helper AsusACPI.cs 中的公开常量）
DEV_CPU_TEMP   = 0x00120094   # Temp_CPU
DEV_GPU_TEMP   = 0x00120097   # Temp_GPU
DEV_PERF_MODE  = 0x00120075   # PerformanceMode：0=平衡 1=增强 2=静音 3=全速 4=手动
DEV_CPU_FAN    = 0x00110013   # CPU_Fan
DEV_GPU_FAN    = 0x00110014   # GPU_Fan
DEV_BATTERY_DISCHARGE = 0x0012005A   # BatteryDischarge

# 风扇转速换算：本机 EC 返回的是 RPM÷100（g-helper GetFan 的 fan>120 判空即据此），
# 实测 CPU fan raw=30 → 3000 RPM。若你的机器不符，改这个系数。
FAN_SCALE = 100

GENERIC_READ  = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ  = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80

MODE_NAMES = {0: "BALANCED", 1: "TURBO", 2: "SILENT", 3: "FULL", 4: "MANUAL"}

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p,
                                     wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                     ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
kernel32.DeviceIoControl.restype = wintypes.BOOL


class AtkAcpi:
    """华硕 EC 直读句柄。用法与 g-helper 的 AsusACPI 类一致。"""

    def __init__(self):
        self.handle = kernel32.CreateFileW(
            ATKACPI_DEVICE, GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL, None)
        if not self.handle or self.handle == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(),
                          "打开 \\\\.\\ATKACPI 失败（请以管理员身份运行本脚本）")
        try:
            self._call(INIT, b"\x00" * 8)   # 与 g-helper DeviceInit() 一致
        except Exception:
            pass

    def _call(self, method_id, args=b""):
        # CallMethod：in 缓冲 = [MethodID(4) + args长度(4) + args]，out 固定 16 字节
        buf = struct.pack("<II", method_id, len(args)) + args
        out = ctypes.create_string_buffer(16)
        returned = wintypes.DWORD(0)
        ok = kernel32.DeviceIoControl(self.handle, CONTROL_CODE,
                                      buf, len(buf), out, 16,
                                      ctypes.byref(returned), None)
        if not ok:
            raise OSError(ctypes.get_last_error(), "DeviceIoControl 失败")
        return out.raw

    def device_get(self, device_id):
        """与 g-helper DeviceGet 完全一致：DSTS 读回 int32，减 65536。"""
        args = struct.pack("<I", device_id) + b"\x00" * 4
        raw = self._call(DSTS, args)
        return struct.unpack("<i", raw[:4])[0] - 65536

    def device_get_buffer(self, device_id, status=0):
        args = struct.pack("<II", device_id, status)
        return self._call(DSTS, args)

    def close(self):
        try:
            if self.handle:
                kernel32.CloseHandle(self.handle)
        except Exception:
            pass


# ==================== 传感器读取 ====================

def read_cpu_temp(acpi):
    try:
        t = acpi.device_get(DEV_CPU_TEMP)
        if 0 <= t <= 125:
            return t
    except Exception:
        pass
    return None


def read_fan(acpi, dev):
    """风扇转速(RPM)：EC 返回缩略值（RPM÷100），按 FAN_SCALE 换算。"""
    try:
        raw = acpi.device_get(dev)
        fan = raw & 0xFFFF
        if fan > 120 or (fan == 0 and raw < 0):   # 与 g-helper GetFan 判空一致
            return None
        return fan * FAN_SCALE
    except Exception:
        return None


def read_mode(acpi):
    """性能模式：优先读 EC 当前值，读不到则回退 g-helper 注册表配置。"""
    try:
        m = acpi.device_get(DEV_PERF_MODE)
        if 0 <= m <= 4:
            return m
    except Exception:
        pass
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\GHelper")
        v, _ = winreg.QueryValueEx(key, "performance_mode")
        winreg.CloseKey(key)
        v = int(v)
        if 0 <= v <= 4:
            return v
    except Exception:
        pass
    return None


def read_battery_discharge(acpi):
    """电池放电功率(W)，与 g-helper GetBatteryDischarge 一致（插电充电时为 null）。"""
    try:
        buf = acpi.device_get_buffer(DEV_BATTERY_DISCHARGE)
        if buf[2] > 0:
            buf = bytearray(buf)
            buf[2] = 0
            w = struct.unpack("<h", bytes(buf[:2]))[0] / 100.0
            if 0 <= w <= 200:
                return w
    except Exception:
        pass
    return None


# ==================== CPU 功耗：Energy Meter\\Power（Intel RAPL / AMD APU） ====================

_power_session = None
_power_path = None


def _try_add_power_counter(win32pdh, path):
    """尝试用 AddCounter / AddEnglishCounter 打开一条计数器路径，成功返回 (hq, hc)。"""
    hq = None
    for adder in (win32pdh.AddCounter, getattr(win32pdh, "AddEnglishCounter", None)):
        if adder is None:
            continue
        try:
            hq = win32pdh.OpenQuery()
            hc = adder(hq, path)
            win32pdh.CollectQueryData(hq)   # 第一次采样，建立基准
            time.sleep(0.4)
            win32pdh.CollectQueryData(hq)   # 第二次采样，得到有效速率值
            return hq, hc
        except Exception:
            try:
                if hq is not None:
                    win32pdh.CloseQuery(hq)
            except Exception:
                pass
            hq = None
    return None


def init_cpu_power():
    """打开 Energy Meter\\Power 性能计数器。中英文系统通用：先枚举实际名称，
    再逐个尝试 本地化路径 / 英文路径 × AddCounter / AddEnglishCounter。"""
    global _power_session, _power_path
    try:
        import win32pdh
    except ImportError:
        print("未安装 pywin32：请执行  pip install pywin32  （CPU 功耗将回退 AIDA64）")
        return

    # 1) 枚举 Energy Meter 对象（中文系统枚举出来可能是本地化名称）
    try:
        objects = win32pdh.EnumObjects(None, None, win32pdh.PERF_DETAIL_WIZARD)
        em = None
        for o in objects:
            u = o.upper()
            if "ENERGY" in u or "METER" in u or "能量" in o:
                em = o
                break
        if em is None:
            print("未发现 Energy Meter 对象（CPU 功耗将回退 AIDA64）")
            return
    except Exception as e:
        print("枚举 Energy Meter 对象失败（CPU 功耗将回退 AIDA64）：", e)
        return

    # 2) 枚举计数器与实例
    try:
        counters, instances = win32pdh.EnumObjectItems(None, None, em, win32pdh.PERF_DETAIL_WIZARD)
    except Exception as e:
        print("枚举 Energy Meter 计数器失败（CPU 功耗将回退 AIDA64）：", e)
        return

    power_name = None
    for c in counters:
        if c.upper() == "POWER" or "功率" in c:
            power_name = c
            break
    if power_name is None:
        print("Energy Meter 无 Power 计数器（枚举到：%s）（CPU 功耗将回退 AIDA64）" % counters)
        return

    names = [i[0] for i in instances] if instances else []
    preferred = ["Apu Power", "RAPL_Package0_PKG", "CPU Power",
                 "Socket Power", "Current Socket Power"]
    cands = [n for n in preferred if n in names] or names

    # 3) 候选路径：实例限定 + 无实例；本地化名称 + 英文名称
    paths = []
    for n in cands:
        if n:
            paths.append("\\%s\\%s(%s)" % (em, power_name, n))
            paths.append("\\Energy Meter\\Power(%s)" % n)   # 英文路径（配合 AddEnglishCounter）
    paths.append("\\%s\\%s" % (em, power_name))
    paths.append("\\Energy Meter\\Power")

    for p in paths:
        sess = _try_add_power_counter(win32pdh, p)
        if sess is not None:
            _power_session, _power_path = sess, p
            print("CPU 功耗来源：%s" % p)
            return

    # 4) 兜底：PowerShell 列出真实计数器路径，便于排查
    print("Energy Meter 计数器添加失败，PowerShell 枚举结果如下（CPU 功耗将回退 AIDA64）：")
    try:
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Counter -ListSet * | Where-Object { $_.CounterSetName -match 'meter|energy|能量' } | ForEach-Object { $_.PathsWithInstances }"],
            capture_output=True, text=True, timeout=10)
        out = (ps.stdout or "").strip()
        print(out if out else "(PowerShell 无输出，可能没有能量计数器)" + (ps.stderr or ""))
    except Exception as e:
        print("PowerShell 枚举失败：", e)


def read_cpu_power():
    """读 RAPL 功耗。g-helper 将 Energy Meter 读数按毫瓦处理，除以 1000 得瓦。"""
    if _power_session is None:
        return None
    try:
        import win32pdh
        hq, hc = _power_session
        win32pdh.CollectQueryData(hq)
        _t, val = win32pdh.GetFormattedCounterValue(hc, win32pdh.PDH_FMT_DOUBLE)
        w = float(val) / 1000.0
        if 1.0 <= w <= 300.0:      # 单位合理性护栏：低于 1W 视为异常，回退 AIDA64
            return round(w, 1)
        return None
    except Exception:
        return None


def read_gpu_nvidia():
    """NVIDIA 独显温度/功耗/占用，直接调 nvidia-smi（与 g-helper NvidiaSmi.cs 同源）。"""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu,power.draw,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3)
        parts = [p.strip() for p in out.stdout.strip().split(",")]
        if len(parts) < 3:
            return None, None, None
        temp = float(parts[0])
        pwr = float(parts[1])
        use = int(float(parts[2]))
        return (temp if 0 <= temp <= 125 else None,
                pwr if 0 <= pwr <= 500 else None,
                use if 0 <= use <= 100 else None)
    except Exception:
        return None, None, None


def read_aida64_sensors():
    """兜底：从注册表读 AIDA64 传感器（与 03_pc_server.py 相同，CPU Package 严格优先）。"""
    cpu_temp = cpu_power = gpu_temp = gpu_power = gpu_usage = None
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\FinalWire\AIDA64\SensorValues")
        num = winreg.QueryInfoKey(key)[1]
        items = []
        for i in range(num):
            name, val, _ = winreg.EnumValue(key, i)
            items.append((str(name).upper(), str(val)))
        winreg.CloseKey(key)

        for name, v in items:
            if any(k in name for k in ["TCPUPKG", "CPU PACKAGE", "CPU 封装", "PACKAGE"]):
                m = re.search(r"[-+]?\d+\.?\d*", v)
                if m and 15 <= float(m.group()) <= 115:
                    cpu_temp = float(m.group())
                    break
        if cpu_temp is None:
            for name, v in items:
                if "TCPU" in name or "CPU" in name:
                    m = re.search(r"[-+]?\d+\.?\d*", v)
                    if m and 15 <= float(m.group()) <= 115:
                        cpu_temp = float(m.group())
                        break

        for name, v in items:
            if any(k in name for k in ["PCPUPKG", "CPU PACKAGE POWER", "CPU 封装功耗", "PACKAGE POWER"]):
                m = re.search(r"[-+]?\d+\.?\d*", v)
                if m and 0 <= float(m.group()) <= 500:
                    cpu_power = float(m.group())
                    break
        if cpu_power is None:
            for name, v in items:
                if "PCPU" in name or "CPU 功耗" in name:
                    m = re.search(r"[-+]?\d+\.?\d*", v)
                    if m and 0 <= float(m.group()) <= 500:
                        cpu_power = float(m.group())
                        break

        for name, v in items:
            if any(k in name for k in ["图形处理器", "TGPU", "GPU", "显卡"]):
                if not any(k in name for k in ["HOTSPOT", "MEMORY", "USAGE", "UTIL"]):
                    m = re.search(r"[-+]?\d+\.?\d*", v)
                    if m and 15 <= float(m.group()) <= 115:
                        gpu_temp = float(m.group())
                        break

        for name, v in items:
            if any(k in name for k in ["GT CORES", "GT CORE", "CPU GT", "PGT"]):
                m = re.search(r"[-+]?\d+\.?\d*", v)
                if m and 0 <= float(m.group()) <= 800:
                    gpu_power = float(m.group())
                    break
        if gpu_power is None:
            for name, v in items:
                if any(k in name for k in ["PGPU", "GPU POWER", "GPU 功耗"]):
                    m = re.search(r"[-+]?\d+\.?\d*", v)
                    if m and 0 <= float(m.group()) <= 800:
                        gpu_power = float(m.group())
                        break

        for name, v in items:
            if any(k in name for k in ["GPU UTILIZATION", "GPU 使用率", "GPU 负载", "UGPU", "GPU1UTIL"]):
                m = re.search(r"[-+]?\d+\.?\d*", v)
                if m and 0 <= float(m.group()) <= 100:
                    gpu_usage = int(float(m.group()))
                    break
    except Exception:
        pass
    return {"cpu_temp": cpu_temp, "cpu_pwr": cpu_power,
            "gpu_temp": gpu_temp, "gpu_pwr": gpu_power, "gpu_usage": gpu_usage}


# ==================== 汇总与 HTTP 服务 ====================

acpi = None


def get_stats():
    cpu = int(psutil.cpu_percent(interval=None))
    mem = int(psutil.virtual_memory().percent)
    sensors = read_aida64_sensors()

    cpu_temp = read_cpu_temp(acpi) if acpi else None
    if cpu_temp is None:
        cpu_temp = sensors["cpu_temp"]

    cpu_pwr = read_cpu_power()
    if cpu_pwr is None:
        cpu_pwr = sensors["cpu_pwr"]

    gpu_temp, gpu_pwr, gpu_use = read_gpu_nvidia()
    if gpu_temp is None:
        gpu_temp = sensors["gpu_temp"]
    if gpu_pwr is None:
        gpu_pwr = sensors["gpu_pwr"]
    if gpu_use is None:
        gpu_use = sensors["gpu_usage"]

    mode = read_mode(acpi) if acpi else None

    return {
        "cpu": cpu, "mem": mem,
        "cpu_temp": cpu_temp, "cpu_pwr": cpu_pwr,
        "gpu_temp": gpu_temp, "gpu_pwr": gpu_pwr, "gpu_usage": gpu_use,
        "time": time.strftime("%H:%M:%S"),
        "mode": mode,
        "mode_name": MODE_NAMES.get(mode) if mode is not None else None,
        "fan_cpu": read_fan(acpi, DEV_CPU_FAN) if acpi else None,
        "fan_gpu": read_fan(acpi, DEV_GPU_FAN) if acpi else None,
        "battery_w": read_battery_discharge(acpi) if acpi else None,
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = json.dumps(get_stats()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


# ==================== 管理员权限 ====================

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return True


def relaunch_as_admin():
    shell32 = ctypes.windll.shell32
    shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                      wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
    shell32.ShellExecuteW.restype = wintypes.HINSTANCE
    cmd = '"%s" %s' % (os.path.abspath(__file__), " ".join(sys.argv[1:]))
    shell32.ShellExecuteW(None, "runas", sys.executable, cmd, None, 1)


def main():
    global acpi
    if "--no-elevate" not in sys.argv and not is_admin():
        print("非管理员权限，ATKACPI 需要提权，正在弹出 UAC 请求...")
        relaunch_as_admin()
        return

    print("==================================================")
    print("g-helper 数据桥接服务（阶段 5，路线 A）")
    print("==================================================")
    try:
        acpi = AtkAcpi()
        print("ATKACPI（华硕 EC）：可用")
    except Exception as e:
        acpi = None
        print("ATKACPI（华硕 EC）：不可用 ->", e)
        print("  （CPU 温度/模式/风扇将回退到 AIDA64 注册表）")

    aida = read_aida64_sensors()
    print("AIDA64 注册表：%s" % ("可用" if any(v is not None for v in aida.values()) else "未运行/未勾选写入注册表"))
    init_cpu_power()

    if "--test" in sys.argv:
        print("\n--- 传感器自检 ---")
        print(json.dumps(get_stats(), ensure_ascii=False, indent=2))
        if acpi:
            try:
                print("\nATKACPI 原始值（用于排查，非输出字段）：")
                print("  cpu_temp_raw =", acpi.device_get(DEV_CPU_TEMP))
                print("  mode_raw     =", acpi.device_get(DEV_PERF_MODE))
                print("  fan_cpu_raw  =", acpi.device_get(DEV_CPU_FAN),
                      "  -> 显示", (acpi.device_get(DEV_CPU_FAN) & 0xFFFF) * FAN_SCALE, "RPM")
                print("  fan_gpu_raw  =", acpi.device_get(DEV_GPU_FAN),
                      "  -> 显示", (acpi.device_get(DEV_GPU_FAN) & 0xFFFF) * FAN_SCALE, "RPM")
            except Exception as e:
                print("  读取原始值失败：", e)
        return

    print("本地测试：浏览器打开 http://127.0.0.1:8080")
    print("==================================================")
    try:
        HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
    except OSError as e:
        print("端口 8080 被占用（请先停止 03_pc_server.py）:", e)
    finally:
        if acpi:
            acpi.close()


if __name__ == "__main__":
    main()
