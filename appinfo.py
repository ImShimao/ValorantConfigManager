# -*- coding: utf-8 -*-
"""Métadonnées de l'application et ressources embarquées."""

import sys
from pathlib import Path


def resource_path(name: str) -> Path:
    """Chemin d'une ressource embarquée (compatible PyInstaller)."""
    base = getattr(sys, "_MEIPASS", None)
    return (Path(base) if base else Path(__file__).parent) / name


def _read_version() -> str:
    """Version lue depuis le fichier VERSION (source unique, partagée avec
    l'installeur Inno Setup). Repli sur une valeur littérale si le fichier est
    absent — ne doit jamais faire échouer le démarrage."""
    try:
        return resource_path("VERSION").read_text(encoding="utf-8").strip() or "1.5.1"
    except OSError:
        return "1.5.1"


APP_NAME = "Valorant Config Manager"
APP_VERSION = _read_version()
APP_ID = "VCM.ValorantConfigManager"
PROFILE_EXT = ".vcmprofile"
GITHUB_URL = "https://github.com/ImShimao/ValorantConfigManager"
