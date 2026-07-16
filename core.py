# -*- coding: utf-8 -*-
"""Logique sans interface : comptes, profils, sauvegardes, archives
.vcmprofile et intégrations Windows (processus du jeu, association de
fichiers).

Deux sources de paramètres sont gérées :
  1. Les fichiers locaux : %LOCALAPPDATA%\\VALORANT\\Saved\\Config\\<compte>\\
     (paramètres vidéo, propres à ce PC)
  2. Les paramètres cloud Riot (crosshair, sensibilité, keybinds...),
     via l'API du client Riot — voir riot_cloud.py. C'est indispensable :
     à la connexion, le jeu écrase les fichiers locaux avec le cloud.

Les dossiers de données sont des globals de module : les tests les
redirigent vers des dossiers temporaires via monkeypatch.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import i18n
import riot_cloud
from i18n import T

ACCOUNT_DIR_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-[a-z0-9]+$",
    re.IGNORECASE,
)

VALO_CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "VALORANT" / "Saved" / "Config"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "ValorantConfigManager"
PROFILES_DIR = DATA_DIR / "profiles"
BACKUPS_DIR = DATA_DIR / "backups"
ACCOUNTS_FILE = DATA_DIR / "accounts.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

MAX_BACKUPS_PER_ACCOUNT = 20


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False),
                             encoding="utf-8")


# ----------------------------------------------------------------------------
# Logique (sans interface)
# ----------------------------------------------------------------------------
def ensure_dirs():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


def load_account_names() -> dict:
    try:
        return json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_account_names(names: dict):
    ensure_dirs()
    ACCOUNTS_FILE.write_text(json.dumps(names, indent=2, ensure_ascii=False), encoding="utf-8")


def list_accounts():
    """Retourne [(nom_dossier, Path, datetime_dernière_modif)] trié du plus récent au plus ancien."""
    accounts = []
    if not VALO_CONFIG_DIR.is_dir():
        return accounts
    for entry in VALO_CONFIG_DIR.iterdir():
        if entry.is_dir() and ACCOUNT_DIR_RE.match(entry.name):
            last = None
            for f in entry.rglob("*"):
                if f.is_file():
                    ts = datetime.fromtimestamp(f.stat().st_mtime)
                    if last is None or ts > last:
                        last = ts
            accounts.append((entry.name, entry, last or datetime.fromtimestamp(entry.stat().st_mtime)))
    accounts.sort(key=lambda a: a[2], reverse=True)
    return accounts


def folder_for_puuid(puuid: str):
    """Dossier de config correspondant à un PUUID, ou None.

    Appelée par le poll de statut toutes les 6 s : on parcourt seulement les
    noms de dossiers, sans les stat récursifs de list_accounts()."""
    if not puuid or not VALO_CONFIG_DIR.is_dir():
        return None
    for entry in VALO_CONFIG_DIR.iterdir():
        if (entry.is_dir() and ACCOUNT_DIR_RE.match(entry.name)
                and entry.name.lower().startswith(puuid.lower())):
            return entry.name
    return None


def list_profiles():
    """Retourne la liste des profils [{id, name, source_name, created, has_cloud, path}]."""
    profiles = []
    if not PROFILES_DIR.is_dir():
        return profiles
    for entry in PROFILES_DIR.iterdir():
        meta_file = entry / "meta.json"
        if entry.is_dir() and meta_file.is_file():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                meta["id"] = entry.name
                meta["path"] = entry
                meta["has_cloud"] = (entry / "cloud.json").is_file()
                profiles.append(meta)
            except (OSError, json.JSONDecodeError):
                continue
    profiles.sort(key=lambda p: p.get("created", ""), reverse=True)
    return profiles


def create_profile(account_dir: Path, profile_name: str, account_label: str,
                   cloud: dict | None = None) -> str:
    """cloud : {'riot_id':..., 'subject':..., 'settings': {...}} ou None."""
    ensure_dirs()
    profile_id = uuid.uuid4().hex[:12]
    dest = PROFILES_DIR / profile_id
    shutil.copytree(account_dir, dest / "files")
    meta = {
        "name": profile_name,
        "source_folder": account_dir.name,
        "source_name": account_label,
        "created": datetime.now().isoformat(timespec="seconds"),
        "riot_id": (cloud or {}).get("riot_id", ""),
    }
    (dest / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    if cloud:
        (dest / "cloud.json").write_text(json.dumps(cloud, ensure_ascii=False), encoding="utf-8")
    return profile_id


def read_profile_cloud(profile_path: Path) -> dict | None:
    try:
        return json.loads((profile_path / "cloud.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _rotate_backups(parent: Path):
    """Rotation : on garde les N sauvegardes les plus récentes."""
    backups = sorted([d for d in parent.iterdir() if d.is_dir()], reverse=True)
    for old in backups[MAX_BACKUPS_PER_ACCOUNT:]:
        shutil.rmtree(old, ignore_errors=True)


def backup_account(account_dir: Path, cloud: dict | None = None, auto: bool = False) -> Path:
    ensure_dirs()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ("_auto" if auto else "")
    dest = BACKUPS_DIR / account_dir.name / stamp
    shutil.copytree(account_dir, dest / "files")
    if cloud:
        (dest / "cloud.json").write_text(json.dumps(cloud, ensure_ascii=False), encoding="utf-8")
    _rotate_backups(BACKUPS_DIR / account_dir.name)
    return dest


def backup_cloud_only(subject: str, cloud: dict) -> Path:
    """Sauvegarde des seuls paramètres cloud, pour un compte qui n'a pas
    (encore) de dossier de configuration local sur ce PC."""
    ensure_dirs()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    parent = BACKUPS_DIR / (subject.lower() or "inconnu")
    dest = parent / stamp
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "cloud.json").write_text(json.dumps(cloud, ensure_ascii=False), encoding="utf-8")
    _rotate_backups(parent)
    return dest


def apply_files(src_files: Path, account_dir: Path):
    """Copie le contenu de src_files vers le dossier du compte (écrase les fichiers)."""
    shutil.copytree(src_files, account_dir, dirs_exist_ok=True)


def list_backups(account_folder_name: str):
    parent = BACKUPS_DIR / account_folder_name
    if not parent.is_dir():
        return []
    return sorted([d for d in parent.iterdir() if d.is_dir()], key=lambda d: d.name, reverse=True)


def is_valorant_running() -> bool:
    """Vérifie si le JEU Valorant tourne (pas le client Riot)."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            creationflags=flags, text=True, errors="ignore", timeout=10,
        ).lower()
        # Noms de processus exacts (le CSV de tasklist les met entre guillemets)
        return '"valorant-win64-shipping.exe"' in out or '"valorant.exe"' in out
    except Exception:
        return False


def short_id(folder_name: str) -> str:
    return folder_name.split("-")[0]


def fmt_date(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M")


def parse_video_settings(profile_path: Path) -> dict:
    """Extrait quelques réglages vidéo lisibles depuis GameUserSettings.ini."""
    out = {}
    ini = profile_path / "files" / "Windows" / "GameUserSettings.ini"
    try:
        text = ini.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return out
    def grab(key):
        m = re.search(rf"^{key}=(.+)$", text, re.MULTILINE)
        return m.group(1).strip() if m else None
    x, y = grab("ResolutionSizeX"), grab("ResolutionSizeY")
    if x and y:
        out["resolution"] = f"{x}x{y}"
    fps = grab("FrameRateLimit")
    if fps:
        try:
            out["fps_limit"] = str(int(float(fps)))
        except ValueError:
            pass
    mode = grab("FullscreenMode") or grab("LastConfirmedFullscreenMode")
    if mode is not None:
        modes_fr = {"0": "Plein écran", "1": "Fenêtré plein écran", "2": "Fenêtré"}
        modes_en = {"0": "Fullscreen", "1": "Borderless", "2": "Windowed"}
        out["screen_mode"] = (modes_en if i18n.LANG == "en" else modes_fr).get(mode, mode)
    return out


def profile_summary(prof: dict) -> dict:
    """Résumé comparable d'un profil : sensi, crosshairs, touches, vidéo..."""
    s = {"cloud": prof.get("has_cloud", False)}
    s.update(parse_video_settings(prof["path"]))
    cloud = read_profile_cloud(prof["path"])
    if cloud:
        parsed = riot_cloud.decode_settings_blob((cloud.get("settings") or {}).get("data", ""))
        if parsed:
            floats = {x["settingEnum"]: x["value"] for x in parsed.get("floatSettings", [])}
            if "EAresFloatSettingName::MouseSensitivity" in floats:
                s["sens"] = round(floats["EAresFloatSettingName::MouseSensitivity"], 4)
            if "EAresFloatSettingName::MouseSensitivityZoomed" in floats:
                s["ads"] = round(floats["EAresFloatSettingName::MouseSensitivityZoomed"], 4)
            strings = {x["settingEnum"]: x["value"] for x in parsed.get("stringSettings", [])}
            xr = strings.get("EAresStringSettingName::SavedCrosshairProfileData")
            if xr:
                try:
                    xd = json.loads(xr)
                    s["crosshairs"] = [p.get("profileName") or "?" for p in xd.get("profiles", [])]
                except json.JSONDecodeError:
                    pass
            s["keybinds"] = {(m.get("name"), m.get("key"), m.get("alt"))
                             for m in parsed.get("actionMappings", [])}
            s["n_settings"] = (len(parsed.get("boolSettings", [])) + len(floats)
                               + len(parsed.get("intSettings", [])))
    return s


_SKIP_ENUMS = {"SavedCrosshairProfileData", "LastSeenAdHocPopup", "LastSeenSeasonalPopup",
               "MouseSensitivity", "MouseSensitivityZoomed"}


def cloud_settings_map(prof: dict) -> dict | None:
    """Tous les réglages cloud d'un profil : {nom_court: valeur}, ou None."""
    cloud = read_profile_cloud(prof["path"])
    if not cloud:
        return None
    parsed = riot_cloud.decode_settings_blob((cloud.get("settings") or {}).get("data", ""))
    if not parsed:
        return None
    out = {}
    for kind in ("boolSettings", "intSettings", "floatSettings", "stringSettings"):
        for item in parsed.get(kind, []):
            short = str(item.get("settingEnum", "")).split("::")[-1]
            if not short or short in _SKIP_ENUMS:
                continue
            v = item.get("value")
            if isinstance(v, float):
                v = round(v, 4)
            out[short] = v
    return out


def keybind_map(prof: dict) -> dict | None:
    """Touches par action : {action: 'touche1 / touche2'}, ou None."""
    cloud = read_profile_cloud(prof["path"])
    if not cloud:
        return None
    parsed = riot_cloud.decode_settings_blob((cloud.get("settings") or {}).get("data", ""))
    if not parsed:
        return None
    binds = {}
    for m in parsed.get("actionMappings", []):
        name = str(m.get("name", "")).split("::")[-1]
        key = str(m.get("key", "")).split("::")[-1]
        if name and key:
            binds.setdefault(name, set()).add(key)
    return {name: " / ".join(sorted(keys)) for name, keys in binds.items()}


def write_profile_archive(profile_path: Path, out_path: str):
    """Crée un fichier .vcmprofile (zip) à partir d'un dossier de profil.

    Le PUUID (`subject`) du compte source est retiré du cloud.json exporté :
    il ne sert qu'aux vérifications locales et n'a pas à circuler dans un
    fichier destiné à être partagé."""
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in profile_path.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(profile_path).as_posix()
            if rel == "cloud.json":
                try:
                    cloud = json.loads(f.read_text(encoding="utf-8"))
                    cloud.pop("subject", None)
                    z.writestr(rel, json.dumps(cloud, ensure_ascii=False))
                    continue
                except (OSError, json.JSONDecodeError):
                    pass
            z.write(f, rel)


def extract_profile_archive(path: str, dest: Path) -> dict:
    """Extrait un .vcmprofile vers `dest` et retourne son meta.json.

    Lève ValueError si l'archive n'est pas un profil valide (meta.json
    manquant ou chemins dangereux — zip slip)."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "meta.json" not in names:
            raise ValueError(T("ce fichier n'est pas un profil valide",
                               "this file is not a valid profile"))
        for n in names:
            if n.startswith(("/", "\\")) or ".." in n or ":" in n:
                raise ValueError(T("archive invalide", "invalid archive"))
        z.extractall(dest)
    return json.loads((dest / "meta.json").read_text(encoding="utf-8"))


def register_file_association():
    """Associe l'extension .vcmprofile à cet exe (HKCU, sans admin)."""
    if not getattr(sys, "frozen", False):
        return
    try:
        import winreg
        exe = sys.executable
        root = winreg.HKEY_CURRENT_USER
        with winreg.CreateKey(root, r"Software\Classes\.vcmprofile") as k:
            winreg.SetValue(k, "", winreg.REG_SZ, "VCM.Profile")
        with winreg.CreateKey(root, r"Software\Classes\VCM.Profile") as k:
            winreg.SetValue(k, "", winreg.REG_SZ, "Profil Valorant Config Manager")
        with winreg.CreateKey(root, r"Software\Classes\VCM.Profile\DefaultIcon") as k:
            winreg.SetValue(k, "", winreg.REG_SZ, f'"{exe}",0')
        with winreg.CreateKey(root, r"Software\Classes\VCM.Profile\shell\open\command") as k:
            winreg.SetValue(k, "", winreg.REG_SZ, f'"{exe}" "%1"')
    except OSError:
        pass
