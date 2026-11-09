#!/usr/bin/env python3
"""
Genere line_phone.ico pour l'appli bureau Line Phone (Material).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "line_phone.ico"


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def _gradient_diag(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGBA", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = (x + y) / max(1, (w + h - 2))
            px[x, y] = (
                _lerp(top[0], bottom[0], t),
                _lerp(top[1], bottom[1], t),
                _lerp(top[2], bottom[2], t),
                255,
            )
    return img


def _handset_poly(size: int, cx: int, cy: int) -> list[tuple[int, int]]:
    """
    Combiner telephone classique (vue 45 deg).

    @param size Taille icone.
    @param cx Centre x.
    @param cy Centre y.
    @returns Points du polygone.
    """
    s = size / 256.0
    pts = [
        (-52, -8),
        (-46, -28),
        (-28, -42),
        (-12, -36),
        (-6, -18),
        (6, 6),
        (18, 22),
        (36, 28),
        (48, 18),
        (54, 2),
        (62, 10),
        (58, 32),
        (36, 50),
        (8, 48),
        (-18, 28),
        (-40, 4),
    ]
    out = []
    for x, y in pts:
        out.append((int(cx + x * s), int(cy + y * s)))
    return out


def render_icon(size: int) -> Image.Image:
    """
    Combine violet M3 + ondes radio.

    @param size Taille carree.
    @returns Image RGBA.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pad = max(2, size // 18)
    bg = _gradient_diag(size, size, (79, 55, 139), (30, 22, 52))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (pad, pad, size - pad, size - pad),
        radius=int(size * 0.24),
        fill=255,
    )
    img.paste(bg, (0, 0), mask)

    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2 + size // 28

    # Ondes
    for i, frac in enumerate((0.28, 0.40, 0.52)):
        r = int(size * frac)
        alpha = 90 - i * 22
        col = (125, 211, 252, alpha) if i % 2 == 0 else (208, 188, 255, alpha)
        bbox = (cx - r, cy - r - size // 10, cx + r, cy + r - size // 10)
        draw.arc(bbox, start=220, end=320, fill=col, width=max(2, size // 28))

    # Combiner
    poly = _handset_poly(size, cx, cy)
    draw.polygon(poly, fill=(250, 245, 255, 255))
    # Ombre interne
    if size >= 48:
        inset = []
        for x, y in poly:
            inset.append((int(x * 0.97 + cx * 0.03), int(y * 0.97 + cy * 0.03)))
        draw.polygon(inset, fill=(234, 221, 255, 255))

    # Point ligne (LED verte)
    led = max(3, size // 14)
    lx = cx + int(size * 0.22)
    ly = cy - int(size * 0.28)
    draw.ellipse((lx - led, ly - led, lx + led, ly + led), fill=(134, 239, 172, 255))

    glow = img.filter(ImageFilter.GaussianBlur(radius=max(1, size // 48)))
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
    png = ROOT / "line_phone.png"
    images[-1].save(png, format="PNG")
    print(f"Icone ecrite : {OUT}")
    print(f"Apercu PNG : {png}")


if __name__ == "__main__":
    main()
