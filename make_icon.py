# Génère icon.ico : un "V" blanc anguleux (branche longue + branche courte) sur
# un fond rouge dégradé, coins arrondis. Version retravaillée : les deux branches
# se rejoignent proprement et un léger dégradé donne du relief.
from PIL import Image, ImageDraw

SIZES = [16, 24, 32, 48, 64, 128, 256]

RED = (255, 70, 85, 255)        # #ff4655
RED_DARK = (214, 52, 66, 255)   # bas du dégradé, pour le relief
WHITE = (255, 255, 255, 255)


def _bg(s: int) -> Image.Image:
    """Carré arrondi rempli d'un dégradé vertical rouge."""
    grad = Image.new("RGBA", (1, s))
    for y in range(s):
        t = y / s
        grad.putpixel((0, y),
                      tuple(int(RED[i] + (RED_DARK[i] - RED[i]) * t)
                            for i in range(3)) + (255,))
    grad = grad.resize((s, s))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1],
                                           radius=s // 5, fill=255)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    return img


def make(size: int) -> Image.Image:
    s = size * 4  # supersampling pour l'anticrénelage
    img = _bg(s)
    d = ImageDraw.Draw(img)
    def P(x, y):
        return (s * x, s * y)
    # Grande branche : haut-gauche -> pointe basse
    d.polygon([P(0.15, 0.22), P(0.32, 0.22), P(0.585, 0.82), P(0.455, 0.82)],
              fill=WHITE)
    # Petite branche : haut-droite -> rejoint (chevauche) la grande
    d.polygon([P(0.86, 0.22), P(0.70, 0.22), P(0.47, 0.60), P(0.40, 0.53)],
              fill=WHITE)
    return img.resize((size, size), Image.LANCZOS)


images = [make(s) for s in SIZES]
images[-1].save("icon.ico", sizes=[(s, s) for s in SIZES],
                append_images=images[:-1])
print("icon.ico OK")
