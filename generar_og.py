#!/usr/bin/env python3
"""Genera og-image.jpg y logo.png para LLANO· usando Pillow"""
from PIL import Image, ImageDraw, ImageFont
import os

RUTA = os.path.dirname(os.path.abspath(__file__))

BG = (10, 9, 9)
ACCENT = (200, 120, 10)
TEXT = (232, 228, 222)
MUTED = (160, 155, 148)

def font(size, bold=True):
    candidatos = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for c in candidatos:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()

# ── OG IMAGE 1200x630 ──
img = Image.new("RGB", (1200, 630), BG)
d = ImageDraw.Draw(img)

# Glow radial sutil (simulado con elipses translúcidas)
for r, alpha in [(500, 18), (350, 28), (200, 40)]:
    overlay = Image.new("RGBA", (1200, 630), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse([200 - r, 500 - r, 200 + r, 500 + r], fill=(*ACCENT, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
d = ImageDraw.Draw(img)

# Linea superior fina
d.rectangle([0, 0, 1200, 4], fill=ACCENT)

# Logo LLANO·
f_logo = font(88)
f_tag = font(30, bold=False)
f_foot = font(22, bold=False)

d.text((80, 220), "LLANO", font=f_logo, fill=TEXT)
bbox = d.textbbox((80, 220), "LLANO", font=f_logo)
d.text((bbox[2] + 6, 220), "·", font=f_logo, fill=ACCENT)

d.text((82, 330), "El primer diario digital 100% IA de La Pampa", font=f_tag, fill=MUTED)

d.text((82, 560), "llano.it.com", font=f_foot, fill=ACCENT)

img.save(os.path.join(RUTA, "og-image.jpg"), quality=90)
print("og-image.jpg generado (1200x630)")

# ── LOGO 512x512 ──
logo = Image.new("RGB", (512, 512), BG)
ld = ImageDraw.Draw(logo)
f_logo2 = font(110)
ld.text((60, 190), "LLANO", font=f_logo2, fill=TEXT)
bbox2 = ld.textbbox((60, 190), "LLANO", font=f_logo2)
ld.text((bbox2[2] + 4, 190), "·", font=f_logo2, fill=ACCENT)
logo.save(os.path.join(RUTA, "logo.png"))
print("logo.png generado (512x512)")
