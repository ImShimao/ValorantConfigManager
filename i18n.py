# -*- coding: utf-8 -*-
"""Langue de l'interface (FR/EN).

Les autres modules traduisent avec `T(fr, en)` et lisent la langue via
`i18n.LANG` (accès par attribut, pour suivre les changements en cours de
session — un `from i18n import LANG` figerait la valeur).
"""

LANG = "fr"


def T(fr: str, en: str) -> str:
    """Retourne la chaîne dans la langue active."""
    return en if LANG == "en" else fr


def set_lang(lang: str):
    global LANG
    LANG = "en" if lang == "en" else "fr"
