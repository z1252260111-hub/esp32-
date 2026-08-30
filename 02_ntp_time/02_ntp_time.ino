#include <WiFi.h>
#include <time.h>

// 纯底层直连引脚 (与 01 完全一致)
#define PIN_CS    4
#define PIN_DC   16
#define PIN_RST  17
#define PIN_MOSI 23
#define PIN_SCK  18

// 简单 5x7 点阵字库，用于绘制清晰数字
static const uint8_t font5x7[11][5] = {
  {0x3E, 0x51, 0x49, 0x45, 0x3E}, // 0
  {0x00, 0x42, 0x7F, 0x40, 0x00}, // 1
  {0x42, 0x61, 0x51, 0x49, 0x46}, // 2
  {0x21, 0x41, 0x45, 0x4B, 0x31}, // 3
  {0x18, 0x14, 0x12, 0x7F, 0x10}, // 4
  {0x27, 0x45, 0x45, 0x45, 0x39}, // 5
  {0x3C, 0x4A, 0x49, 0x49, 0x30}, // 6
  {0x01, 0x71, 0x09, 0x05, 0x03}, // 7
  {0x36, 0x49, 0x49, 0x49, 0x36}, // 8
  {0x06, 0x49, 0x49, 0x29, 0x1E}, // 9
  {0x00, 0x36, 0x36, 0x00, 0x00}  // : (冒号)
};

// ==== 改成你自己的 WiFi ====
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
// ==== 改到这里结束 ====

void spi_write(uint8_t data) {
  for (int i = 0; i < 8; i++) {
    digitalWrite(PIN_SCK, LOW);
    digitalWrite(PIN_MOSI, (data & 0x80) ? HIGH : LOW);
    digitalWrite(PIN_SCK, HIGH);
    data <<= 1;
  }
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

void draw_digit_large(uint16_t x, uint16_t y, int idx, uint16_t color, int scale) {
  if (idx < 0 || idx > 10) return;
  for (int col = 0; col < 5; col++) {
    uint8_t line = font5x7[idx][col];
    for (int row = 0; row < 7; row++) {
      if (line & (1 << row)) {
        fill_rect(x + col * scale, y + row * scale, scale, scale, color);
      } else {
        fill_rect(x + col * scale, y + row * scale, scale, scale, 0x0000);
      }
    }
  }
  // 列间距清黑
  fill_rect(x + 5 * scale, y, scale, 7 * scale, 0x0000);
}

void draw_time_string(uint16_t x, uint16_t y, const char* str, uint16_t color, int scale) {
  uint16_t cur_x = x;
  while (*str) {
    char c = *str++;
    if (c >= '0' && c <= '9') {
      draw_digit_large(cur_x, y, c - '0', color, scale);
      cur_x += 6 * scale;
    } else if (c == ':') {
      draw_digit_large(cur_x, y, 10, color, scale);
      cur_x += 4 * scale;
    } else {
      cur_x += 3 * scale;
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("Starting Direct NTP Clock...");

  pinMode(PIN_CS, OUTPUT);
  pinMode(PIN_DC, OUTPUT);
  pinMode(PIN_RST, OUTPUT);
  pinMode(PIN_MOSI, OUTPUT);
  pinMode(PIN_SCK, OUTPUT);

  // 硬件复位
  digitalWrite(PIN_RST, HIGH);
  delay(50);
  digitalWrite(PIN_RST, LOW);
  delay(100);
  digitalWrite(PIN_RST, HIGH);
  delay(150);

  // 初始化序列
  write_cmd(0x01); delay(150);
  write_cmd(0x11); delay(150);
  write_cmd(0x36); write_data(0xE8); // 旋转180度横屏 (原来是 0x28)
  write_cmd(0x3A); write_data(0x55);
  write_cmd(0x29); delay(50);

  // 清黑屏
  fill_rect(0, 0, 320, 240, 0x0000);
  Serial.println("Screen Inited! Connecting WiFi...");

  WiFi.begin(ssid, password);
  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 30) {
    delay(500);
    Serial.print(".");
    retry++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected! Syncing time...");
    configTime(8 * 3600, 0, "ntp.aliyun.com", "pool.ntp.org");
  } else {
    Serial.println("\nWiFi Failed!");
  }
}

void loop() {
  struct tm t;
  if (getLocalTime(&t)) {
    char buf[12];
    snprintf(buf, sizeof(buf), "%02d:%02d:%02d", t.tm_hour, t.tm_min, t.tm_sec);
    Serial.print("Current Time: ");
    Serial.println(buf);

    // 在屏幕中央 (x=35, y=90) 用 6 倍点阵大字体绘制时间 (亮青色 0x07FF)
    draw_time_string(35, 90, buf, 0x07FF, 6);
  } else {
    Serial.println("Waiting for NTP sync...");
  }
  delay(1000);
}
