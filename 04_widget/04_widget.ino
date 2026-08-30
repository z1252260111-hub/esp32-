// 阶段 4：无线联通 —— 桌面副屏摆件主程序（原生 16x24 超高清大字 + 满屏科技仪表盘）
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// 纯底层直连引脚
#define PIN_CS    4
#define PIN_DC   16
#define PIN_RST  17
#define PIN_MOSI 23
#define PIN_SCK  18

// ESP32 GPIO 输出寄存器直写（比 digitalWrite 快约 50 倍，支撑 0.3s 高刷）
#define W1TS_REG (*(volatile uint32_t*)0x3FF44008)  // GPIO_OUT_W1TS：引脚置 1
#define W1TC_REG (*(volatile uint32_t*)0x3FF4400C)  // GPIO_OUT_W1TC：引脚清 0
#define SCK_BIT  (1u << PIN_SCK)
#define MOSI_BIT (1u << PIN_MOSI)

// ==== 改成你自己的 WiFi 和本机 IP ====
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
const char* pc_url = "http://192.168.X.X:8080";
// =========================================

// 原生 16x24 高清字库 (每个字符 16x24 像素 = 48 字节，1:1 原生大号，零拉伸，边缘极致圆滑清晰)
// 0~9, :, C, P, U, G, M, E, W, %, 空格
static const uint16_t font16x24_digits[10][24] = {
  {0x0000,0x07E0,0x0FF0,0x1C38,0x381C,0x300C,0x6006,0x6006,0x6006,0x6006,0x6006,0x6006,0x6006,0x6006,0x6006,0x6006,0x300C,0x381C,0x1C38,0x0FF0,0x07E0,0x0000,0x0000,0x0000}, // 0
  {0x0000,0x0180,0x0380,0x0780,0x0F80,0x0180,0x0180,0x0180,0x0180,0x0180,0x0180,0x0180,0x0180,0x0180,0x0180,0x0180,0x0180,0x0180,0x0180,0x0FF0,0x0FF0,0x0000,0x0000,0x0000}, // 1
  {0x0000,0x07E0,0x0FF0,0x1C38,0x301C,0x300C,0x000C,0x001C,0x0038,0x0070,0x00E0,0x01C0,0x0380,0x0700,0x0E00,0x1C00,0x3804,0x300C,0x3FFC,0x3FFC,0x3FFC,0x0000,0x0000,0x0000}, // 2
  {0x0000,0x07E0,0x0FF0,0x1C38,0x301C,0x300C,0x000C,0x001C,0x0038,0x07F0,0x07F0,0x001C,0x000C,0x0006,0x0006,0x3006,0x300C,0x381C,0x1C38,0x0FF0,0x07E0,0x0000,0x0000,0x0000}, // 3
  {0x0000,0x0030,0x0070,0x00F0,0x01F0,0x0370,0x0670,0x0C70,0x1870,0x3070,0x6070,0xC070,0x3FFF,0x3FFF,0x0070,0x0070,0x0070,0x0070,0x0070,0x03FC,0x03FC,0x0000,0x0000,0x0000}, // 4
  {0x0000,0x3FFC,0x3FFC,0x3000,0x3000,0x3000,0x3000,0x3000,0x3FE0,0x3FF8,0x001C,0x000C,0x0006,0x0006,0x0006,0x3006,0x300C,0x381C,0x1C38,0x0FF0,0x07E0,0x0000,0x0000,0x0000}, // 5
  {0x0000,0x03F0,0x0FF8,0x1C1C,0x380C,0x3000,0x6000,0x67E0,0x6FF0,0x7838,0x701C,0x600C,0x6006,0x6006,0x6006,0x600C,0x300C,0x3818,0x1C38,0x0FF0,0x07E0,0x0000,0x0000,0x0000}, // 6
  {0x0000,0x3FFC,0x3FFC,0x300C,0x000C,0x0018,0x0030,0x0060,0x00C0,0x0180,0x0300,0x0600,0x0C00,0x1800,0x1800,0x3000,0x3000,0x3000,0x6000,0x6000,0x6000,0x0000,0x0000,0x0000}, // 7
  {0x0000,0x07E0,0x0FF0,0x1C38,0x381C,0x300C,0x300C,0x381C,0x1C38,0x0FF0,0x1FF8,0x381C,0x300C,0x6006,0x6006,0x6006,0x300C,0x381C,0x1C38,0x0FF0,0x07E0,0x0000,0x0000,0x0000}, // 8
  {0x0000,0x07E0,0x0FF0,0x1C38,0x381C,0x300C,0x6006,0x6006,0x6006,0x300E,0x381E,0x1FF6,0x0FE6,0x0006,0x000C,0x000C,0x3018,0x3830,0x1FE0,0x0FC0,0x0700,0x0000,0x0000,0x0000}  // 9
};

static const uint16_t font16x24_colon[24] = 
  {0x0000,0x0000,0x0000,0x0000,0x0180,0x03C0,0x03C0,0x0180,0x0000,0x0000,0x0000,0x0000,0x0180,0x03C0,0x03C0,0x0180,0x0000,0x0000,0x0000,0x0000,0x0000,0x0000,0x0000,0x0000}; // :

static const uint16_t font16x24_C[24] = 
  {0x0000,0x03F0,0x0FF8,0x1C1C,0x380C,0x3006,0x6000,0x6000,0x6000,0x6000,0x6000,0x6000,0x6000,0x6000,0x6000,0x3006,0x380C,0x1C1C,0x0FF8,0x03F0,0x0000,0x0000,0x0000,0x0000}; // C
static const uint16_t font16x24_P[24] = 
  {0x0000,0x3FE0,0x3FF8,0x301C,0x300E,0x3006,0x3006,0x300E,0x301C,0x3FF8,0x3FE0,0x3000,0x3000,0x3000,0x3000,0x3000,0x3000,0x3000,0x3000,0x7800,0x7800,0x0000,0x0000,0x0000}; // P
static const uint16_t font16x24_U[24] = 
  {0x0000,0x300C,0x300C,0x300C,0x300C,0x300C,0x300C,0x300C,0x300C,0x300C,0x300C,0x300C,0x300C,0x300C,0x300C,0x300C,0x300C,0x381C,0x1C38,0x0FF0,0x07E0,0x0000,0x0000,0x0000}; // U
static const uint16_t font16x24_G[24] = 
  {0x0000,0x03F0,0x0FF8,0x1C1C,0x380C,0x3006,0x6000,0x6000,0x6000,0x6000,0x6000,0x63FE,0x63FE,0x6006,0x6006,0x3006,0x380C,0x1C1C,0x0FF8,0x03F0,0x0000,0x0000,0x0000,0x0000}; // G
static const uint16_t font16x24_M[24] = 
  {0x0000,0x6006,0x700E,0x781E,0x6C36,0x6666,0x63C6,0x6186,0x6006,0x6006,0x6006,0x6006,0x6006,0x6006,0x6006,0x6006,0x6006,0x6006,0x6006,0xF00F,0xF00F,0x0000,0x0000,0x0000}; // M
static const uint16_t font16x24_E[24] = 
  {0x0000,0x3FFC,0x3FFC,0x3000,0x3000,0x3000,0x3000,0x3000,0x3FC0,0x3FC0,0x3000,0x3000,0x3000,0x3000,0x3000,0x3000,0x3000,0x3000,0x3FFC,0x3FFC,0x0000,0x0000,0x0000,0x0000}; // E
// 漂亮且标准的 16x24 字母 W
static const uint16_t font16x24_W[24] = {
  0x0000,0x0000,0xC003,0xC003,0xC003,0xC003,0xC003,0xC003,
  0xC003,0xC183,0xC183,0xC3C3,0xC3C3,0x6666,0x6666,0x6666,
  0x3C3C,0x3C3C,0x381C,0x1818,0x0000,0x0000,0x0000,0x0000
};

static const uint16_t font16x24_percent[24] = 
  {0x0000,0x1806,0x3C0C,0x3C18,0x1830,0x0060,0x00C0,0x0180,0x0300,0x0618,0x0C3C,0x183C,0x3018,0x0000,0x0000,0x0000,0x0000,0x0000,0x0000,0x0000,0x0000,0x0000,0x0000,0x0000}; // %

// 温度单位符号 "°"（上标小圆环，供 '^' 占位符使用）
static const uint16_t font16x24_degree_sign[24] = {
  0x0000, 0x0000, 0x0000, 0x03C0, 0x07C0, 0x0E70, 0x0C30, 0x0C30,
  0x0E70, 0x07C0, 0x03C0, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
};
// 16x24 字母 D
static const uint16_t font16x24_D[24] = {
  0x3FF0, 0x3060, 0x3030, 0x3018, 0x300C, 0x3006, 0x3006, 0x3006,
  0x3006, 0x3006, 0x3006, 0x3006, 0x3006, 0x3006, 0x3006, 0x3006,
  0x3006, 0x300C, 0x3018, 0x3030, 0x3060, 0x3FF0, 0x0000, 0x0000
};
// 16x24 字母 N
static const uint16_t font16x24_N[24] = {
  0x3306, 0x3186, 0x30C6, 0x3066, 0x3036, 0x301E, 0x301E, 0x3006,
  0x3006, 0x3006, 0x3006, 0x3006, 0x3006, 0x3006, 0x3006, 0x3006,
  0x3006, 0x3006, 0x3006, 0x3006, 0x3006, 0x0000, 0x0000, 0x0000
};
// 16x24 字母 O
static const uint16_t font16x24_O[24] = {
  0x3FF0, 0x0360, 0x0630, 0x0C18, 0x180C, 0x3006, 0x3006, 0x3006,
  0x3006, 0x3006, 0x3006, 0x3006, 0x3006, 0x3006, 0x3006, 0x3006,
  0x3006, 0x180C, 0x0C18, 0x0630, 0x0360, 0x3FF0, 0x0000, 0x0000
};
// 16x24 字母 A
static const uint16_t font16x24_A[24] = {
  0x0180, 0x0180, 0x0240, 0x0240, 0x0420, 0x0420, 0x0810, 0x0810,
  0xFFFC, 0xFFFC, 0x1008, 0x1008, 0x2004, 0x2004, 0x4002, 0x4002,
  0xC003, 0xC003, 0xC003, 0xC003, 0xC003, 0x0000, 0x0000, 0x0000
};
// 16x24 字母 T
static const uint16_t font16x24_T[24] = {
  0xFFFC, 0xFFFC, 0x0180, 0x0180, 0x0180, 0x0180, 0x0180, 0x0180,
  0x0180, 0x0180, 0x0180, 0x0180, 0x0180, 0x0180, 0x0180, 0x0180,
  0x0180, 0x0180, 0x0180, 0x0180, 0x0180, 0x0000, 0x0000, 0x0000
};

inline void spi_write(uint8_t data) {
  W1TC_REG = SCK_BIT;
  if (data & 0x80) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT;
  W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT;
  if (data & 0x40) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT;
  W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT;
  if (data & 0x20) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT;
  W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT;
  if (data & 0x10) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT;
  W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT;
  if (data & 0x08) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT;
  W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT;
  if (data & 0x04) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT;
  W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT;
  if (data & 0x02) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT;
  W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT;
  if (data & 0x01) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT;
  W1TS_REG = SCK_BIT;
}

void write_cmd(uint8_t cmd) {
  digitalWrite(PIN_DC, LOW);
  digitalWrite(PIN_CS, LOW);
  spi_write(cmd);
  digitalWrite(PIN_CS, HIGH);
}

void write_data(uint8_t data) {
  digitalWrite(PIN_DC, HIGH);
  digitalWrite(PIN_CS, LOW);
  spi_write(data);
  digitalWrite(PIN_CS, HIGH);
}

void set_window(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) {
  write_cmd(0x2A);
  write_data(x0 >> 8); write_data(x0 & 0xFF);
  write_data(x1 >> 8); write_data(x1 & 0xFF);

  write_cmd(0x2B);
  write_data(y0 >> 8); write_data(y0 & 0xFF);
  write_data(y1 >> 8); write_data(y1 & 0xFF);

  write_cmd(0x2C);
}

void fill_rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint16_t color) {
  set_window(x, y, x + w - 1, y + h - 1);
  digitalWrite(PIN_DC, HIGH);
  digitalWrite(PIN_CS, LOW);
  for (uint32_t i = 0; i < (uint32_t)w * h; i++) {
    spi_write(color >> 8);
    spi_write(color & 0xFF);
  }
  digitalWrite(PIN_CS, HIGH);
}

// 高速整字窗口推流绘制 16x24 字符
void draw_char16x24(uint16_t x, uint16_t y, const uint16_t glyph[24], uint16_t color) {
  set_window(x, y, x + 15, y + 23);
  digitalWrite(PIN_DC, HIGH);
  digitalWrite(PIN_CS, LOW);
  for (int row = 0; row < 24; row++) {
    uint16_t line = glyph[row];
    for (int col = 0; col < 16; col++) {
      uint16_t c = (line & (0x8000 >> col)) ? color : 0x0000;
      spi_write(c >> 8);
      spi_write(c & 0xFF);
    }
  }
  digitalWrite(PIN_CS, HIGH);
}

void draw_text16x24(uint16_t x, uint16_t y, const char* str, uint16_t color) {
  uint16_t cur_x = x;
  while (*str) {
    char c = *str++;
    if (c >= '0' && c <= '9') {
      draw_char16x24(cur_x, y, font16x24_digits[c - '0'], color);
      cur_x += 16;
    } else if (c == ':') {
      draw_char16x24(cur_x, y, font16x24_colon, color);
      cur_x += 10;
    } else if (c == 'C') {
      draw_char16x24(cur_x, y, font16x24_C, color);
      cur_x += 16;
    } else if (c == 'P') {
      draw_char16x24(cur_x, y, font16x24_P, color);
      cur_x += 16;
    } else if (c == 'U') {
      draw_char16x24(cur_x, y, font16x24_U, color);
      cur_x += 16;
    } else if (c == 'G') {
      draw_char16x24(cur_x, y, font16x24_G, color);
      cur_x += 16;
    } else if (c == 'M') {
      draw_char16x24(cur_x, y, font16x24_M, color);
      cur_x += 16;
    } else if (c == 'E') {
      draw_char16x24(cur_x, y, font16x24_E, color);
      cur_x += 16;
    } else if (c == 'W') {
      draw_char16x24(cur_x, y, font16x24_W, color);
      cur_x += 16;
    } else if (c == '%') {
      draw_char16x24(cur_x, y, font16x24_percent, color);
      cur_x += 16;
    } else if (c == 'D') {
      draw_char16x24(cur_x, y, font16x24_D, color);
      cur_x += 16;
    } else if (c == 'N') {
      draw_char16x24(cur_x, y, font16x24_N, color);
      cur_x += 16;
    } else if (c == 'O') {
      draw_char16x24(cur_x, y, font16x24_O, color);
      cur_x += 16;
    } else if (c == 'A') {
      draw_char16x24(cur_x, y, font16x24_A, color);
      cur_x += 16;
    } else if (c == 'T') {
      draw_char16x24(cur_x, y, font16x24_T, color);
      cur_x += 16;
    } else if (c == '^') { // '^' 占位符 → 绘制温度单位 "°"
      draw_char16x24(cur_x, y, font16x24_degree_sign, color);
      cur_x += 16;
    } else if (c == ' ') {
      fill_rect(cur_x, y, 6, 24, 0x0000);
      cur_x += 6;
    } else {
      fill_rect(cur_x, y, 6, 24, 0x0000);
      cur_x += 6;
    }
  }
}

// 绘制满屏电竞厚实进度条
void draw_bar(uint16_t x, uint16_t y, uint16_t w, uint16_t h, int percent, uint16_t color) {
  if (percent < 0) percent = 0;
  if (percent > 100) percent = 100;
  uint16_t fill_w = (w * percent) / 100;
  if (fill_w > 0) fill_rect(x, y, fill_w, h, color);
  if (w - fill_w > 0) fill_rect(x + fill_w, y, w - fill_w, h, 0x18E3);
}

void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(PIN_CS, OUTPUT);
  pinMode(PIN_DC, OUTPUT);
  pinMode(PIN_RST, OUTPUT);
  pinMode(PIN_MOSI, OUTPUT);
  pinMode(PIN_SCK, OUTPUT);

  // 硬件复位
  digitalWrite(PIN_RST, HIGH); delay(100);
  digitalWrite(PIN_RST, LOW);  delay(150);
  digitalWrite(PIN_RST, HIGH); delay(200);

  // 初始化 (180度旋转 0xE8)
  write_cmd(0x01); delay(150);
  write_cmd(0x11); delay(150);
  write_cmd(0x36); write_data(0xE8);
  write_cmd(0x3A); write_data(0x55);
  write_cmd(0x29); delay(50);

  fill_rect(0, 0, 320, 240, 0x0000);
  draw_text16x24(60, 100, "CONNECTING...", 0x07FF);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 30) {
    delay(500);
    retry++;
  }

  fill_rect(0, 0, 320, 240, 0x0000);
}

void loop() {
  bool got_data = false;

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.setTimeout(1500);
    http.begin(pc_url);
    int code = http.GET();
    if (code == 200) {
#if ARDUINOJSON_VERSION_MAJOR >= 7
      JsonDocument doc;
#else
      DynamicJsonDocument doc(1024);
#endif
      deserializeJson(doc, http.getString());

      int cpu = doc["cpu"] | 0;
      int mem = doc["mem"] | 0;
      float cpu_t = doc["cpu_temp"] | 0.0f;
      float cpu_w = doc["cpu_pwr"] | 0.0f;
      float gpu_t = doc["gpu_temp"] | 0.0f;
      float gpu_w = doc["gpu_pwr"] | 0.0f;
      int gpu_use = doc["gpu_usage"] | -1;
      const char* t = doc["time"] | "00:00:00";

      // 1. 顶部大号高清时钟 (8 字符共 116px 宽，居中起点 (320-116)/2=102)
      draw_text16x24(102, 8, t, 0x07FF);
      fill_rect(10, 38, 300, 2, 0x31A6); // 科技蓝分割线

      // 2. CPU 区域 (y=44 ~ 98)
      uint16_t cpu_col = cpu > 85 ? 0xF800 : (cpu > 60 ? 0xFFE0 : 0x07E0);
      draw_text16x24(10, 44, "CPU", 0xFFFF);
      char cpu_str[8]; snprintf(cpu_str, sizeof(cpu_str), "%2d%%", cpu);
      draw_text16x24(62, 44, cpu_str, cpu_col);

      // 显示：xx°C xxW（'^' 是 ° 符号的占位符）
      char cpu_metric[20];
      snprintf(cpu_metric, sizeof(cpu_metric), "%2.0f^C %2.0fW", cpu_t, cpu_w);
      draw_text16x24(150, 44, cpu_metric, 0x07FF);
      draw_bar(10, 72, 300, 12, cpu, cpu_col);

      // 3. GPU 区域 (y=98 ~ 152)
      uint16_t gpu_col = (gpu_use > 85) ? 0xF800 : ((gpu_use > 60) ? 0xFFE0 : 0x07E0);
      draw_text16x24(10, 98, "GPU", 0xFFFF);
      if (gpu_use >= 0) {
        char gpu_str[8]; snprintf(gpu_str, sizeof(gpu_str), "%2d%%", gpu_use);
        draw_text16x24(62, 98, gpu_str, gpu_col);
      } else {
        fill_rect(62, 98, 48, 24, 0x0000);
      }

      // 暖橙金显示：xx°C xxW
      char gpu_metric[20];
      snprintf(gpu_metric, sizeof(gpu_metric), "%2.0f^C %2.0fW", gpu_t, gpu_w);
      draw_text16x24(150, 98, gpu_metric, 0xFDA0);
      int bar_val = (gpu_use >= 0) ? gpu_use : (int)(gpu_w / 1.5);
      draw_bar(10, 126, 300, 12, bar_val, (gpu_use >= 0) ? gpu_col : 0xFDA0);

      // 4. MEM 区域 (y=152 ~ 206)
      uint16_t mem_col = mem > 85 ? 0xF800 : (mem > 60 ? 0xFFE0 : 0x07E0);
      draw_text16x24(10, 152, "MEM", 0xFFFF);
      char mem_str[8]; snprintf(mem_str, sizeof(mem_str), "%2d%%", mem);
      draw_text16x24(62, 152, mem_str, mem_col);
      draw_bar(10, 180, 300, 12, mem, mem_col);

      got_data = true;
    }
    http.end();
  }

  if (got_data) {
    fill_rect(109, 210, 102, 24, 0x0000); // 清除底部断连提示
    delay(300);                           // 0.3 秒电竞极速刷新
  } else {
    draw_text16x24(109, 210, "NO DATA", 0xF800); // 断网/电脑服务未开时底部红色提示
    if (WiFi.status() != WL_CONNECTED) {
      WiFi.disconnect();
      WiFi.reconnect();
    }
    delay(1000); // 未取到数据时降低重试频率
  }
}
