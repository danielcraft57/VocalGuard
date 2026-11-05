#!/usr/bin/env python3
"""
Genere commercial_studio.ico pour l'exe Windows Commercial Studio.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "commercial_studio.ico"


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def _gradient_vertical(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGBA", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        col = (
            _lerp(top[0], bottom[0], t),
            _lerp(top[1], bottom[1], t),
            _lerp(top[2], bottom[2], t),
            255,
        )
        for x in range(w):
            px[x, y] = col
    return img


def render_icon(size: int) -> Image.Image:
    """
    Dessine une icone micro + onde (palette Studio).

    @param size Taille carree.
    @returns Image RGBA.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(2, size // 16)
    r = size // 2 - pad

    # Fond arrondi
    bg = _gradient_vertical(size, size, (15, 20, 28), (8, 12, 18))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (pad, pad, size - pad, size - pad), radius=int(size * 0.22), fill=255
    )
    img.paste(bg, (0, 0), mask)

    cx, cy = size // 2, size // 2 - size // 18
    mic_w = max(4, size // 7)
    mic_h = max(8, size // 4)
    body_top = cy - mic_h // 2
    body_bot = cy + mic_h // 2
    draw.rounded_rectangle(
        (cx - mic_w // 2, body_top, cx + mic_w // 2, body_bot),
        radius=mic_w // 2,
        fill=(248, 250, 252, 255),
    )
    arc_y = body_bot + max(2, size // 32)
    draw.arc(
        (
            cx - mic_w,
            arc_y - mic_w // 2,
            cx + mic_w,
            arc_y + mic_w + mic_h // 3,
        ),
        start=0,
        end=180,
        fill=(94, 234, 212, 255),
        width=max(2, size // 32),
    )
    stem_h = max(3, size // 16)
    draw.rectangle(
        (cx - max(1, size // 64), body_bot, cx + max(1, size // 64), body_bot + stem_h),
        fill=(148, 163, 184, 255),
    )
    base_w = mic_w + max(4, size // 12)
    draw.rounded_rectangle(
        (
            cx - base_w // 2,
            body_bot + stem_h,
            cx + base_w // 2,
            body_bot + stem_h + max(3, size // 24),
        ),
        radius=max(2, size // 48),
        fill=(56, 189, 248, 255),
    )

    # Barres onde (bas)
    bar_y = size - pad - max(6, size // 6)
    bar_h_max = max(6, size // 5)
    n = 5
    gap = max(2, size // 24)
    total_w = n * max(3, size // 18) + (n - 1) * gap
    x0 = cx - total_w // 2
    heights = (0.35, 0.7, 1.0, 0.55, 0.4)
    for i, frac in enumerate(heights):
        bw = max(3, size // 18)
        bh = int(bar_h_max * frac)
        x = x0 + i * (bw + gap)
        col = (249, 115, 22, 230) if i == 2 else (56, 189, 248, 200)
        draw.rounded_rectangle(
            (x, bar_y - bh, x + bw, bar_y),
            radius=bw // 2,
            fill=col,
        )

    glow = img.filter(ImageFilter.GaussianBlur(radius=max(1, size // 64)))
    img = Image.alpha_composite(glow, img)
    return img


def main() -> None:
    """Ecrit le fichier .ico multi-resolution."""
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = [render_icon(s) for s in sizes]
    images[0].save(
        OUT,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print(f"Icône écrite : {OUT}")


if __name__ == "__main__":
    main()
