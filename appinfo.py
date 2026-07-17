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
    l'installeur Inno Setup). Le fichier doit toujours être présent (bundlé par
    le .spec, à la racine en dev) ; le repli « dev » est volontairement une
    valeur non-version, pour qu'un build cassé se voie au lieu de mentir sur la
    version. Ne doit jamais faire échouer le démarrage."""
    try:
        return resource_path("VERSION").read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


APP_NAME = "Valorant Config Manager"
APP_VERSION = _read_version()
APP_ID = "VCM.ValorantConfigManager"
PROFILE_EXT = ".vcmprofile"
GITHUB_URL = "https://github.com/ImShimao/ValorantConfigManager"
