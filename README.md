# ESP32 华硕笔记本状态信息监控副屏 🖥️

基于 **ESP32 + 2.4寸 TFT 彩屏 (ILI9341)** 构建的桌面硬件副屏，实时显示电脑硬件状态与网络时钟。支持 Wi-Fi HTTP、BLE 蓝牙低功耗、蓝牙串口 (SPP) 多种通信模式。

---

## 📸 项目特性

- 🕒 **实时网络时钟**：支持 NTP 网络时间精准同步与数码管风格排版显示。
- 💻 **硬件全维监控**：
  - **CPU**：占用率（进度条）、CPU Package 封装温度、实时功耗 (W)。
  - **GPU**：GPU 温度、实时功耗 (W)。
  - **RAM**：内存使用量 / 总量、占用率（进度条）。
- 🚀 **华硕专属优化**：支持直读 G-Helper 与 AIDA64 传感器注册表数据，超低系统资源开销，免管理员提权。
- 📡 **多通信链路支持**：
  - **Wi-Fi 模式**：ESP32 局域网 HTTP 请求 Python 本地服务。
  - **BLE 蓝牙模式**：低功耗蓝牙广播与订阅，无线免配网。
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
├── 06_ble_widget/                # 阶段 6：BLE 蓝牙低功耗无线传输版（含字体工具）
│   ├── 06_ble_widget.ino
│   ├── ble_pc_sender.py
│   ├── dseg_font.h
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

### 2. Wi-Fi HTTP 模式运行（阶段 4）
1. 打开 `04_widget/04_widget.ino`，将 `ssid`、`password` 与 `pc_url` 改为你实际的 Wi-Fi 与电脑 IP：
   ```cpp
   const char* ssid = "你的WiFi名称";
   const char* password = "你的WiFi密码";
   const char* pc_url = "http://你的电脑局域网IP:8080";
   ```
2. 电脑端启动数据源服务：
   ```bash
   python 03_pc_server.py
   ```
3. 将 `04_widget.ino` 烧录至 ESP32 开发板，即可自动连接并刷新监控画面。

### 3. BLE 蓝牙无线模式（阶段 6）
1. 烧录 `06_ble_widget/06_ble_widget.ino` 至 ESP32。
2. 电脑端双击运行 `06_ble_widget/一键启动_发送端.bat`（或执行 `python ble_pc_sender.py`），脚本将自动搜寻并连接 ESP32 进行推流。

### 4. 经典蓝牙 SPP 模式（阶段 6 备选）
1. 烧录 `06_bt_spp_widget/06_bt_spp_widget.ino` 至 ESP32。
2. 电脑端双击运行 `06_bt_spp_widget/一键启动_蓝牙串口发送端.bat`（或执行 `python bt_spp_pc_sender.py`）。
