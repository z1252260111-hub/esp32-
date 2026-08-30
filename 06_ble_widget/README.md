# ESP32 低功耗蓝牙 (BLE) 桌面副屏 · 华硕 G-Helper & 游戏 FPS 增强版

本方案为【低功耗蓝牙 (BLE)】独立版本，深度对接华硕 G-Helper 体系，支持游戏实时帧率 (FPS) 采集与硬件全维监控。

---

## 📸 核心特性

- 🎮 **游戏实时帧率 (FPS)**：
  - Windows ETW (`Microsoft-Windows-DxgKrnl`) 底层 Present 事件捕获，与 G-Helper 相同机制，0 负载测速。
  - 支持 RTSS (RivaTuner) 共享内存与 AIDA64 多重兜底。
  - 游戏时顶部高亮实时显示 `144 FPS`（动态变色），桌面时平滑切换为 G-Helper 性能模式（`TURBO`/`BALANCED`）或时钟。
- 🚀 **华硕 G-Helper 深度对接**：
  - **ASUS ATKACPI (`\\.\ATKACPI`)**：直读笔记本 EC 硬件寄存器（CPU 温度、风扇转速、性能模式）。
  - **NVIDIA NVML (`nvml.dll`)**：底层 C 接口直读独显 GPU 温度、实时功耗 (W)、GPU 占用率。
  - **Windows Energy Meter RAPL**：硬件级 CPU Package 功耗直读。
- ⚡ **超低功耗与极速刷新**：
  - 蓝牙功耗仅为 Wi-Fi 的 1/5 ~ 1/10，0.3s 极速 GATT 数据推流，无需连接路由器。

---

## 📁 目录文件清单

* `06_ble_widget.ino`：ESP32 蓝牙从机固件（内置 BLE GATT 服务 + JetBrains Mono 现代字库 + 动态变色引擎）。
* `ble_pc_sender.py`：电脑端 Python 蓝牙发射器（ATKACPI + NVML + ETW FPS + BLE 推流）。
* `一键启动_BLE发送端.bat`：Windows 一键提权启动脚本。
* `dseg_font.h`：字库独立备份。
* `tools/`：字体生成与效果预览工具。

---

## 🎨 动态配色规则

| 指标 | 绿色/青色（正常） | 黄色/橙色（中高负载） | 红色（极限/危险） |
| :--- | :--- | :--- | :--- |
| **游戏 FPS** | ≥120 FPS（荧光绿） / ≥60 FPS（青色） | 30~59 FPS（黄色） | <30 FPS（红色） |
| **CPU / GPU / MEM 占用率** | ≤60% 绿色 | 61~85% 黄色 | >85% 红色 |
| **CPU 温度** | <70°C 青色 | 70~87°C 黄橙 | ≥88°C 红色 |
| **GPU 温度** | <60°C 青色 | 60~84°C 黄橙 | ≥85°C 红色 |
| **CPU 功耗 (160W标定)** | <56W 青色 | 56~119W 橙色 | ≥120W 红色 |
| **GPU 功耗 (150W标定)** | <52W 青色 | 52~112W 橙色 | ≥113W 红色 |

---

## 🚀 使用步骤

### 1. 烧录 ESP32 固件
1. 打开 Arduino IDE。
2. 打开 `06_ble_widget/06_ble_widget.ino`。
3. 编译并上传到开发板。屏幕显示 `BLE WAITING...` 等待连接。

### 2. 电脑端一键启动
1. 确保电脑已开启蓝牙。
2. 双击运行 `06_ble_widget/一键启动_BLE发送端.bat`（会自动申请管理员权限以启用华硕 EC 硬件直读与 ETW 游戏 FPS 监控）。
3. 脚本将自动搜寻并连接 `ESP32-Dashboard`，副屏随即开启监控！
