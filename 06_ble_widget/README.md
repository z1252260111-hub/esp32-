# ESP32 低功耗蓝牙 (BLE) 桌面副屏 · 使用指南

本方案为【低功耗蓝牙 (BLE)】独立开发版本，功耗仅为 WiFi 的 **1/5 ~ 1/10**，无需连接路由器，适合便携/电池供电或无 WiFi 环境。

---

## 📁 目录文件清单

* `06_ble_widget.ino`：ESP32 蓝牙从机固件（内置 BLE GATT 服务 + DSEG 开源 LCD 字库 + 动态配色引擎）。字库已**内联在 .ino 里，单文件自包含**——新建空白草稿直接粘贴整个文件内容也能编译。
* `dseg_font.h`：16x24 位图字库独立副本（脚本自动生成，勿手改；已被内联进 .ino，仅作备份/再生成用）。
* `ble_pc_sender.py`：电脑端 Python 蓝牙发射器（自动扫描 `ESP32-Dashboard` 并以 0.3s 推送硬件状态）。
* `tools/gen_font.py`：字体生成脚本（DSEG7/DSEG14 -> dseg_font.h，改字号/字重/字符集后重跑即可）。
* `tools/preview.py`：整屏效果模拟器（生成 `tools/preview.png`，烧录前预览配色效果）。

---

## 🔤 字体方案（v4：放大版）

当前使用开源 **JetBrains Mono Bold**（SIL OFL 1.1 许可，[github.com/JetBrains/JetBrainsMono](https://github.com/JetBrains/JetBrainsMono)），**22x33 大字模**（字高约 24px，比初版大 50%）：

* 现代等宽字体：数字严格等宽（刷新不抖动）、x-height 大、小字号可读性最佳；
* 带斜杠零（0/O 不混淆），`%` 冒号句点等符号齐全，适合仪表数值显示；
* 修复旧手绘字库的 bug：缺 A/I/T/N/F/R 等字母（"BLE WAITING..." 曾显示为空白）、`%` 字形只画了上半截；
* 占用率/温度显示上限 99（防 4 字符越界，只在瞬时尖峰出现且颜色已是红色）。

> 换字体大小/风格：
> ```powershell
> cd esp32\06_ble_widget\tools
> python gen_font.py jbmono 22 33   # 当前: 现代清晰风 22x33 (默认 16x24)
> python gen_font.py dseg 22 33     # LCD 仪表风 22x33
> ```
> 生成后把 `dseg_font.h` 的内容重新粘贴进 .ino 的内联区（或改回 include 方式）。

### 🎨 动态配色规则（按 i7-14650HX 笔记本标定）

| 数据 | 青/绿（正常） | 黄（偏热） | 橙（高负载） | 红（危险） |
| :--- | :--- | :--- | :--- | :--- |
| CPU/GPU/MEM 占用率 | ≤60% 绿 | 61~85% | — | >85% |
| CPU 温度 (14650HX) | <70°C | 70~77°C | 78~87°C | ≥88°C |
| GPU 温度（笔记本独显） | <60°C | 60~74°C | 75~84°C | ≥85°C |
| CPU 功率（参考 160W = PL2 157W） | <56W | — | 56~119W | ≥120W |
| GPU 功率（参考 150W） | <52W | — | 52~112W | ≥113W |

> 笔记本 HX 处理器日常游戏 80~90°C 属正常工况（TjMax 100°C），阈值据此放宽；
> 台式机可把 CPU 档位回调为 60/75/85°C、参考功耗 130W。
> 阈值在 `06_ble_widget.ino` 的 `temp_color(...)` 调用参数和 `pwr_color(...)` 参考功耗处修改。

### 重新生成字体 / 预览效果

```powershell
cd esp32\06_ble_widget\tools
python gen_font.py     # 重新生成 dseg_font.h（需 pip install pillow）
python preview.py      # 生成整屏配色预览图 preview.png
```

---

## 🔌 硬件接线（与之前完全一致，无需改动）

| 屏幕引脚 | ESP32 GPIO | 说明 |
| :--- | :--- | :--- |
| **VCC** | **5V (VIN)** | 必须 5V 供电 |
| **GND** | **GND** | 严禁误插 G0/SD0 |
| **CS** | **GPIO 4** | 片选 |
| **RESET** | **GPIO 17**| 复位 |
| **DC** | **GPIO 16**| 命令/数据 |
| **MOSI** | **GPIO 23**| 数据输入 |
| **SCK** | **GPIO 18**| 时钟 |
| **LED** | **3.3V** | 背光电源 |

---

## 🚀 使用步骤

### 步骤 1：烧录 ESP32 蓝牙固件
1. 打开 Arduino IDE。
2. 打开 `esp32/06_ble_widget/06_ble_widget.ino`。
3. 点击 **“上传”**。
4. 屏幕上会显示：`BLE WAITING...`（等待蓝牙连接）。

### 步骤 2：在电脑上运行蓝牙发射器
1. 确保电脑已开启蓝牙。
2. 打开终端（PowerShell），运行：
   ```powershell
   python c:\Users\Administrator\Desktop\esp32\06_ble_widget\ble_pc_sender.py
   ```
3. 脚本会自动搜索并连接 `ESP32-Dashboard`，副屏随即进入 **0.3 秒超低功耗极速监控模式**！
