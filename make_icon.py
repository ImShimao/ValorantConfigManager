# Génère icon.ico : un nuage bicolore (rouge / vert) traversé de deux flèches
# blanches (envoi ↑ / réception ↓), coins arrondis. Le motif évoque la synchro
# des configs vers le cloud Riot — cœur de l'appli — et ne reprend rien du logo
# Valorant.
from PIL import Image, ImageDraw

SIZES = [16, 24, 32, 48, 64, 128, 256]

C_BG = (15, 25, 35, 255)        # #0f1923 — bleu nuit du thème
C_RED = (255, 70, 85, 255)      # moitié gauche du nuage
C_TEAL = (61, 220, 132, 255)    # moitié droite du nuage
C_LIGHT = (240, 244, 248, 255)  # flèches


def _cloud(s: int, fill) -> Image.Image:
    """Silhouette de nuage (base + trois bosses), pleine hauteur s×s."""
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([0.22*s, 0.46*s, 0.80*s, 0.66*s], radius=0.10*s, fill=fill)
    d.ellipse([0.20*s, 0.40*s, 0.44*s, 0.64*s], fill=fill)   # bosse gauche
    d.ellipse([0.36*s, 0.26*s, 0.68*s, 0.58*s], fill=fill)   # grande bosse
    d.ellipse([0.56*s, 0.36*s, 0.82*s, 0.62*s], fill=fill)   # bosse droite
    return layer


def _up(d, cx, cy, s, col):
    w, hh, head = 0.048*s, 0.105*s, 0.088*s
    d.polygon([(cx, cy-hh), (cx-head, cy-hh+head), (cx-w, cy-hh+head),
               (cx-w, cy+hh), (cx+w, cy+hh), (cx+w, cy-hh+head),
               (cx+head, cy-hh+head)], fill=col)


def _down(d, cx, cy, s, col):
    w, hh, head = 0.048*s, 0.105*s, 0.088*s
    d.polygon([(cx, cy+hh), (cx-head, cy+hh-head), (cx-w, cy+hh-head),
               (cx-w, cy-hh), (cx+w, cy-hh), (cx+w, cy+hh-head),
               (cx+head, cy+hh-head)], fill=col)


def make(size: int) -> Image.Image:
    s = size * 4  # supersampling pour l'anticrénelage
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, s-1, s-1], radius=s//5, fill=C_BG)

    img.alpha_composite(_cloud(s, C_RED))                    # nuage rouge entier
    right = _cloud(s, C_TEAL).crop((s//2, 0, s, s))          # moitié droite verte
    img.alpha_composite(right, (s//2, 0))

    d = ImageDraw.Draw(img)
    d.line([(s/2, 0.28*s), (s/2, 0.66*s)], fill=C_BG, width=max(2, int(0.02*s)))
    _up(d, 0.385*s, 0.50*s, s, C_LIGHT)                      # envoi — moitié rouge
    _down(d, 0.615*s, 0.50*s, s, C_LIGHT)                    # réception — moitié verte

    return img.resize((size, size), Image.LANCZOS)


images = [make(s) for s in SIZES]
images[-1].save("icon.ico", sizes=[(s, s) for s in SIZES],
                append_images=images[:-1])
print("icon.ico OK")
