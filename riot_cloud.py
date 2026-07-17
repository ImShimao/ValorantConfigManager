# -*- coding: utf-8 -*-
"""
Accès aux paramètres cloud Valorant via le client Riot local.

Le client Riot expose une API locale (port + mot de passe dans le "lockfile").
On y récupère les jetons de session du compte connecté, puis on lit/écrit les
paramètres du jeu (crosshair, sensibilité, keybinds...) via le service
player-preferences de Riot — celui que le jeu utilise lui-même pour la
synchronisation cloud.

Aucun identifiant / mot de passe n'est demandé ni stocké : on utilise la
session déjà ouverte dans le client Riot.
"""

import base64
import json
import os
import ssl
import urllib.error
import urllib.request
import zlib
from pathlib import Path

LOCKFILE = Path(os.environ.get("LOCALAPPDATA", "")) / "Riot Games" / "Riot Client" / "Config" / "lockfile"

SETTINGS_TYPE = "Ares.PlayerSettings"

# Serveurs player-preferences par affinité (source : config publique du client
# Riot, clé "keystone.player-preferences.url_by_affinity").
PREFS_HOSTS = {
    "eu": "https://player-preferences-euc1.pp.sgp.pvp.net",
    "us": "https://player-preferences-usw2.pp.sgp.pvp.net",
    "asia": "https://player-preferences-apne1.pp.sgp.pvp.net",
    "sea": "https://player-preferences-apse1.pp.sgp.pvp.net",
}
# Région du compte (chat session) -> affinité
REGION_TO_AFFINITY = {
    "eu": "eu", "tr": "eu", "ru": "eu",
    "na": "us", "latam": "us", "br": "us", "pbe": "us",
    "kr": "asia", "ap": "sea",
}

# En-têtes attendus par le service (Cloudflare rejette les User-Agent inconnus)
_UA = "ShooterGame/13 Windows/10.0.26100.1.256.64bit"
_PLATFORM = base64.b64encode(json.dumps({
    "platformType": "PC",
    "platformOS": "Windows",
    "platformOSVersion": "10.0.26100.1.256.64bit",
    "platformChipset": "Unknown",
}).encode()).decode()

_SSL_LOCAL = ssl.create_default_context()
_SSL_LOCAL.check_hostname = False
_SSL_LOCAL.verify_mode = ssl.CERT_NONE  # certificat auto-signé du client Riot (localhost)


class RiotClientError(Exception):
    """Client Riot fermé, personne de connecté, ou erreur réseau."""


def read_lockfile():
    try:
        raw = LOCKFILE.read_text(encoding="utf-8")
    except OSError:
        raise RiotClientError("Le client Riot n'est pas ouvert.")
    parts = raw.strip().split(":")
    if len(parts) < 5:
        raise RiotClientError("Lockfile du client Riot illisible.")
    return {"port": parts[2], "password": parts[3], "protocol": parts[4]}


def _local_request(path: str, method: str = "GET"):
    info = read_lockfile()
    url = f"{info['protocol']}://127.0.0.1:{info['port']}{path}"
    auth = base64.b64encode(f"riot:{info['password']}".encode()).decode()
    req = urllib.request.Request(url, method=method,
                                 data=b"" if method != "GET" else None,
                                 headers={"Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(req, context=_SSL_LOCAL, timeout=6) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        if e.code in (400, 404, 409):
            raise RiotClientError(
                "Aucun compte connecté dans le client Riot.\n"
                "Ouvre la fenêtre du client Riot et connecte-toi.")
        raise RiotClientError(f"Erreur du client Riot (HTTP {e.code}).")
    except (urllib.error.URLError, OSError):
        raise RiotClientError("Impossible de contacter le client Riot.")


def get_tokens() -> dict:
    """Jetons de session du compte connecté : accessToken, token (entitlement), subject (PUUID)."""
    data = _local_request("/entitlements/v1/token")
    if not data.get("accessToken"):
        raise RiotClientError("Aucun compte connecté dans le client Riot.")
    return data


def get_chat_session() -> dict:
    """Session du compte connecté : game_name, game_tag, puuid, region, state..."""
    return _local_request("/chat/v1/session")


def get_riot_id() -> str:
    """Riot ID du compte connecté, ex : 'Player#EUW'. Chaîne vide si indisponible."""
    try:
        s = get_chat_session()
        name, tag = s.get("game_name"), s.get("game_tag")
        if name and tag:
            return f"{name}#{tag}"
    except (RiotClientError, ValueError):
        pass
    try:
        info = _local_request("/riot-client-auth/v1/userinfo")
        acct = info.get("acct") or {}
        if acct.get("game_name") and acct.get("tag_line"):
            return f"{acct['game_name']}#{acct['tag_line']}"
    except (RiotClientError, ValueError):
        pass
    return ""


def _candidate_hosts() -> list[str]:
    """Hôtes player-preferences à essayer, le plus probable en premier."""
    hosts = []
    try:
        region = (get_chat_session().get("region") or "").lower()
        affinity = REGION_TO_AFFINITY.get(region)
        if affinity:
            hosts.append(PREFS_HOSTS[affinity])
    except RiotClientError:
        pass
    for h in PREFS_HOSTS.values():
        if h not in hosts:
            hosts.append(h)
    return hosts


def _cloud_request(method: str, url: str, tokens: dict, body: dict | None = None):
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=payload, method=method, headers={
        "Authorization": f"Bearer {tokens['accessToken']}",
        "X-Riot-Entitlements-JWT": tokens["token"],
        "X-Riot-ClientPlatform": _PLATFORM,
        "User-Agent": _UA,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_reason(code: int) -> str:
    """Message lisible pour un code HTTP. Un 401/403 signifie en général que
    Riot a rejeté nos en-têtes (User-Agent/plateforme) : c'est le symptôme
    typique d'une évolution de leur API — l'appli a alors besoin d'une mise à
    jour, plutôt qu'un simple « HTTP 403 » opaque."""
    if code in (401, 403):
        return (f"HTTP {code} — accès refusé par Riot. Une mise à jour de "
                "l'appli est probablement nécessaire (l'API Riot a pu changer).")
    return f"HTTP {code}"


def get_cloud_settings(tokens: dict) -> dict:
    """Paramètres cloud du compte connecté : {'type', 'data', 'modified', 'host'}.

    Le champ 'host' mémorise le serveur qui a répondu, pour que l'écriture
    (put_cloud_settings) aille au même endroit."""
    last_error = None
    for host in _candidate_hosts():
        try:
            result = _cloud_request(
                "GET", f"{host}/playerPref/v3/getPreference/{SETTINGS_TYPE}", tokens)
            if result.get("data"):
                result["host"] = host
                return result
        except urllib.error.HTTPError as e:
            last_error = _http_reason(e.code)
        except (urllib.error.URLError, OSError) as e:
            last_error = str(e)
    raise RiotClientError(
        f"Paramètres cloud introuvables ({last_error or 'aucune réponse'}).")


def find_riot_client() -> Path | None:
    """Chemin de RiotClientServices.exe via le fichier d'installation standard."""
    installs = Path(os.environ.get("ALLUSERSPROFILE", r"C:\ProgramData")) / "Riot Games" / "RiotClientInstalls.json"
    try:
        data = json.loads(installs.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for key in ("rc_default", "rc_live", "rc_beta"):
        p = data.get(key)
        if p and Path(p).is_file():
            return Path(p)
    return None


def launch_riot_client(product: str | None = None) -> bool:
    """Ouvre le client Riot (ou lance un jeu si `product` est fourni, ex 'valorant').

    Quand le client tourne déjà, relancer l'exe avec --launch-product ne fait
    que réveiller la fenêtre existante sans démarrer le jeu (clients Riot
    récents) : on passe alors par son API locale — l'endpoint product-launcher,
    celui que le client utilise lui-même. L'exe ne sert que si le client est
    fermé (démarrage à froid, où --launch-product fonctionne)."""
    if product:
        try:
            _local_request(
                f"/product-launcher/v1/products/{product}/patchlines/live",
                method="POST")
            return True
        except RiotClientError:
            pass  # client fermé (pas de lockfile) : lancement par l'exe
    exe = find_riot_client()
    if not exe:
        return False
    import subprocess
    args = [str(exe)]
    if product:
        args += [f"--launch-product={product}", "--launch-patchline=live"]
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    subprocess.Popen(args, creationflags=flags, close_fds=True)
    return True


def decode_settings_blob(data: str) -> dict | None:
    """Décode le blob cloud (base64 + deflate brut) en JSON lisible, ou None."""
    try:
        raw = base64.b64decode(data)
        return json.loads(zlib.decompress(raw, -15))
    except Exception:
        return None


def encode_settings_blob(settings: dict) -> str:
    """Ré-encode des réglages en blob cloud (JSON + deflate brut + base64).

    Exactement l'inverse de decode_settings_blob. Le service Riot stocke ce
    blob tel quel (il ne le lit pas) ; c'est le jeu qui le décompresse et
    parse le JSON — la mise en forme du JSON n'a donc pas d'importance, seul
    son contenu compte. Indispensable pour n'appliquer qu'une partie des
    réglages : on relit ceux du compte cible, on y injecte la catégorie
    choisie, et on ré-encode le tout."""
    raw = json.dumps(settings, ensure_ascii=False).encode("utf-8")
    comp = zlib.compressobj(wbits=-15)
    return base64.b64encode(comp.compress(raw) + comp.flush()).decode()


def put_cloud_settings(tokens: dict, settings: dict) -> dict:
    """Écrit les paramètres cloud sur le compte CONNECTÉ.

    Le serveur est choisi d'après la région du compte connecté — pas d'après
    le 'host' mémorisé dans `settings`, qui est celui du compte SOURCE du
    profil (les deux comptes peuvent être de régions différentes).
    `settings` = dict avec au minimum {'data': ...}."""
    body = {"type": SETTINGS_TYPE, "data": settings["data"]}
    last_error = None
    for host in _candidate_hosts():
        try:
            return _cloud_request("PUT", f"{host}/playerPref/v3/savePreference", tokens, body)
        except urllib.error.HTTPError as e:
            last_error = _http_reason(e.code)
        except (urllib.error.URLError, OSError):
            raise RiotClientError("Impossible de contacter les serveurs Riot (connexion internet ?).")
    raise RiotClientError(f"Écriture des paramètres cloud refusée ({last_error}).")
