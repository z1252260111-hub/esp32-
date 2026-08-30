# -*- coding: utf-8 -*-
"""
preview.py — 用生成的字库模拟 320x240 整屏效果（与 .ino 布局/配色一致）
输出: preview.png (3x 放大便于查看)
用法: python tools/preview.py   (需先运行 gen_font.py 生成 glyphs.json)
"""
import json
import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 320, 240

# RGB565 -> RGB888
def rgb(v):
    r, g, b = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
    return (r * 255 // 31, g * 255 // 63, b * 255 // 31)

CYAN, GREEN, YELLOW = 0x07FF, 0x07E0, 0xFFE0
ORANGE, RED, WHITE, TRACK = 0xFDA0, 0xF800, 0xFFFF, 0x18E3
DIVIDER = 0x31A6

with open(os.path.join(HERE, "glyphs.json")) as f:
    _data = json.load(f)
    GLYPHS = _data["glyphs"]
    ADVS = _data["advs"]
    CW, CH = _data["cell_w"], _data["cell_h"]

def ADV(c):
    if c == ' ':
        return CW // 2
    return ADVS.get(c, CW)

def text_w(s):
    return sum(ADV(c) for c in s)

def draw_text(img, x, y, s, color):
    px = img.load()
    col = rgb(color)
    for ch in s:
        rows = GLYPHS.get(ch)
        if rows:
            for r, bits in enumerate(rows):
                for c in range(CW):
                    if bits & (0x80000000 >> c):
                        px[x + c, y + r] = col
        x += ADV(ch)

def draw_bar(img, x, y, w, h, pct, color):
    px = img.load()
    fw = w * pct // 100
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            px[xx, yy] = rgb(color if xx < x + fw else TRACK)

# —— 与 .ino 相同的动态配色逻辑 (i7-14650HX 笔记本标定) ——
def usage_color(v):   return RED if v > 85 else (YELLOW if v > 60 else GREEN)
def temp_color(t, y_c, o_c, r_c):
    return RED if t >= r_c else (ORANGE if t >= o_c else (YELLOW if t >= y_c else CYAN))
def pwr_color(w, ref):
    r = w / ref
    return RED if r >= 0.75 else (ORANGE if r >= 0.35 else CYAN)

X_LABEL, X_USAGE, X_TEMP, X_PWR = 8, 80, 150, 222
Y0, BAR_DY, BAR_H = 48, 37, 14

def render(cpu, cpu_t, cpu_w, gpu_use, gpu_t, gpu_w, mem, tstr):
    img = Image.new("RGB", (W, H), (0, 0, 0))

    # 1. 顶部时钟（居中）+ 分割线
    draw_text(img, (W - text_w(tstr)) // 2, 6, tstr, CYAN)
    for xx in range(8, 312):
        img.putpixel((xx, 43), rgb(DIVIDER))
        img.putpixel((xx, 44), rgb(DIVIDER))

    # 2/3/4. CPU / GPU / MEM (y = 48 / 104 / 160)
    rows = [
        (Y0,        "CPU", cpu,      cpu_t,  cpu_w,  70, 78, 88, 160),  # i7-14650HX
        (Y0 + 56,   "GPU", gpu_use,  gpu_t,  gpu_w,  60, 75, 85, 150),  # 笔记本独显
        (Y0 + 112,  "MEM", mem,      None,   None,   0, 0, 0, 0),
    ]
    for y, label, use, t, w_, y_c, o_c, r_c, ref in rows:
        draw_text(img, X_LABEL, y, label, WHITE)
        if use >= 0:
            draw_text(img, X_USAGE, y, "%2d%%" % min(use, 99), usage_color(use))
        if t is not None:
            draw_text(img, X_TEMP, y, "%2.0fC" % min(t, 99), temp_color(t, y_c, o_c, r_c))
            draw_text(img, X_PWR, y, "%2.0fW" % w_, pwr_color(w_, ref))
        draw_bar(img, 8, y + BAR_DY, 304, BAR_H,
                 use if use >= 0 else 0, usage_color(use))
    return img

if __name__ == "__main__":
    # 笔记本游戏工况示例 (i7-14650HX): CPU 82C=橙, 95W=橙 | GPU 76C=橙, 110W=橙 | MEM 绿
    img = render(cpu=62, cpu_t=82, cpu_w=95,
                 gpu_use=88, gpu_t=76, gpu_w=110,
                 mem=43, tstr="22:43:41")
    out = os.path.join(HERE, "preview.png")
    img.resize((W * 3, H * 3), Image.NEAREST).save(out)
    print("已生成:", out)
