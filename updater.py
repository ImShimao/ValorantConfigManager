# -*- coding: utf-8 -*-
"""Vérification des mises à jour via la page « releases/latest » de GitHub.

GitHub redirige /releases/latest vers /releases/tag/vX.Y.Z : on lit simplement
l'en-tête Location de cette redirection. Pas d'API, pas de quota, pas de JSON,
et aucune donnée envoyée — l'équivalent réseau d'ouvrir la page des versions.
"""

import re
import urllib.error
import urllib.request

from appinfo import APP_VERSION, GITHUB_URL

LATEST_URL = GITHUB_URL + "/releases/latest"


def parse_version(s: str):
    """'v1.6.1' → (1, 6, 1). None si non reconnaissable (ex. 'dev')."""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", s or "")
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(latest: str, current: str) -> bool:
    """True si `latest` est strictement plus récente que `current`."""
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Ne pas suivre la redirection : c'est elle qu'on veut lire."""

    def redirect_request(self, *args, **kwargs):
        return None


def get_latest_version(timeout: float = 6) -> str | None:
    """Dernière version publiée sur GitHub ('1.6.1'), ou None (hors-ligne...)."""
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(
        LATEST_URL, headers={"User-Agent": "ValorantConfigManager"})
    location = ""
    try:
        with opener.open(req, timeout=timeout) as resp:
            location = resp.headers.get("Location", "")
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            location = e.headers.get("Location", "")
    except (urllib.error.URLError, OSError):
        return None
    v = parse_version(location.rsplit("/", 1)[-1])
    return ".".join(map(str, v)) if v else None


def update_available() -> str | None:
    """Version plus récente que celle installée, ou None."""
    latest = get_latest_version()
    return latest if latest and is_newer(latest, APP_VERSION) else None
