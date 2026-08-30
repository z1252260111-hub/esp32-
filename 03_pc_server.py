# 阶段 3：电脑端数据服务
# 用法：先 pip install psutil，然后运行 python 03_pc_server.py
# 验证：浏览器打开 http://127.0.0.1:8080 能看到一段 JSON
#
# 温度/风扇数据来源（自动选择，装不上也不影响基本功能）：
#   1. AIDA64（推荐）：文件 → 设置 → WMI → 启用 WMI 支持（AIDA64 保持后台运行）
#   2. LibreHardwareMonitor：GitHub 下载，管理员运行
#   3. Linux：sudo 运行，psutil 直接读
#   都读不到时：只返回 CPU 占用和内存

import json, time, re
from http.server import HTTPServer, BaseHTTPRequestHandler
import psutil

import winreg

def read_aida64_sensors():
    """从 Windows 注册表读取 AIDA64 的 CPU/GPU 温度与功耗"""
    cpu_temp = None
    cpu_power = None
    gpu_temp = None
    gpu_power = None

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\FinalWire\AIDA64\SensorValues")
        num_values = winreg.QueryInfoKey(key)[1]
        
        all_items = []
        for i in range(num_values):
            name, val, _ = winreg.EnumValue(key, i)
            all_items.append((str(name).upper(), str(val)))
        winreg.CloseKey(key)

        # 1. CPU Package 温度 (绝对严格第一优先级扫描)
        for name_upper, val_str in all_items:
            if any(k in name_upper for k in ["TCPUPKG", "CPU PACKAGE", "CPU 封装", "PACKAGE"]):
                m = re.search(r"[-+]?\d+\.?\d*", val_str)
                if m:
                    num = float(m.group())
                    if 15 <= num <= 115:
                        cpu_temp = num
                        break
        # 若实在没有 Package，再 fallback 到 TCPU
        if cpu_temp is None:
            for name_upper, val_str in all_items:
                if "TCPU" in name_upper or "CPU" in name_upper:
                    m = re.search(r"[-+]?\d+\.?\d*", val_str)
                    if m:
                        num = float(m.group())
                        if 15 <= num <= 115:
                            cpu_temp = num
                            break

        # 2. CPU Package 功耗 (W)
        for name_upper, val_str in all_items:
            if any(k in name_upper for k in ["PCPUPKG", "CPU PACKAGE POWER", "CPU 封装功耗", "PACKAGE POWER"]):
                m = re.search(r"[-+]?\d+\.?\d*", val_str)
                if m:
                    num = float(m.group())
                    if 0 <= num <= 500:
                        cpu_power = num
                        break
        if cpu_power is None:
            for name_upper, val_str in all_items:
                if "PCPU" in name_upper or "CPU 功耗" in name_upper:
                    m = re.search(r"[-+]?\d+\.?\d*", val_str)
                    if m:
                        num = float(m.group())
                        if 0 <= num <= 500:
                            cpu_power = num
                            break

        # 3. GPU 温度 (图形处理器(GPU))
        for name_upper, val_str in all_items:
            if any(k in name_upper for k in ["图形处理器", "TGPU", "GPU", "显卡"]):
                if "HOTSPOT" not in name_upper and "MEMORY" not in name_upper and "USAGE" not in name_upper and "UTIL" not in name_upper:
                    m = re.search(r"[-+]?\d+\.?\d*", val_str)
                    if m:
                        num = float(m.group())
                        if 15 <= num <= 115:
                            gpu_temp = num
                            break

        # 4. GPU 功耗 (CPU GT Cores)
        for name_upper, val_str in all_items:
            if any(k in name_upper for k in ["GT CORES", "GT CORE", "CPU GT", "PGT"]):
                m = re.search(r"[-+]?\d+\.?\d*", val_str)
                if m:
                    num = float(m.group())
                    if 0 <= num <= 800:
                        gpu_power = num
                        break
        if gpu_power is None:
            for name_upper, val_str in all_items:
                if any(k in name_upper for k in ["PGPU", "GPU POWER", "GPU 功耗"]):
                    m = re.search(r"[-+]?\d+\.?\d*", val_str)
                    if m:
                        num = float(m.group())
                        if 0 <= num <= 800:
                            gpu_power = num
                            break

        # 5. GPU 占用率 (GPU Utilization / GPU 负载 / GPU 使用率)
        gpu_usage = None
        for name_upper, val_str in all_items:
            if any(k in name_upper for k in ["GPU UTILIZATION", "GPU 使用率", "GPU 负载", "UGPU", "GPU1UTIL"]):
                m = re.search(r"[-+]?\d+\.?\d*", val_str)
                if m:
                    num = float(m.group())
                    if 0 <= num <= 100:
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

def get_stats():
    # interval=None 保证瞬间返回瞬态 CPU 使用率，零阻塞，支持 0.3 秒超高刷新
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory().percent
    sensors = read_aida64_sensors()
    
    return {
        "cpu": int(cpu),
        "mem": int(mem),
        "cpu_temp": sensors["cpu_temp"],
        "cpu_pwr": sensors["cpu_pwr"],
        "gpu_temp": sensors["gpu_temp"],
        "gpu_pwr": sensors["gpu_pwr"],
        "gpu_usage": sensors["gpu_usage"],
        "time": time.strftime("%H:%M:%S")
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

print("==================================================")
print("PC 数据服务已就绪！")
print("本地测试：浏览器打开 http://127.0.0.1:8080")
print("==================================================")
HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
