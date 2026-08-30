# ESP32 华硕笔记本状态信息监控副屏 🖥️

基于 **ESP32 + 2.4寸 TFT 彩屏 (ILI9341)** 构建的桌面硬件副屏，实时显示电脑硬件状态、G-Helper 性能模式、实时游戏帧率 (FPS) 与网络时钟。支持 Wi-Fi HTTP、BLE 蓝牙低功耗、蓝牙串口 (SPP) 多种通信模式。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-ESP32-brightgreen.svg)
![Language](https://img.shields.io/badge/language-C%2B%2B%20%2F%20Python-orange.svg)

---

## 📸 项目特性

- 🎮 **游戏实时帧率 (FPS)**：支持 Windows ETW (DxgKrnl Present) / RTSS 游戏渲染帧率直读，游戏时自动高亮显示实时帧率。
- 🕒 **实时网络时钟 / 性能模式**：支持 NTP 网络时间同步；桌面状态下自动展示 G-Helper 当前性能模式（`TURBO`/`BALANCED`/`SILENT`）。
- 💻 **硬件全维监控**：
  - **CPU**：占用率（进度条）、CPU Package 封装温度、实时功耗 (W)。
  - **GPU**：GPU 占用率（进度条）、GPU 温度、实时功耗 (W)。
  - **RAM & 风扇**：内存使用率（进度条）、CPU / GPU 风扇实时转速 (RPM)。
- 🚀 **华硕 G-Helper 深度对接**：
  - 华硕 ATKACPI 硬件直读（`\\.\ATKACPI`），直读笔记本 EC 寄存器。
  - NVIDIA NVML 底层直读（`nvml.dll`），毫秒级延迟，0 系统开销。
  - Windows Energy Meter RAPL 硬件功耗直读。
- 📡 **多通信链路支持**：
  - **BLE 蓝牙模式 (推荐)**：0.3s 极速低功耗推流，无线免配网。
  - **Wi-Fi 模式**：ESP32 局域网 HTTP 请求 Python 本地服务。
  - **蓝牙串口 (SPP) 模式**：传统蓝牙虚拟串口高速推流。
- ⚡ **原生直驱引擎**：内置底层 GPIO SPI 驱动，告别库配置冲突与白屏问题。

---

## 🔌 硬件接线表（已验证 100% 稳定方案）

> **屏幕型号**：2.4 寸 TFT LCD（驱动 IC：**ILI9341**，分辨率 240×320）  
> ⚠️ **注意**：VCC 必须连接 **5V (VIN)**，背光 LED 连接 **3.3V**；请严格避开 ESP32 内部 Flash 禁区引脚。

| 屏幕排针 | ESP32 GPIO 引脚 | 作用说明 |
| :--- | :--- | :--- |
| **VCC** | **5V (VIN)** | 屏幕主电源供电 |
| **GND** | **GND** | 接地（切勿接错到 G0/SD0） |
| **CS** | **GPIO 4 (D4)** | 片选信号 |
| **RESET** | **GPIO 17 (TX2)** | 硬件复位 |
| **DC** | **GPIO 16 (RX2)** | 数据 / 命令切换 |
| **SDI (MOSI)** | **GPIO 23 (D23)** | SPI 数据主出从入 |
| **SCK** | **GPIO 18 (D18)** | SPI 时钟 |
| **LED** | **3.3V (3V3)** | 屏幕背光供电 |
| **SDO (MISO)** | *悬空不接* | 本项目无需回传触摸/SD 数据 |

---

## 📂 目录结构与各阶段源码

```text
├── 00_购买清单与完整流程.md        # 硬件选型、接线与阶段开发完整教程
├── 01_hello_screen/              # 阶段 1：屏幕底层驱动与 RGB 点亮测试
│   └── 01_hello_screen.ino
├── 02_ntp_time/                  # 阶段 2：WiFi NTP 网络时间同步
│   └── 02_ntp_time.ino
├── 03_pc_server.py               # 阶段 3：PC 端 Python 硬件数据采集服务（HTTP）
├── 04_widget/                    # 阶段 4：Wi-Fi HTTP 完整桌面监控副屏
│   └── 04_widget.ino
├── 05_ghelper_bridge/            # 华硕 G-Helper 深度对接桥接版
│   ├── 04_widget_ghelper/
│   │   └── 04_widget_ghelper.ino
│   ├── 05_ghelper_bridge.py
│   └── 使用说明.md
├── 06_ble_widget/                # 阶段 6 (推荐)：BLE 蓝牙低功耗版（华硕 G-Helper + 游戏 FPS）
│   ├── 06_ble_widget.ino
│   ├── ble_pc_sender.py
│   ├── 一键启动_BLE发送端.bat
│   ├── dseg_font.h
│   ├── README.md
│   └── tools/
├── 06_bt_spp_widget/             # 阶段 6 备选：经典蓝牙 SPP 串口高速推流版
│   ├── 06_bt_spp_widget.ino
│   └── bt_spp_pc_sender.py
├── 99_项目提示词.md               # 项目上下文记忆与核心避坑库
└── .gitignore                    # Git 忽略规则配置
```

---

## 🚀 快速上手指南

### 1. 软件环境准备
- **Arduino IDE 2.x**：安装 ESP32 开发板核心（推荐 `2.0.17` 版本）
- **Python 3.10+**：安装所需依赖库
  ```bash
  pip install psutil wmi pywin32 bleak pyserial
  ```

### 2. BLE 蓝牙无线模式（阶段 6 推荐）
1. 烧录 `06_ble_widget/06_ble_widget.ino` 至 ESP32。
2. 电脑端双击运行 `06_ble_widget/一键启动_BLE发送端.bat`（自动以管理员身份运行，启用 ATKACPI 与 ETW 游戏 FPS 监控）。
3. 脚本将自动搜寻并连接 ESP32 进行 0.3s 极速推流。

### 3. Wi-Fi HTTP 模式（阶段 4）
1. 打开 `04_widget/04_widget.ino`，将 `ssid`、`password` 与 `pc_url` 改为你实际的 Wi-Fi 与电脑 IP。
2. 电脑端运行 `python 03_pc_server.py`，烧录 `04_widget.ino` 即可。

---

## 🛡️ 许可证

本项目采用 [MIT License](LICENSE) 开源协议。
