"""Prépare les images du site à partir des dossiers de production.

Outil de développement local : il n'est pas à envoyer sur l'hébergement.
Usage : py -3 tools/build_assets.py   (nécessite Pillow)
Les fichiers générés sont écrits dans public/.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
IMG = PUBLIC / "assets" / "img"
FONT = ROOT / "tools" / "archivo-variable.ttf"

SHORTS = Path("D:/@UMPC-Shorts-Reactions/Videos")
LONG = Path("D:/@UMPC-Long/Videos")
LOGO_TRANSPARENT = Path("D:/@UMPC-Long/Assets/Logos/umpc_mark_transparent.png")
LOGO_NAVY = Path("D:/@UMPC-Long/Assets/Logos/umpc_mark_navy_square.png")

NAVY = (10, 22, 51)
YELLOW = (255, 212, 0)
CYAN = (51, 214, 232)
WHITE = (255, 255, 255)

# name: (source, aspect w/h, focus x, focus y, widths)
IMAGES = {
    "hero-colibri": (SHORTS / "6 - La langue du colibri est une micropompe/Scenes/Scene-1/v6_s1_first_frame.png", 9 / 16, 0.5, 0.5, (240, 480)),
    "hero-paille": (SHORTS / "8 - Jusqu a quelle hauteur peut-on boire avec une paille/Scenes/Scene-5/v8_s5_first_frame.png", 9 / 16, 0.5, 0.5, (240, 480)),
    "hero-immunite": (LONG / "2 - Pourquoi ton systeme immunitaire te rend malade pour te proteger/Scenes/Scene-6/v2_s6_first_frame.png", 9 / 16, 0.37, 0.5, (240, 480)),
    "univers-science": (SHORTS / "13 - Cette bacterie fabrique de l or pour survivre/Scenes/Scene-1/v13_s1_first_frame.png", 4 / 5, 0.5, 0.58, (360, 720)),
    "univers-animaux": (SHORTS / "12 - Comment la pieuvre goute par le toucher/Scenes/Scene-3/v12_s3_last_frame.png", 4 / 5, 0.5, 0.42, (360, 720)),
    "univers-corps-humain": (LONG / "2 - Pourquoi ton systeme immunitaire te rend malade pour te proteger/Scenes/Scene-14/v2_s14_first_frame.png", 4 / 5, 0.25, 0.5, (360, 720)),
    "univers-nature": (SHORTS / "10 - Pourquoi l ortie pique sans epine/Scenes/Scene-2/v10_s2_last_frame.png", 4 / 5, 0.5, 0.42, (360, 720)),
}


def crop_to(im, aspect, fx, fy):
    w, h = im.size
    if w / h > aspect:
        cw, ch = round(h * aspect), h
    else:
        cw, ch = w, round(w / aspect)
    x = min(max(round(fx * w - cw / 2), 0), w - cw)
    y = min(max(round(fy * h - ch / 2), 0), h - ch)
    return im.crop((x, y, x + cw, y + ch))


def font(size, wght=800, wdth=100):
    f = ImageFont.truetype(str(FONT), size)
    f.set_variation_by_axes([wght, wdth])
    return f


def trimmed_logo():
    im = Image.open(LOGO_TRANSPARENT).convert("RGBA")
    # Le PNG source contient un halo quasi transparent : on coupe sur l'alpha réel.
    alpha = im.getchannel("A").point(lambda a: 255 if a > 40 else 0)
    im = im.crop(alpha.getbbox())
    side = round(max(im.size) * 1.08)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2), im)
    return sq


def navy_icon(size, pad=0.14, radius=0.0):
    logo = trimmed_logo()
    bg = Image.new("RGBA", (size, size), NAVY + (255,))
    inner = round(size * (1 - 2 * pad))
    lg = logo.resize((inner, inner), Image.LANCZOS)
    bg.paste(lg, ((size - inner) // 2, (size - inner) // 2), lg)
    if radius:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), round(size * radius), fill=255)
        bg.putalpha(mask)
    return bg


def build_photos():
    for name, (src, aspect, fx, fy, widths) in IMAGES.items():
        im = crop_to(Image.open(src).convert("RGB"), aspect, fx, fy)
        for w in widths:
            out = im.resize((w, round(w / aspect)), Image.LANCZOS)
            out.save(IMG / f"{name}-{w}.webp", "WEBP", quality=72, method=6)


def build_brand():
    logo = trimmed_logo()
    for s in (96, 192):
        logo.resize((s, s), Image.LANCZOS).save(IMG / f"logo-{s}.webp", "WEBP", quality=90, method=6)
    navy_icon(512, pad=0.1).convert("RGB").save(IMG / "logo-512.png", optimize=True)
    navy_icon(180, pad=0.1).convert("RGB").save(PUBLIC / "apple-touch-icon.png", optimize=True)
    navy_icon(192, pad=0.1).convert("RGB").save(PUBLIC / "icon-192.png", optimize=True)
    navy_icon(512, pad=0.1).convert("RGB").save(PUBLIC / "icon-512.png", optimize=True)
    navy_icon(64, pad=0.04, radius=0.22).save(PUBLIC / "favicon-32.png", optimize=True)
    ico = navy_icon(256, pad=0.04, radius=0.22)
    ico.save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])


def build_og():
    W, H = 1200, 630
    og = Image.new("RGB", (W, H), NAVY)
    glow = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(glow)
    d.ellipse((760, -160, 1360, 440), fill=(18, 52, 110))
    d.ellipse((-220, 380, 360, 900), fill=(14, 38, 84))
    og = Image.blend(og, glow.filter(ImageFilter.GaussianBlur(120)), 1.0)

    cards = [("hero-paille", -9, 880, 160), ("hero-immunite", 9, 1062, 160), ("hero-colibri", 0, 972, 110)]
    for name, angle, cx, top in cards:
        src, aspect, fx, fy, _ = IMAGES[name]
        im = crop_to(Image.open(src).convert("RGB"), aspect, fx, fy).resize((200, 356), Image.LANCZOS)
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), 22, fill=255)
        card = Image.new("RGBA", im.size)
        card.paste(im, (0, 0), mask)
        card = card.rotate(angle, resample=Image.BICUBIC, expand=True)
        pad = 60
        alpha = Image.new("L", (card.width + 2 * pad, card.height + 2 * pad), 0)
        alpha.paste(card.getchannel("A").point(lambda a: int(a * 0.55)), (pad, pad))
        shadow = Image.new("RGBA", alpha.size, (0, 0, 0, 0))
        shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(18)))
        x, y = cx - card.width // 2, top
        og.paste(shadow, (x + 8 - pad, y + 18 - pad), shadow)
        og.paste(card, (x, y), card)

    logo = trimmed_logo().resize((112, 112), Image.LANCZOS)
    og.paste(logo, (72, 70), logo)
    d = ImageDraw.Draw(og)
    f_title = font(82, 900, 68)
    d.text((72, 214), "UNE MINUTE", font=f_title, fill=WHITE)
    d.text((72, 300), "POUR COMPRENDRE", font=f_title, fill=YELLOW)
    d.text((74, 418), "Science · Animaux · Corps humain · Nature", font=font(30, 600, 100), fill=(220, 230, 242))
    d.text((74, 486), "@1min.pour.comprendre", font=font(30, 700, 100), fill=CYAN)
    og.save(IMG / "og-image.jpg", "JPEG", quality=84, optimize=True, progressive=True)


if __name__ == "__main__":
    IMG.mkdir(parents=True, exist_ok=True)
    build_photos()
    build_brand()
    build_og()
    for p in sorted(list(IMG.iterdir()) + [p for p in PUBLIC.iterdir() if p.is_file()]):
        print(f"{p.stat().st_size / 1024:7.1f} Ko  {p.relative_to(PUBLIC)}")
