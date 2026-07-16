# Génère icon.ico : un "V" blanc sur fond rouge Valorant, coins arrondis.
from PIL import Image, ImageDraw

SIZES = [16, 24, 32, 48, 64, 128, 256]


def make(size: int) -> Image.Image:
    s = size * 4  # supersampling pour l'anticrénelage
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = s // 5
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=(255, 70, 85, 255))

    # "V" anguleux style Valorant
    w = s * 0.16          # épaisseur des branches
    top = s * 0.24
    bot = s * 0.80
    cx = s / 2
    left_x = s * 0.20
    right_x = s * 0.80
    d.polygon([(left_x, top), (left_x + w, top), (cx + w * 0.5, bot),
               (cx - w * 0.5, bot)], fill=(255, 255, 255, 255))
    d.polygon([(right_x - w, top), (right_x, top), (cx + w * 0.62, bot * 0.78),
               (cx + w * 0.62 - w, bot * 0.78)], fill=(255, 255, 255, 255))

    return img.resize((size, size), Image.LANCZOS)


images = [make(s) for s in SIZES]
images[-1].save("icon.ico", sizes=[(s, s) for s in SIZES],
                append_images=images[:-1])
print("icon.ico OK")
