// 阶段 6：低功耗蓝牙 (BLE) 桌面副屏（华硕 G-Helper + 游戏 FPS + 16x24 紧凑清晰字模）
// 字体: JetBrains Mono Bold 16x24 (自包含内联，完美适配 320x240，零边缘遮挡)
// 配色: 动态变色 (占用率/温度/功耗/FPS 随数值平滑变色)
// 通信: BLE GATT Server 0.3s 极速推流

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <ArduinoJson.h>

// ============================================================
//  16x24 高清位图字库（JetBrains Mono Bold）
// ============================================================
#define DSEG_CELL_W 16
#define DSEG_CELL_H 24

static const uint32_t DSEG_DIGITS[10][24] = {
  { /* '0' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x07800000, 0x1FE00000, 0x1CE00000, 0x38700000,
  0x38700000, 0x38700000, 0x3B700000, 0x3B700000, 0x38700000, 0x38700000,
  0x38700000, 0x1CE00000, 0x1FE00000, 0x07800000, 0x00000000, 0x00000000
  },
  { /* '1' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x07800000, 0x0F800000, 0x1F800000, 0x1B800000,
  0x13800000, 0x03800000, 0x03800000, 0x03800000, 0x03800000, 0x03800000,
  0x03800000, 0x03800000, 0x1FF00000, 0x1FF00000, 0x00000000, 0x00000000
  },
  { /* '2' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x07800000, 0x1FE00000, 0x1CE00000, 0x38700000,
  0x00700000, 0x00600000, 0x00E00000, 0x01C00000, 0x03800000, 0x07000000,
  0x0E000000, 0x1C000000, 0x3FF00000, 0x3FF00000, 0x00000000, 0x00000000
  },
  { /* '3' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x1FE00000, 0x1FE00000, 0x00E00000, 0x01C00000,
  0x03000000, 0x07800000, 0x07E00000, 0x00E00000, 0x00700000, 0x00700000,
  0x38700000, 0x3CE00000, 0x1FE00000, 0x0F800000, 0x00000000, 0x00000000
  },
  { /* '4' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x01C00000, 0x01800000, 0x03800000, 0x07000000,
  0x0E000000, 0x0E000000, 0x1C600000, 0x38600000, 0x38600000, 0x3FE00000,
  0x3FE00000, 0x00600000, 0x00600000, 0x00600000, 0x00000000, 0x00000000
  },
  { /* '5' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x1FE00000, 0x1FE00000, 0x18000000, 0x18000000,
  0x18000000, 0x1FC00000, 0x1FE00000, 0x00600000, 0x00700000, 0x00700000,
  0x38700000, 0x1CE00000, 0x1FE00000, 0x0F800000, 0x00000000, 0x00000000
  },
  { /* '6' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x03800000, 0x03000000, 0x07000000, 0x06000000,
  0x0E000000, 0x1FC00000, 0x1FE00000, 0x38700000, 0x38700000, 0x38700000,
  0x38700000, 0x3CE00000, 0x1FE00000, 0x07800000, 0x00000000, 0x00000000
  },
  { /* '7' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x3FF00000, 0x3FF00000, 0x38700000, 0x38700000,
  0x00E00000, 0x00E00000, 0x00C00000, 0x01C00000, 0x01800000, 0x03800000,
  0x03000000, 0x07000000, 0x07000000, 0x0E000000, 0x00000000, 0x00000000
  },
  { /* '8' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x0F800000, 0x1FE00000, 0x38700000, 0x38700000,
  0x1FE00000, 0x0FE00000, 0x38700000, 0x38700000, 0x38700000, 0x38700000,
  0x38700000, 0x3CE00000, 0x1FE00000, 0x07800000, 0x00000000, 0x00000000
  },
  { /* '9' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x0F800000, 0x1FE00000, 0x38700000, 0x38700000,
  0x38700000, 0x38700000, 0x1FE00000, 0x0FE00000, 0x00700000, 0x00E00000,
  0x01C00000, 0x03800000, 0x07000000, 0x0E000000, 0x00000000, 0x00000000
  }
};

static const uint32_t DSEG_ALPHA[26][24] = {
  { /* 'A' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x07800000, 0x0FC00000, 0x0FC00000, 0x1BE00000,
  0x1BE00000, 0x18E00000, 0x30700000, 0x3FF00000, 0x3FF00000, 0x30380000,
  0x60180000, 0x601C0000, 0x601C0000, 0x601C0000, 0x00000000, 0x00000000
  },
  { /* 'B' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x1FC00000, 0x1FE00000, 0x18700000, 0x18700000,
  0x1FE00000, 0x1FE00000, 0x18700000, 0x18380000, 0x18380000, 0x18380000,
  0x18700000, 0x1FE00000, 0x1FC00000, 0x1F800000, 0x00000000, 0x00000000
  },
  { /* 'C' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x0F800000, 0x1FE00000, 0x38700000, 0x38700000,
  0x38000000, 0x38000000, 0x38000000, 0x38000000, 0x38000000, 0x38000000,
  0x38700000, 0x38700000, 0x1FE00000, 0x0F800000, 0x00000000, 0x00000000
  },
  { /* 'D' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x1FC00000, 0x1FE00000, 0x18700000, 0x18380000,
  0x18380000, 0x18380000, 0x18380000, 0x18380000, 0x18380000, 0x18380000,
  0x18380000, 0x18700000, 0x1FE00000, 0x1FC00000, 0x00000000, 0x00000000
  },
  { /* 'E' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x1FF00000, 0x1FF00000, 0x18000000, 0x18000000,
  0x18000000, 0x1FE00000, 0x1FE00000, 0x18000000, 0x18000000, 0x18000000,
  0x18000000, 0x18000000, 0x1FF00000, 0x1FF00000, 0x00000000, 0x00000000
  },
  { /* 'F' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x1FF00000, 0x1FF00000, 0x18000000, 0x18000000,
  0x18000000, 0x1FE00000, 0x1FE00000, 0x18000000, 0x18000000, 0x18000000,
  0x18000000, 0x18000000, 0x18000000, 0x18000000, 0x00000000, 0x00000000
  },
  { /* 'G' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x0F800000, 0x1FE00000, 0x38600000, 0x38000000,
  0x38000000, 0x38000000, 0x3BE00000, 0x3BE00000, 0x38700000, 0x38700000,
  0x38700000, 0x38700000, 0x1FE00000, 0x0F800000, 0x00000000, 0x00000000
  },
  { /* 'H' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x18300000, 0x18300000, 0x18300000, 0x18300000,
  0x18300000, 0x1FF00000, 0x1FF00000, 0x18300000, 0x18300000, 0x18300000,
  0x18300000, 0x18300000, 0x18300000, 0x18300000, 0x00000000, 0x00000000
  },
  { /* 'I' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x0FF00000, 0x0FF00000, 0x01800000, 0x01800000,
  0x01800000, 0x01800000, 0x01800000, 0x01800000, 0x01800000, 0x01800000,
  0x01800000, 0x01800000, 0x0FF00000, 0x0FF00000, 0x00000000, 0x00000000
  },
  { /* 'J' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x003E0000, 0x003E0000, 0x00060000, 0x00060000,
  0x00060000, 0x00060000, 0x00060000, 0x00060000, 0x00060000, 0x30060000,
  0x30060000, 0x380E0000, 0x1FFC0000, 0x07F00000, 0x00000000, 0x00000000
  },
  { /* 'K' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x18700000, 0x18E00000, 0x19C00000, 0x1B800000,
  0x1F000000, 0x1FC00000, 0x1FE00000, 0x18F00000, 0x18780000, 0x183C0000,
  0x181E0000, 0x180F0000, 0x18070000, 0x18038000, 0x00000000, 0x00000000
  },
  { /* 'L' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x18000000, 0x18000000, 0x18000000, 0x18000000,
  0x18000000, 0x18000000, 0x18000000, 0x18000000, 0x18000000, 0x18000000,
  0x18000000, 0x18000000, 0x1FF00000, 0x1FF00000, 0x00000000, 0x00000000
  },
  { /* 'M' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x18030000, 0x1C070000, 0x1E0F0000, 0x1B1B0000,
  0x19B30000, 0x18E30000, 0x18E30000, 0x18030000, 0x18030000, 0x18030000,
  0x18030000, 0x18030000, 0x18030000, 0x18030000, 0x00000000, 0x00000000
  },
  { /* 'N' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x18030000, 0x1C030000, 0x1E030000, 0x1B030000,
  0x19830000, 0x18C30000, 0x18630000, 0x18330000, 0x181B0000, 0x180F0000,
  0x18070000, 0x18030000, 0x18030000, 0x18030000, 0x00000000, 0x00000000
  },
  { /* 'O' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x07800000, 0x1FE00000, 0x1CE00000, 0x38700000,
  0x38700000, 0x38700000, 0x38700000, 0x38700000, 0x38700000, 0x38700000,
  0x38700000, 0x1CE00000, 0x1FE00000, 0x07800000, 0x00000000, 0x00000000
  },
  { /* 'P' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x1FC00000, 0x1FE00000, 0x18700000, 0x18380000,
  0x18380000, 0x18700000, 0x1FE00000, 0x1FC00000, 0x18000000, 0x18000000,
  0x18000000, 0x18000000, 0x18000000, 0x18000000, 0x00000000, 0x00000000
  },
  { /* 'Q' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x07800000, 0x1FE00000, 0x1CE00000, 0x38700000,
  0x38700000, 0x38700000, 0x38700000, 0x38700000, 0x38700000, 0x38F00000,
  0x39F00000, 0x1DF00000, 0x1FE00000, 0x07C00000, 0x00780000, 0x003C0000
  },
  { /* 'R' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x1FC00000, 0x1FE00000, 0x18700000, 0x18380000,
  0x18380000, 0x18700000, 0x1FE00000, 0x1FE00000, 0x18700000, 0x18380000,
  0x18380000, 0x18380000, 0x18380000, 0x18380000, 0x00000000, 0x00000000
  },
  { /* 'S' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x0FE00000, 0x1FE00000, 0x38700000, 0x38000000,
  0x3E000000, 0x1FE00000, 0x03F00000, 0x00700000, 0x00700000, 0x38700000,
  0x38700000, 0x3CE00000, 0x1FE00000, 0x0F800000, 0x00000000, 0x00000000
  },
  { /* 'T' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x3FF00000, 0x3FF00000, 0x01800000, 0x01800000,
  0x01800000, 0x01800000, 0x01800000, 0x01800000, 0x01800000, 0x01800000,
  0x01800000, 0x01800000, 0x01800000, 0x01800000, 0x00000000, 0x00000000
  },
  { /* 'U' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x18300000, 0x18300000, 0x18300000, 0x18300000,
  0x18300000, 0x18300000, 0x18300000, 0x18300000, 0x18300000, 0x18300000,
  0x18300000, 0x1CE00000, 0x1FE00000, 0x07800000, 0x00000000, 0x00000000
  },
  { /* 'V' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x30180000, 0x30180000, 0x18300000, 0x18300000,
  0x0C600000, 0x0C600000, 0x0EE00000, 0x06C00000, 0x06C00000, 0x07C00000,
  0x03800000, 0x03800000, 0x03800000, 0x01000000, 0x00000000, 0x00000000
  },
  { /* 'W' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x308C0000, 0x308C0000, 0x19980000, 0x1DB80000,
  0x1DB80000, 0x1DB80000, 0x1DB80000, 0x1B180000, 0x1B180000, 0x1B180000,
  0x1B180000, 0x0E1C0000, 0x0E1C0000, 0x0E1C0000, 0x00000000, 0x00000000
  },
  { /* 'X' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x30180000, 0x38380000, 0x1C700000, 0x0EE00000,
  0x07C00000, 0x03800000, 0x07C00000, 0x0EE00000, 0x1C700000, 0x38380000,
  0x30180000, 0x30180000, 0x30180000, 0x30180000, 0x00000000, 0x00000000
  },
  { /* 'Y' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x300C0000, 0x381C0000, 0x1C380000, 0x0E700000,
  0x07E00000, 0x03C00000, 0x01800000, 0x01800000, 0x01800000, 0x01800000,
  0x01800000, 0x01800000, 0x01800000, 0x01800000, 0x00000000, 0x00000000
  },
  { /* 'Z' */
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000,
  0x00000000, 0x00000000, 0x1FF00000, 0x1FF00000, 0x00E00000, 0x01C00000,
  0x03800000, 0x07000000, 0x0E000000, 0x1C000000, 0x38000000, 0x70000000,
  0x1FF00000, 0x1FF00000, 0x1FF00000, 0x00000000, 0x00000000, 0x00000000
  }
};

static const uint32_t DSEG_COLON[24] = {
  0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,
  0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,0x03000000,
  0x07800000,0x03000000,0x00000000,0x00000000,0x00000000,0x00000000,
  0x00000000,0x03000000,0x07800000,0x03000000,0x00000000,0x00000000
};

static const uint32_t DSEG_DOT[24] = {
  0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,
  0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,
  0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,
  0x03000000,0x07800000,0x07800000,0x03000000,0x00000000,0x00000000
};

static const uint32_t DSEG_PCT[24] = {
  0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,
  0x00000000,0x00000000,0x3C180000,0x7E300000,0x66600000,0x66400000,
  0x7EC00000,0x3D800000,0x03000000,0x03F00000,0x07F80000,0x0D980000,
  0x09980000,0x19980000,0x31F80000,0x60F00000,0x00000000,0x00000000
};

static const uint32_t DSEG_MINUS[24] = {
  0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,
  0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,
  0x00000000,0x00000000,0x0FC00000,0x0FC00000,0x00000000,0x00000000,
  0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,0x00000000
};

static const uint32_t DSEG_LBRACKET[24] = {
  0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,
  0x00000000,0x00000000,0x0FE00000,0x0FE00000,0x0C000000,0x0C000000,
  0x0C000000,0x0C000000,0x0C000000,0x0C000000,0x0C000000,0x0C000000,
  0x0C000000,0x0C000000,0x0FE00000,0x0FE00000,0x00000000,0x00000000
};

static const uint32_t DSEG_RBRACKET[24] = {
  0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,0x00000000,
  0x00000000,0x00000000,0x1FC00000,0x1FC00000,0x00C00000,0x00C00000,
  0x00C00000,0x00C00000,0x00C00000,0x00C00000,0x00C00000,0x00C00000,
  0x00C00000,0x00C00000,0x1FC00000,0x1FC00000,0x00000000,0x00000000
};

inline const uint32_t* dseg_glyph(char c, uint8_t* adv) {
  if (c >= '0' && c <= '9') { *adv = 16; return DSEG_DIGITS[c - '0']; }
  if (c >= 'a' && c <= 'z') c -= 32;
  if (c >= 'A' && c <= 'Z') { *adv = 16; return DSEG_ALPHA[c - 'A']; }
  switch (c) {
    case ':': *adv = 16; return DSEG_COLON;
    case '.': *adv = 16; return DSEG_DOT;
    case '%': *adv = 16; return DSEG_PCT;
    case '-': *adv = 16; return DSEG_MINUS;
    case '[': *adv = 12; return DSEG_LBRACKET;
    case ']': *adv = 12; return DSEG_RBRACKET;
    default:  *adv = 8;  return nullptr;
  }
}

// 硬件引脚定义
#define PIN_CS    4
#define PIN_DC   16
#define PIN_RST  17
#define PIN_MOSI 23
#define PIN_SCK  18

#define W1TS_REG (*(volatile uint32_t*)0x3FF44008)
#define W1TC_REG (*(volatile uint32_t*)0x3FF4400C)
#define SCK_BIT  (1u << PIN_SCK)
#define MOSI_BIT (1u << PIN_MOSI)

#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

bool deviceConnected = false;
bool oldDeviceConnected = false;
String receivedData = "";
bool newDataAvailable = false;

inline void spi_write(uint8_t data) {
  W1TC_REG = SCK_BIT; if (data & 0x80) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT; W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT; if (data & 0x40) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT; W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT; if (data & 0x20) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT; W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT; if (data & 0x10) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT; W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT; if (data & 0x08) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT; W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT; if (data & 0x04) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT; W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT; if (data & 0x02) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT; W1TS_REG = SCK_BIT;
  W1TC_REG = SCK_BIT; if (data & 0x01) W1TS_REG = MOSI_BIT; else W1TC_REG = MOSI_BIT; W1TS_REG = SCK_BIT;
}

void write_cmd(uint8_t cmd) {
  digitalWrite(PIN_DC, LOW); digitalWrite(PIN_CS, LOW); spi_write(cmd); digitalWrite(PIN_CS, HIGH);
}
void write_data(uint8_t data) {
  digitalWrite(PIN_DC, HIGH); digitalWrite(PIN_CS, LOW); spi_write(data); digitalWrite(PIN_CS, HIGH);
}
void set_window(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) {
  write_cmd(0x2A); write_data(x0 >> 8); write_data(x0 & 0xFF); write_data(x1 >> 8); write_data(x1 & 0xFF);
  write_cmd(0x2B); write_data(y0 >> 8); write_data(y0 & 0xFF); write_data(y1 >> 8); write_data(y1 & 0xFF);
  write_cmd(0x2C);
}
void fill_rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint16_t color) {
  set_window(x, y, x + w - 1, y + h - 1);
  digitalWrite(PIN_DC, HIGH); digitalWrite(PIN_CS, LOW);
  for (uint32_t i = 0; i < (uint32_t)w * h; i++) {
    spi_write(color >> 8); spi_write(color & 0xFF);
  }
  digitalWrite(PIN_CS, HIGH);
}

void draw_char(uint16_t x, uint16_t y, const uint32_t glyph[], uint16_t color) {
  set_window(x, y, x + DSEG_CELL_W - 1, y + DSEG_CELL_H - 1);
  digitalWrite(PIN_DC, HIGH); digitalWrite(PIN_CS, LOW);
  for (int row = 0; row < DSEG_CELL_H; row++) {
    uint32_t line = glyph[row];
    for (int col = 0; col < DSEG_CELL_W; col++) {
      uint16_t c = (line & (0x80000000u >> col)) ? color : 0x0000;
      spi_write(c >> 8); spi_write(c & 0xFF);
    }
  }
  digitalWrite(PIN_CS, HIGH);
}

void draw_text(uint16_t x, uint16_t y, const char* str, uint16_t color) {
  uint16_t cur_x = x;
  while (*str) {
    uint8_t adv;
    const uint32_t* glyph = dseg_glyph(*str++, &adv);
    if (glyph) {
      draw_char(cur_x, y, glyph, color);
    } else {
      fill_rect(cur_x, y, adv, DSEG_CELL_H, 0x0000);
    }
    cur_x += adv;
  }
}

// 动态变色逻辑
uint16_t usage_color(int v) {
  return v > 85 ? 0xF800 : (v > 60 ? 0xFFE0 : 0x07E0);
}
uint16_t temp_color(float t, float yellow_c, float orange_c, float red_c) {
  return t >= red_c ? 0xF800 : (t >= orange_c ? 0xFDA0 :
         (t >= yellow_c ? 0xFFE0 : 0x07FF));
}
uint16_t pwr_color(float w, float ref) {
  float r = w / ref;
  return r >= 0.75f ? 0xF800 : (r >= 0.35f ? 0xFDA0 : 0x07FF);
}
uint16_t fps_color(int fps) {
  return fps >= 120 ? 0x07E0 : (fps >= 60 ? 0x07FF : (fps >= 30 ? 0xFFE0 : 0xF800));
}

void draw_bar(uint16_t x, uint16_t y, uint16_t w, uint16_t h, int percent, uint16_t color) {
  if (percent < 0) percent = 0; if (percent > 100) percent = 100;
  uint16_t fill_w = (w * percent) / 100;
  if (fill_w > 0) fill_rect(x, y, fill_w, h, color);
  if (w - fill_w > 0) fill_rect(x + fill_w, y, w - fill_w, h, 0x18E3);
}

// BLE 服务回调
class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
      Serial.println("BLE Client Connected!");
    };
    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
      Serial.println("BLE Client Disconnected!");
    }
};

class MyCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
      String rxValue = String(pCharacteristic->getValue().c_str());
      if (rxValue.length() > 0) {
        receivedData = rxValue;
        newDataAvailable = true;
      }
    }
};

void setup() {
  Serial.begin(115200);
  delay(300);

  pinMode(PIN_CS, OUTPUT);
  pinMode(PIN_DC, OUTPUT);
  pinMode(PIN_RST, OUTPUT);
  pinMode(PIN_MOSI, OUTPUT);
  pinMode(PIN_SCK, OUTPUT);

  // 硬件复位屏幕
  digitalWrite(PIN_RST, HIGH); delay(50);
  digitalWrite(PIN_RST, LOW);  delay(100);
  digitalWrite(PIN_RST, HIGH); delay(150);

  // 180度横屏 (0xE8)
  write_cmd(0x01); delay(120);
  write_cmd(0x11); delay(120);
  write_cmd(0x36); write_data(0xE8);
  write_cmd(0x3A); write_data(0x55);
  write_cmd(0x29); delay(50);

  fill_rect(0, 0, 320, 240, 0x0000);
  draw_text(16, 100, "BLE WAITING...", 0x07FF);

  // 初始化 BLE 服务
  BLEDevice::init("ESP32-Dashboard");
  BLEServer *pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService *pService = pServer->createService(SERVICE_UUID);
  BLECharacteristic *pCharacteristic = pService->createCharacteristic(
                                         CHARACTERISTIC_UUID,
                                         BLECharacteristic::PROPERTY_READ |
                                         BLECharacteristic::PROPERTY_WRITE |
                                         BLECharacteristic::PROPERTY_NOTIFY
                                       );
  pCharacteristic->setCallbacks(new MyCallbacks());
  pCharacteristic->addDescriptor(new BLE2902());
  pService->start();

  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);
  pAdvertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();
}

void loop() {
  if (newDataAvailable) {
    newDataAvailable = false;

#if ARDUINOJSON_VERSION_MAJOR >= 7
    JsonDocument doc;
#else
    DynamicJsonDocument doc(512);
#endif
    DeserializationError error = deserializeJson(doc, receivedData);

    if (!error) {
      int fps = doc["fps"] | 0;
      int cpu = doc["cpu"] | 0;
      int mem = doc["mem"] | 0;
      float cpu_t = doc["cpu_temp"] | 0.0f;
      float cpu_w = doc["cpu_pwr"] | 0.0f;
      float gpu_t = doc["gpu_temp"] | 0.0f;
      float gpu_w = doc["gpu_pwr"] | 0.0f;
      int gpu_use = doc["gpu_usage"] | -1;
      const char* mode = doc["mode"] | "TURBO";
      const char* t = doc["time"] | "00:00:00";

      // 1. 顶部 Header (y = 8 ~ 32)
      draw_text(10, 8, t, 0x07FF); // 完整时间 8 字符 = 128px (x: 10 ~ 138)

      if (fps > 0) {
        // 游戏状态: 右侧显示 144 FPS (宽约 112px, x: 196 ~ 308)
        char fps_str[10];
        snprintf(fps_str, sizeof(fps_str), "%3d FPS", fps > 999 ? 999 : fps);
        draw_text(196, 8, fps_str, fps_color(fps));
      } else {
        // 桌面状态: 右侧显示 G-Helper 模式 (例如 [TURBO] / [FULL] / [BAL])
        char mode_str[10];
        snprintf(mode_str, sizeof(mode_str), "[%-5s]", mode);
        uint16_t mode_color = strcmp(mode, "TURBO") == 0 ? 0xF800 : (strcmp(mode, "FULL") == 0 ? 0xFDA0 : 0x07E0);
        draw_text(196, 8, mode_str, mode_color);
      }
      fill_rect(10, 36, 300, 2, 0x31A6); // 科技蓝细分割线

      // 2. CPU 区域 (y = 44 ~ 90)
      draw_text(10, 44, "CPU", 0xFFFF);
      char cpu_str[8]; snprintf(cpu_str, sizeof(cpu_str), "%2d%%", cpu > 99 ? 99 : cpu);
      draw_text(74, 44, cpu_str, usage_color(cpu));

      char cpu_tstr[8]; snprintf(cpu_tstr, sizeof(cpu_tstr), "%2.0fC", cpu_t > 99 ? 99 : cpu_t);
      draw_text(144, 44, cpu_tstr, temp_color(cpu_t, 70, 78, 88));

      char cpu_wstr[8]; snprintf(cpu_wstr, sizeof(cpu_wstr), "%3.0fW", cpu_w > 999 ? 999 : cpu_w);
      draw_text(214, 44, cpu_wstr, pwr_color(cpu_w, 160));
      draw_bar(10, 74, 300, 12, cpu, usage_color(cpu));

      // 3. GPU 区域 (y = 96 ~ 142)
      draw_text(10, 96, "GPU", 0xFFFF);
      if (gpu_use >= 0) {
        char gpu_str[8]; snprintf(gpu_str, sizeof(gpu_str), "%2d%%", gpu_use > 99 ? 99 : gpu_use);
        draw_text(74, 96, gpu_str, usage_color(gpu_use));
      } else {
        fill_rect(74, 96, 48, 24, 0x0000);
      }

      char gpu_tstr[8]; snprintf(gpu_tstr, sizeof(gpu_tstr), "%2.0fC", gpu_t > 99 ? 99 : gpu_t);
      draw_text(144, 96, gpu_tstr, temp_color(gpu_t, 60, 75, 85));

      char gpu_wstr[8]; snprintf(gpu_wstr, sizeof(gpu_wstr), "%3.0fW", gpu_w > 999 ? 999 : gpu_w);
      draw_text(214, 96, gpu_wstr, pwr_color(gpu_w, 150));
      int bar_val = (gpu_use >= 0) ? gpu_use : (int)(gpu_w / 1.5);
      draw_bar(10, 126, 300, 12, bar_val, (gpu_use >= 0) ? usage_color(gpu_use) : pwr_color(gpu_w, 150));

      // 4. MEM 区域 (y = 148 ~ 194) (不显示风扇转速，保持极简清爽)
      draw_text(10, 148, "MEM", 0xFFFF);
      char mem_str[8]; snprintf(mem_str, sizeof(mem_str), "%2d%%", mem > 99 ? 99 : mem);
      draw_text(74, 148, mem_str, usage_color(mem));
      fill_rect(144, 148, 166, 24, 0x0000); // 清理旧残留
      draw_bar(10, 178, 300, 12, mem, usage_color(mem));
    }
  }

  // 断开后重新广播
  if (!deviceConnected && oldDeviceConnected) {
    delay(500);
    BLEDevice::startAdvertising();
    fill_rect(0, 0, 320, 240, 0x0000);
    draw_text(16, 100, "BLE WAITING...", 0x07FF);
    oldDeviceConnected = deviceConnected;
  }
  if (deviceConnected && !oldDeviceConnected) {
    oldDeviceConnected = deviceConnected;
    fill_rect(0, 0, 320, 240, 0x0000);
  }
  delay(10);
}
