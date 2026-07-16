# -*- coding: utf-8 -*-
"""Métadonnées de l'application et ressources embarquées."""

import sys
from pathlib import Path

APP_NAME = "Valorant Config Manager"
APP_VERSION = "1.5.1"
APP_ID = "VCM.ValorantConfigManager"
PROFILE_EXT = ".vcmprofile"
GITHUB_URL = "https://github.com/ImShimao/ValorantConfigManager"


def resource_path(name: str) -> Path:
    """Chemin d'une ressource embarquée (compatible PyInstaller)."""
    base = getattr(sys, "_MEIPASS", None)
    return (Path(base) if base else Path(__file__).parent) / name
