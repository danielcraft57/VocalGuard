"""
Genere les icones launcher VocalGuard (Material / adaptive Android).

Le fond adaptive DOIT etre opaque : un fond transparent est rendu noir
par Android. Le glyphe (bouclier + barres voix) reste dans la zone sure
66 dp au centre d un canvas 108 dp.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

CANVAS = 1024
SAFE_RATIO = 66 / 108
SAFE = int(CANVAS * SAFE_RATIO)
PAD = (CANVAS - SAFE) // 2

GREEN_TOP = (52, 211, 153, 255)
GREEN_MID = (34, 197, 94, 255)
GREEN_BOT = (21, 128, 61, 255)
WHITE = (255, 255, 255, 255)


def lerp(a: tuple[int, ...], b: tuple[int, ...], t: float) -> tuple[int, ...]:
    """Interpole deux couleurs RGBA."""
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))  # type: ignore[return-value]


def make_background(size: int) -> Image.Image:
    """Fond vert plein, degrade leger 135 deg, 100 % opaque."""
    img = Image.new("RGBA", (size, size), GREEN_MID)
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            if t < 0.5:
                color = lerp(GREEN_TOP, GREEN_MID, t * 2)
            else:
                color = lerp(GREEN_MID, GREEN_BOT, (t - 0.5) * 2)
            px[x, y] = color
    return img


def shield_polygon(cx: float, cy: float, w: float, h: float) -> list[tuple[float, float]]:
    """Silhouette de bouclier Material, centree."""
    left = cx - w / 2
    right = cx + w / 2
    top = cy - h / 2
    bottom = cy + h / 2
    return [
        (cx, top),
        (right - w * 0.12, top + h * 0.06),
        (right - w * 0.04, top + h * 0.16),
        (right - w * 0.04, top + h * 0.46),
        (right - w * 0.18, top + h * 0.78),
        (cx, bottom),
        (left + w * 0.18, top + h * 0.78),
        (left + w * 0.04, top + h * 0.46),
        (left + w * 0.04, top + h * 0.16),
        (left + w * 0.12, top + h * 0.06),
    ]


def make_foreground(size: int) -> Image.Image:
    """Glyphe blanc transparent autour, bouclier + barres en reserve."""
    scale = 4
    hi = size * scale
    mask = Image.new("L", (hi, hi), 0)
    draw = ImageDraw.Draw(mask)
    cx = hi / 2
    cy = hi / 2 + hi * 0.01
    shield_w = hi * (58 / 108)
    shield_h = hi * (64 / 108)
    pts = shield_polygon(cx, cy, shield_w, shield_h)
    draw.polygon(pts, fill=255)
    bar_draw = ImageDraw.Draw(mask)
    # Recalcule les barres a l echelle haute.
    heights = [0.22, 0.38, 0.52, 0.30]
    bar_w = hi * 0.046
    gap = hi * 0.028
    total = 4 * bar_w + 3 * gap
    x0 = cx - total / 2
    radius = bar_w / 2
    for i, rel_h in enumerate(heights):
        bh = hi * rel_h
        x = x0 + i * (bar_w + gap)
        y = cy - bh / 2 + hi * 0.01
        bar_draw.rounded_rectangle((x, y, x + bar_w, y + bh), radius=radius, fill=0)
    mask = mask.resize((size, size), Image.Resampling.LANCZOS)
    fg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fg.putalpha(mask)
    white = Image.new("RGBA", (size, size), WHITE)
    return Image.composite(white, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask)


def compose(bg: Image.Image, fg: Image.Image) -> Image.Image:
    """Assemble fond opaque + glyphe."""
    out = bg.copy()
    out.alpha_composite(fg)
    return out


def save_resized(img: Image.Image, path: Path, size: int, mode: str = "RGBA") -> None:
    """Redimensionne et enregistre un PNG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    if mode == "RGB":
        resized = resized.convert("RGB")
    resized.save(path, "PNG")


def main() -> None:
    """Ecrit les assets Expo et les mipmaps / drawables Android."""
    root = Path(__file__).resolve().parents[1]
    assets = root / "assets"
    res = root / "android" / "app" / "src" / "main" / "res"
    assets.mkdir(parents=True, exist_ok=True)

    bg = make_background(CANVAS)
    fg = make_foreground(CANVAS)
    full = compose(bg, fg)

    full.convert("RGB").save(assets / "icon.png", "PNG")
    fg.save(assets / "adaptive-icon.png", "PNG")
    fg.save(assets / "adaptive-icon-monochrome.png", "PNG")
    fg.save(assets / "splash-icon.png", "PNG")
    full.resize((512, 512), Image.Resampling.LANCZOS).convert("RGB").save(
        assets / "icon-playstore-512.png", "PNG"
    )
    fg.save(assets / "notification-icon.png", "PNG")

    legacy = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    adaptive = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}
    splash = {"mdpi": 144, "hdpi": 216, "xhdpi": 288, "xxhdpi": 432, "xxxhdpi": 576}
    notif = {"mdpi": 24, "hdpi": 36, "xhdpi": 48, "xxhdpi": 72, "xxxhdpi": 96}

    for dens, size in legacy.items():
        folder = res / f"mipmap-{dens}"
        save_resized(full, folder / "ic_launcher.png", size, "RGB")
        save_resized(full, folder / "ic_launcher_round.png", size, "RGB")

    for dens, size in adaptive.items():
        folder = res / f"mipmap-{dens}"
        save_resized(fg, folder / "ic_launcher_foreground.png", size)
        save_resized(fg, folder / "ic_launcher_monochrome.png", size)

    for dens, size in splash.items():
        folder = res / f"drawable-{dens}"
        save_resized(fg, folder / "splashscreen_logo.png", size)

    for dens, size in notif.items():
        folder = res / f"drawable-{dens}"
        save_resized(fg, folder / "notification_icon.png", size)

    print("ok", SAFE, PAD)


if __name__ == "__main__":
    main()
