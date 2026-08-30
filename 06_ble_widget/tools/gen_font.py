# -*- coding: utf-8 -*-
"""
gen_font.py — 把开源字体渲染成位图字库 dseg_font.h
用法:
  python gen_font.py [dseg|jbmono] [单元格宽] [单元格高]
  python gen_font.py jbmono 22 33   # 现代清晰风格, 22x33 大字号(默认 16x24)
依赖: Pillow (pip install pillow)
"""
import json
import os
import sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
F7 = os.path.join(HERE, "dseg_fonts", "fonts-DSEG_v046",
                  "DSEG7-Classic", "DSEG7Classic-Bold.ttf")
F14 = os.path.join(HERE, "dseg_fonts", "fonts-DSEG_v046",
                   "DSEG14-Classic", "DSEG14Classic-Bold.ttf")
FJB = os.path.join(HERE, "jbmono_fonts", "fonts", "ttf", "JetBrainsMono-Bold.ttf")
OUT_H = os.path.join(HERE, "..", "dseg_font.h")

CELL_W = 16   # 与 .ino 绘图引擎一致，可由命令行覆盖
CELL_H = 24
INK_H_MAX = CELL_H - 6     # 字高上限（顶部留白 + 基线下留 2 行）
INK_W_MAX = CELL_W - 2     # 字宽上限（左右各留 1px）
BASELINE_ROW = CELL_H - 2  # 字符底边所在行

# 各模式的字体与符号配置: char -> (字体组名, 步进宽度, 是否在步进内居中)
# 步进宽度 -1 = 跟随单元格宽
MODES = {
    "dseg": {
        "fonts": {"7": F7, "14": F14},
        "groups": [("0123456789", "7"), ("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "14")],
        # 注意: DSEG7 的 '%' 是占位方框（七段码画不出百分号），必须用 DSEG14
        "symbols": {":": ("7", -1, True), ".": ("7", -2, True),
                    "%": ("14", -1, False), "-": ("14", -1, False),
                    "?": ("14", -1, False)},
        "banner": "DSEG7 Classic Bold + DSEG14 Classic Bold (LCD 仪表风格)",
    },
    "jbmono": {
        "fonts": {"jb": FJB},
        "groups": [("0123456789", "jb"), ("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "jb")],
        # 等宽字体: 所有字符同宽, 冒号/句点由字体自然居中
        "symbols": {":": ("jb", -1, False), ".": ("jb", -1, False),
                    "%": ("jb", -1, False), "-": ("jb", -1, False),
                    "?": ("jb", -1, False)},
        "banner": "JetBrains Mono Bold (现代清晰等宽风格)",
    },
}

CANVAS_BL = 40  # 大画布中基线的 y 坐标


def load_best(path, chars):
    """找最大字号，使 chars 中所有字形宽高都在限制内"""
    for size in range(60, 7, -1):
        font = ImageFont.truetype(path, size)
        ok = True
        for ch in chars:
            bbox = probe(font, ch)
            if bbox is None:
                ok = False
                break
            x0, y0, x1, y1 = bbox
            if (x1 - x0) > INK_W_MAX or (y1 - y0) > INK_H_MAX:
                ok = False
                break
        if ok:
            return font
    raise RuntimeError("字号搜索失败: " + path)


def probe(font, ch):
    """在大画布上按基线锚点渲染，返回墨迹包围盒"""
    img = Image.new("1", (80, 80), 0)
    ImageDraw.Draw(img).text((10, CANVAS_BL), ch, font=font, fill=1, anchor="ls")
    return img.getbbox()


def render_cell(font, ch, origin_x=None, adv=None, center_h=False):
    """渲染单个字符到位图行数组（最高位=最左像素），保持基线对齐。
    origin_x: 字体共享原点(画布x)，字符保持字体内的自然水平位置
    center_h: 窄字符在步进宽度内水平居中"""
    if adv is None:
        adv = CELL_W
    img = Image.new("1", (80, 80), 0)
    ImageDraw.Draw(img).text((10, CANVAS_BL), ch, font=font, fill=1, anchor="ls")
    bbox = img.getbbox()
    if bbox is None:
        return None
    x0, _, x1, _ = bbox
    ink_w = x1 - x0
    if origin_x is None:
        origin_x = x0 - 1
    rows = []
    for r in range(CELL_H):
        cy = CANVAS_BL - BASELINE_ROW + r
        bits = 0
        for c in range(CELL_W):
            if center_h:
                cx = x0 - 1 + (c - max(0, (adv - ink_w) // 2))
            else:
                cx = origin_x + c
            if 0 <= cy < 80 and 0 <= cx < 80 and img.getpixel((cx, cy)):
                bits |= 0x80000000 >> c   # 32位行, 支持最宽 32px 单元格
        rows.append(bits)
    return rows


def fmt(name, rows):
    lines = ",\n  ".join(",".join("0x%08X" % v for v in rows[i:i + 6])
                          for i in range(0, len(rows), 6))
    return "static const uint32_t %s[%d] = {\n  %s\n};" % (name, len(rows), lines)


def ascii_art(rows):
    return ["".join("#" if bits & (0x80000000 >> c) else "."
                    for c in range(CELL_W)) for bits in rows]


def main():
    global CELL_W, CELL_H, INK_W_MAX, INK_H_MAX, BASELINE_ROW
    mode = sys.argv[1] if len(sys.argv) > 1 else "dseg"
    if mode not in MODES:
        raise SystemExit("未知模式: %s (可选: %s)" % (mode, "/".join(MODES)))
    if len(sys.argv) > 3:
        CELL_W, CELL_H = int(sys.argv[2]), int(sys.argv[3])
        INK_W_MAX = CELL_W - 2
        INK_H_MAX = CELL_H - 6
        BASELINE_ROW = CELL_H - 2
    cfg = MODES[mode]
    digits = "0123456789"
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def resolve_adv(v):
        if v == -1:
            return CELL_W
        if v == -2:
            return CELL_W // 2
        return v

    fonts = {k: load_best(p, digits + letters + "".join(cfg["symbols"]))
             for k, p in cfg["fonts"].items()}
    for k, f in fonts.items():
        print("字体组[%s] %s 选中字号: %d" % (k, os.path.basename(f.path), f.size))

    # 每种字体取所有字形最左墨迹作为共享原点（保持字体内自然水平位置）
    def shared_origin(font, chars):
        xs = [probe(font, ch)[0] for ch in chars if probe(font, ch)]
        return min(xs) - 1
    origins = {k: shared_origin(f, digits + letters + "".join(cfg["symbols"]))
               for k, f in fonts.items()}

    glyphs, advs = {}, {}
    for chars, key in cfg["groups"]:
        for ch in chars:
            glyphs[ch] = render_cell(fonts[key], ch, origins[key])
            advs[ch] = CELL_W
    for ch, (key, adv_v, center) in cfg["symbols"].items():
        adv = resolve_adv(adv_v)
        r = render_cell(fonts[key], ch, origins[key], adv, center)
        if r and any(r):
            glyphs[ch] = r
            advs[ch] = adv

    # ASCII 预览关键字形，人工核对
    for ch in "0147%:CPUWGM.":
        if ch in glyphs:
            print("char '%s'" % ch)
            for line in ascii_art(glyphs[ch]):
                print("  " + line)

    # —— 生成 dseg_font.h ——
    def rows_str(rows):
        vals = ["0x%08X" % v for v in rows]
        lines = [", ".join(vals[i:i + 6]) for i in range(0, len(vals), 6)]
        return ",\n  ".join(lines)

    def fmt_table(name, size, chars):
        body = []
        for ch in chars:
            body.append("  { /* '%s' */\n  %s\n  }" % (ch, rows_str(glyphs[ch])))
        return "static const uint32_t %s[%d][%d] = {\n%s\n};" % (
            name, size, CELL_H, ",\n".join(body))

    parts = []
    parts.append("""// ============================================================
//  %dx%d 位图字库（脚本自动生成，勿手改）
//  字体: %s
//  许可: SIL Open Font License 1.1
//  重新生成: python tools/gen_font.py %s %d %d
//  行格式: uint32_t，最高位 = 单元格最左列像素
// ============================================================
#define DSEG_CELL_W %d
#define DSEG_CELL_H %d""" % (CELL_W, CELL_H, cfg["banner"], mode, CELL_W, CELL_H,
                             CELL_W, CELL_H))

    parts.append(fmt_table("DSEG_DIGITS", 10, digits))
    parts.append(fmt_table("DSEG_ALPHA", 26, letters))

    sym_names = {":": "DSEG_COLON", ".": "DSEG_DOT", "%": "DSEG_PCT",
                 "-": "DSEG_MINUS", "?": "DSEG_QMARK"}
    for ch, name in sym_names.items():
        if ch in glyphs:
            parts.append(fmt(name, glyphs[ch]))

    switch_lines = []
    for ch, name in sym_names.items():
        if ch in glyphs:
            switch_lines.append("    case '%s': *adv = %d; return %s;"
                                % (ch, advs[ch], name))
    parts.append("""
// 字符查找表：返回 %d 行位图；adv = 绘制步进宽度(像素)
// 空格与未知字符返回 nullptr（调用方用黑色矩形擦除）
inline const uint32_t* dseg_glyph(char c, uint8_t* adv) {
  if (c >= '0' && c <= '9') { *adv = %d; return DSEG_DIGITS[c - '0']; }
  if (c >= 'A' && c <= 'Z') { *adv = %d; return DSEG_ALPHA[c - 'A']; }
  switch (c) {
%s
    default:  *adv = %d;  return nullptr;
  }
}""" % (CELL_H, advs.get("0", CELL_W), advs.get("A", CELL_W),
        "\n".join(switch_lines), CELL_W // 2))

    with open(OUT_H, "w", encoding="utf-8") as f:
        f.write("\n\n".join(parts) + "\n")
    print("\n已生成:", os.path.abspath(OUT_H))

    # 供 preview.py 复用（字形 + 步进宽度 + 单元格尺寸）
    with open(os.path.join(HERE, "glyphs.json"), "w") as f:
        json.dump({"glyphs": glyphs, "advs": advs,
                   "cell_w": CELL_W, "cell_h": CELL_H}, f)
    print("已生成: glyphs.json (预览脚本用)")


if __name__ == "__main__":
    main()
