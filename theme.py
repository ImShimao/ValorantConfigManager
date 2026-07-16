# -*- coding: utf-8 -*-
"""Apparence : palette Valorant, polices et icônes vectorielles Windows.

Les polices sont affinées par init_fonts() au démarrage : y accéder via
`theme.FONT_UI` / `theme.FONT_TITLE` (accès par attribut, pas de from-import).
"""

import os
from pathlib import Path

import customtkinter as ctk
import tkinter.font as tkfont
from PIL import Image, ImageDraw, ImageFont

# ----------------------------------------------------------------------------
# Couleurs (palette Valorant)
# ----------------------------------------------------------------------------
C_BG = "#0f1923"        # bleu nuit Valorant
C_PANEL = "#16232f"
C_CARD = "#1f2f3d"
C_CARD_HOVER = "#27394a"
C_RED = "#ff4655"       # rouge Valorant
C_RED_HOVER = "#e13a48"
C_TEXT = "#ece8e1"
C_TEXT_DIM = "#8b9aa7"
C_GREEN = "#3ddc84"
C_ORANGE = "#ffb454"
C_BORDER = "#26394a"

# Polices (affinées au démarrage selon ce qui est installé — voir init_fonts)
FONT_UI = "Segoe UI"
FONT_TITLE = "Segoe UI Black"


def init_fonts():
    """Choisit les meilleures polices disponibles sur ce PC."""
    global FONT_UI, FONT_TITLE
    try:
        fams = set(tkfont.families())
    except Exception:
        return
    if "Segoe UI Variable Text" in fams:
        FONT_UI = "Segoe UI Variable Text"
    for cand in ("Bahnschrift SemiBold", "Bahnschrift", "Segoe UI Black"):
        if cand in fams:
            FONT_TITLE = cand
            break


# ----------------------------------------------------------------------------
# Icônes vectorielles (police d'icônes Windows : Segoe Fluent / MDL2)
# ----------------------------------------------------------------------------
_ICON_FONT_FILES = [
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "SegoeIcons.ttf",   # Win 11
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segmdl2.ttf",      # Win 10
]
GLYPHS = {
    "save": "", "delete": "", "edit": "", "eye": "",
    "export": "", "import": "", "refresh": "", "play": "",
    "compare": "", "restore": "", "bolt": "", "cloud": "",
    "close": "", "globe": "", "user": "", "check": "", "help": "",
}
_icon_cache: dict = {}
_icon_font_path = None
for _f in _ICON_FONT_FILES:
    if _f.is_file():
        _icon_font_path = str(_f)
        break


def icon(name: str, size: int = 15, color: str = C_TEXT):
    """CTkImage d'une icône Windows, ou None si indisponible."""
    if _icon_font_path is None or name not in GLYPHS:
        return None
    key = (name, size, color)
    if key in _icon_cache:
        return _icon_cache[key]
    try:
        big = size * 4
        font = ImageFont.truetype(_icon_font_path, int(big * 0.9))
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((big / 2, big / 2), GLYPHS[name],
                                 font=font, fill=color, anchor="mm")
        img = img.resize((size, size), Image.LANCZOS)
        ci = ctk.CTkImage(img, size=(size, size))
        _icon_cache[key] = ci
        return ci
    except Exception:
        return None
