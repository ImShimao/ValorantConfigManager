# -*- coding: utf-8 -*-
"""Vérification et application des mises à jour via GitHub.

Détection : GitHub redirige /releases/latest vers /releases/tag/vX.Y.Z — on
lit simplement l'en-tête Location de cette redirection. Pas d'API, pas de
quota, pas de JSON, et aucune donnée envoyée.

Application : l'appli télécharge le bon artefact de la release puis se ferme ;
un script batch jetable attend la fin du processus, applique la mise à jour
(installeur silencieux OU remplacement de l'exe portable), relance l'appli et
s'auto-détruit. Un exe Windows ne pouvant pas écraser son propre fichier en
cours d'exécution, ce relais externe est le mécanisme standard.
"""

import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

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


# ----------------------------------------------------------------------------
# Mise à jour automatique
# ----------------------------------------------------------------------------
def install_mode() -> str | None:
    """Comment l'appli est déployée : 'installed' (installeur Inno Setup,
    reconnu à son désinstalleur unins000.exe), 'portable' (exe seul), ou
    None (lancée depuis les sources — pas de mise à jour automatique)."""
    if not getattr(sys, "frozen", False):
        return None
    exe_dir = Path(sys.executable).parent
    return "installed" if (exe_dir / "unins000.exe").is_file() else "portable"


def download_url(version: str, mode: str) -> str:
    """URL de l'artefact adapté au mode de déploiement."""
    if mode == "installed":
        return (f"{GITHUB_URL}/releases/download/v{version}/"
                f"ValorantConfigManager-Setup-{version}.exe")
    return f"{GITHUB_URL}/releases/download/v{version}/ValorantConfigManager.exe"


def fetch_update(version: str, mode: str, progress=None) -> Path:
    """Télécharge l'artefact dans le dossier temporaire et retourne son chemin.

    `progress(fait, total)` est appelé pendant le téléchargement. Lève OSError
    si le fichier est anormalement petit (téléchargement tronqué)."""
    url = download_url(version, mode)
    dest = Path(tempfile.gettempdir()) / url.rsplit("/", 1)[-1]
    req = urllib.request.Request(url, headers={"User-Agent": "ValorantConfigManager"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done, total)
    if dest.stat().st_size < 5_000_000:  # un exe PyInstaller pèse ~30 Mo
        dest.unlink(missing_ok=True)
        raise OSError("téléchargement incomplet")
    return dest


def build_update_script(downloaded: Path, target_exe: Path, pid: int,
                        mode: str, relaunch: bool = True) -> list[str]:
    """Lignes du script batch qui applique la mise à jour.

    Il attend la fin du processus `pid`, puis : mode installé → lance
    l'installeur en silencieux (même dossier, mêmes raccourcis) ; mode
    portable → remplace l'exe (avec réessais tant que Windows le verrouille).
    Enfin il relance l'appli et se supprime."""
    lines = [
        "@echo off",
        ":waitexit",
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
        "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto waitexit)",
        # Un exe PyInstaller onefile a un processus lanceur parent qui peut
        # survivre quelques instants au processus principal en gardant le
        # fichier verrouillé : petite marge avant d'agir.
        "timeout /t 2 /nobreak >nul",
    ]
    if mode == "installed":
        lines.append(f'"{downloaded}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART')
        if relaunch:
            lines.append(f'start "" "{target_exe}"')
        lines.append(f'del "{downloaded}"')
    else:
        lines += [
            ":replace",
            f'move /y "{downloaded}" "{target_exe}" >nul 2>&1',
            "if errorlevel 1 (timeout /t 1 /nobreak >nul & goto replace)",
        ]
        if relaunch:
            lines.append(f'start "" "{target_exe}"')
    lines.append('del "%~f0"')
    return lines


def apply_update(downloaded: Path, mode: str) -> None:
    """Écrit le script de mise à jour et le lance (fenêtre cachée).

    L'appelant doit fermer l'appli immédiatement après : le script attend
    justement la fin de notre processus pour agir."""
    lines = build_update_script(downloaded, Path(sys.executable),
                                os.getpid(), mode)
    script = Path(tempfile.gettempdir()) / f"vcm_update_{os.getpid()}.cmd"
    script.write_text("\r\n".join(lines) + "\r\n", encoding="ascii",
                      errors="replace")
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags,
                     close_fds=True)
