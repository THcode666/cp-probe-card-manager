"""生成软件图标：小仓库 + 小芯片（简笔画风格）。

产出：
    assets/app.ico      多尺寸 Windows 图标（256/128/64/48/32/16）
    assets/preview.png  预览图（开发时人工检查用）

运行：python tools/make_icon.py（依赖 Pillow：pip install pillow）
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")  # 仓库根目录/assets

BLUE = (31, 78, 121, 255)     # 仓库：与应用主题一致 #1F4E79
GOLD = (242, 166, 60, 255)    # 芯片：暖金色 #F2A63C
S = 512  # 先画大图再缩小，边缘更平滑


def draw_icon() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ---------- 仓库（简笔画：人字屋顶 + 两侧墙 + 地面） ----------
    lw = 26
    d.line([(60, 232), (256, 96), (452, 232)], fill=BLUE, width=lw, joint="curve")
    d.line([(92, 210), (92, 432)], fill=BLUE, width=lw)
    d.line([(420, 210), (420, 432)], fill=BLUE, width=lw)
    d.line([(56, 436), (456, 436)], fill=BLUE, width=lw)

    # ---------- 芯片（居中：圆角方块 + 四边引脚 + 内芯） ----------
    cx, cy, half = 256, 320, 84
    pin_w = 18
    for off in (-42, 0, 42):
        # 上/下引脚
        d.line([(cx + off, cy - half - 30), (cx + off, cy - half + 6)], fill=GOLD, width=pin_w)
        d.line([(cx + off, cy + half - 6), (cx + off, cy + half + 30)], fill=GOLD, width=pin_w)
        # 左/右引脚
        d.line([(cx - half - 30, cy + off), (cx - half + 6, cy + off)], fill=GOLD, width=pin_w)
        d.line([(cx + half - 6, cy + off), (cx + half + 30, cy + off)], fill=GOLD, width=pin_w)
    d.rounded_rectangle(
        [cx - half, cy - half, cx + half, cy + half], radius=18, outline=GOLD, width=pin_w
    )
    d.rounded_rectangle(
        [cx - 38, cy - 38, cx + 38, cy + 38], radius=8, outline=GOLD, width=14
    )
    return img


def main() -> None:
    os.makedirs(ASSETS, exist_ok=True)
    base = draw_icon()

    ico_path = os.path.join(ASSETS, "app.ico")
    base.save(
        ico_path,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    base.resize((256, 256), Image.LANCZOS).save(os.path.join(ASSETS, "preview.png"))
    print("saved:", ico_path)


if __name__ == "__main__":
    main()
