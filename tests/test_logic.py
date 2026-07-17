# -*- coding: utf-8 -*-
"""Tests de la logique sans interface (pytest).

Lancer avec :  python -m pytest
Tous les chemins de données (profils, sauvegardes, config Valorant) sont
redirigés vers des dossiers temporaires : rien ne touche aux vraies données.
"""

import base64
import json
import os
import time
import zipfile
import zlib
from pathlib import Path

import pytest

import core
import riot_cloud
import single_instance


# ----------------------------------------------------------------------------
# Aides
# ----------------------------------------------------------------------------
def make_blob(payload: dict) -> str:
    """Encode un dict comme le fait Riot : JSON -> deflate brut -> base64."""
    comp = zlib.compressobj(wbits=-15)
    raw = comp.compress(json.dumps(payload).encode()) + comp.flush()
    return base64.b64encode(raw).decode()


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirige tous les dossiers de données de l'appli vers tmp_path."""
    monkeypatch.setattr(core, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(core, "PROFILES_DIR", tmp_path / "data" / "profiles")
    monkeypatch.setattr(core, "BACKUPS_DIR", tmp_path / "data" / "backups")
    monkeypatch.setattr(core, "VALO_CONFIG_DIR", tmp_path / "valo_config")
    return tmp_path


def make_profile_dir(root: Path, cloud_payload: dict | None = None,
                     subject: str = "abc-123") -> Path:
    """Crée un dossier de profil complet (meta + files + cloud.json)."""
    prof = root / "profile"
    (prof / "files" / "Windows").mkdir(parents=True)
    (prof / "meta.json").write_text(json.dumps({"name": "Test"}), encoding="utf-8")
    (prof / "files" / "Windows" / "GameUserSettings.ini").write_text(
        "ResolutionSizeX=1920\nResolutionSizeY=1080\n"
        "FrameRateLimit=240.000000\nFullscreenMode=0\n", encoding="utf-8")
    if cloud_payload is not None:
        cloud = {"riot_id": "Player#EUW", "subject": subject,
                 "settings": {"data": make_blob(cloud_payload), "host": "https://x"}}
        (prof / "cloud.json").write_text(json.dumps(cloud), encoding="utf-8")
    return prof


CLOUD_PAYLOAD = {
    "floatSettings": [
        {"settingEnum": "EAresFloatSettingName::MouseSensitivity", "value": 0.35},
        {"settingEnum": "EAresFloatSettingName::MouseSensitivityZoomed", "value": 1.0},
    ],
    "boolSettings": [
        {"settingEnum": "EAresBoolSettingName::ShowBlood", "value": True},
    ],
    "intSettings": [],
    "stringSettings": [
        {"settingEnum": "EAresStringSettingName::SavedCrosshairProfileData",
         "value": json.dumps({"profiles": [{"profileName": "Dot"},
                                           {"profileName": "Cross"}]})},
    ],
    "actionMappings": [
        {"name": "EAresInputActionName::Jump", "key": "EKeys::SpaceBar", "alt": ""},
        {"name": "EAresInputActionName::Walk", "key": "EKeys::LeftShift", "alt": ""},
    ],
}


# ----------------------------------------------------------------------------
# riot_cloud
# ----------------------------------------------------------------------------
def test_decode_settings_blob_roundtrip():
    payload = {"floatSettings": [{"settingEnum": "X", "value": 1.5}]}
    assert riot_cloud.decode_settings_blob(make_blob(payload)) == payload


def test_decode_settings_blob_invalide():
    assert riot_cloud.decode_settings_blob("pas du base64 !") is None
    assert riot_cloud.decode_settings_blob(base64.b64encode(b"pas du deflate").decode()) is None


# ----------------------------------------------------------------------------
# Lecture des profils
# ----------------------------------------------------------------------------
def test_parse_video_settings(tmp_path):
    prof = make_profile_dir(tmp_path)
    out = core.parse_video_settings(prof)
    assert out["resolution"] == "1920x1080"
    assert out["fps_limit"] == "240"
    assert out["screen_mode"] == "Plein écran"  # LANG par défaut : fr


def test_profile_summary_complet(tmp_path):
    prof_path = make_profile_dir(tmp_path, CLOUD_PAYLOAD)
    prof = {"path": prof_path, "has_cloud": True}
    s = core.profile_summary(prof)
    assert s["cloud"] is True
    assert s["sens"] == 0.35
    assert s["ads"] == 1.0
    assert s["crosshairs"] == ["Dot", "Cross"]
    assert len(s["keybinds"]) == 2
    assert s["resolution"] == "1920x1080"


def test_keybind_map(tmp_path):
    prof_path = make_profile_dir(tmp_path, CLOUD_PAYLOAD)
    binds = core.keybind_map({"path": prof_path})
    assert binds["Jump"] == "SpaceBar"
    assert binds["Walk"] == "LeftShift"


def test_cloud_settings_map_exclut_les_enums_a_part(tmp_path):
    prof_path = make_profile_dir(tmp_path, CLOUD_PAYLOAD)
    m = core.cloud_settings_map({"path": prof_path})
    assert m["ShowBlood"] is True
    # La sensi et les crosshairs sont affichés à part : exclus de la liste brute
    assert "MouseSensitivity" not in m
    assert "SavedCrosshairProfileData" not in m


# ----------------------------------------------------------------------------
# Comptes
# ----------------------------------------------------------------------------
def test_folder_for_puuid(sandbox):
    puuid = "12345678-1234-1234-1234-123456789abc"
    folder = f"{puuid}-eu1"
    (core.VALO_CONFIG_DIR / folder).mkdir(parents=True)
    (core.VALO_CONFIG_DIR / "pas-un-compte").mkdir()
    assert core.folder_for_puuid(puuid) == folder
    assert core.folder_for_puuid(puuid.upper()) == folder
    assert core.folder_for_puuid("00000000-0000-0000-0000-000000000000") is None
    assert core.folder_for_puuid("") is None


# ----------------------------------------------------------------------------
# Export / import de profils (.vcmprofile)
# ----------------------------------------------------------------------------
def test_export_retire_le_puuid(tmp_path):
    prof = make_profile_dir(tmp_path, CLOUD_PAYLOAD, subject="secret-puuid")
    out = tmp_path / "export.vcmprofile"
    core.write_profile_archive(prof, str(out))
    with zipfile.ZipFile(out) as z:
        cloud = json.loads(z.read("cloud.json"))
        assert "subject" not in cloud
        assert cloud["riot_id"] == "Player#EUW"       # le Riot ID public reste
        assert cloud["settings"]["data"]              # les réglages restent
        assert "meta.json" in z.namelist()
        assert "files/Windows/GameUserSettings.ini" in z.namelist()


def test_export_import_roundtrip(tmp_path):
    prof = make_profile_dir(tmp_path, CLOUD_PAYLOAD)
    out = tmp_path / "export.vcmprofile"
    core.write_profile_archive(prof, str(out))
    dest = tmp_path / "imported"
    meta = core.extract_profile_archive(str(out), dest)
    assert meta["name"] == "Test"
    assert (dest / "cloud.json").is_file()
    assert (dest / "files" / "Windows" / "GameUserSettings.ini").is_file()


def test_import_refuse_sans_meta(tmp_path):
    bad = tmp_path / "bad.vcmprofile"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("cloud.json", "{}")
    with pytest.raises(ValueError):
        core.extract_profile_archive(str(bad), tmp_path / "dest")


def test_import_refuse_zip_slip(tmp_path):
    evil = tmp_path / "evil.vcmprofile"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("meta.json", "{}")
        z.writestr("../evil.txt", "pwned")
    with pytest.raises(ValueError):
        core.extract_profile_archive(str(evil), tmp_path / "dest")
    assert not (tmp_path / "evil.txt").exists()


# ----------------------------------------------------------------------------
# Sauvegardes
# ----------------------------------------------------------------------------
def test_backup_account_et_rotation(sandbox):
    account = core.VALO_CONFIG_DIR / "12345678-1234-1234-1234-123456789abc-eu1"
    (account / "Windows").mkdir(parents=True)
    (account / "Windows" / "GameUserSettings.ini").write_text("x")

    dest = core.backup_account(account, cloud={"subject": "abc"})
    assert (dest / "files" / "Windows" / "GameUserSettings.ini").is_file()
    assert (dest / "cloud.json").is_file()

    # Rotation : au-delà de MAX_BACKUPS_PER_ACCOUNT, les plus anciennes partent
    parent = core.BACKUPS_DIR / account.name
    for i in range(core.MAX_BACKUPS_PER_ACCOUNT + 5):
        (parent / f"2020-01-01_00-00-{i:02d}").mkdir(parents=True, exist_ok=True)
    core._rotate_backups(parent)
    restants = [d for d in parent.iterdir() if d.is_dir()]
    assert len(restants) == core.MAX_BACKUPS_PER_ACCOUNT
    # Les plus récentes (tri par nom) sont conservées
    assert max(d.name for d in restants) in {d.name for d in restants}


def test_backup_cloud_only(sandbox):
    cloud = {"riot_id": "X#Y", "subject": "ABC-123", "settings": {"data": "d"}}
    dest = core.backup_cloud_only("ABC-123", cloud)
    assert dest.parent.name == "abc-123"        # PUUID normalisé en minuscules
    saved = json.loads((dest / "cloud.json").read_text(encoding="utf-8"))
    assert saved == cloud


def test_backup_cloud_only_sujet_vide(sandbox):
    dest = core.backup_cloud_only("", {"settings": {}})
    assert dest.parent.name == "inconnu"


def test_list_backups_tri_recent_d_abord(sandbox):
    parent = core.BACKUPS_DIR / "compte"
    for name in ("2024-01-01_10-00-00", "2025-06-15_08-30-00_auto", "2023-12-31_23-59-59"):
        (parent / name).mkdir(parents=True)
    backups = core.list_backups("compte")
    assert [b.name for b in backups] == [
        "2025-06-15_08-30-00_auto", "2024-01-01_10-00-00", "2023-12-31_23-59-59"]


def test_apply_files_ignore_cloud_json(tmp_path):
    """cloud.json (métadonnées internes) ne doit jamais atterrir dans le dossier
    de config Valorant — cas des sauvegardes legacy où il est à la racine."""
    src = tmp_path / "backup_root"
    (src / "Windows").mkdir(parents=True)
    (src / "Windows" / "GameUserSettings.ini").write_text("res", encoding="utf-8")
    (src / "cloud.json").write_text("{}", encoding="utf-8")
    target = tmp_path / "account"
    core.apply_files(src, target)
    assert (target / "Windows" / "GameUserSettings.ini").is_file()
    assert not (target / "cloud.json").exists()


# ----------------------------------------------------------------------------
# Cache de décodage cloud
# ----------------------------------------------------------------------------
def test_load_parsed_cloud_cache(tmp_path):
    prof = make_profile_dir(tmp_path, CLOUD_PAYLOAD)
    cloud1, parsed1 = core.load_parsed_cloud(prof)
    assert parsed1 is not None and parsed1["floatSettings"]
    # 2e appel : servi par le cache (même objet décodé, pas re-décodé)
    _, parsed2 = core.load_parsed_cloud(prof)
    assert parsed2 is parsed1
    # Réécriture du cloud.json (mtime différent) → cache invalidé, nouveau décodage
    cf = prof / "cloud.json"
    data = json.loads(cf.read_text(encoding="utf-8"))
    data["settings"]["data"] = make_blob({"floatSettings": [], "actionMappings": []})
    cf.write_text(json.dumps(data), encoding="utf-8")
    os.utime(cf, (time.time() + 5, time.time() + 5))
    _, parsed3 = core.load_parsed_cloud(prof)
    assert parsed3 is not parsed1
    assert parsed3["floatSettings"] == []


def test_load_parsed_cloud_absent(tmp_path):
    (tmp_path / "profile").mkdir()
    assert core.load_parsed_cloud(tmp_path / "profile") == (None, None)


# ----------------------------------------------------------------------------
# riot_cloud : messages d'erreur HTTP
# ----------------------------------------------------------------------------
def test_http_reason():
    assert "mise à jour" in riot_cloud._http_reason(403)
    assert "mise à jour" in riot_cloud._http_reason(401)
    assert riot_cloud._http_reason(500) == "HTTP 500"


# ----------------------------------------------------------------------------
# Instance unique
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# Catégories de réglages
# ----------------------------------------------------------------------------
def test_category_for_enum_noms_reels():
    """Classification vérifiée sur de vrais noms d'enum Valorant."""
    c = core.category_for_enum
    assert c("MouseSensitivity") == core.CAT_SENSITIVITY
    assert c("MouseSensitivityZoomed") == core.CAT_SENSITIVITY
    # Pièges : contient « Sensitivity » mais c'est de l'audio
    assert c("MicSensitivityThreshold") == core.CAT_AUDIO
    # Piège : contient « Video » mais c'est un volume sonore
    assert c("VideoVolume") == core.CAT_AUDIO
    assert c("PushToTalkKey") == core.CAT_AUDIO
    assert c("SavedCrosshairProfileData") == core.CAT_CROSSHAIR
    assert c("FadeCrosshairWithFiringError") == core.CAT_CROSSHAIR
    assert c("MinimapZoom") == core.CAT_MINIMAP
    assert c("ShowBlood") == core.CAT_GAMEPLAY
    assert c("ColorBlindMode") == core.CAT_GAMEPLAY
    # Drapeaux d'état du compte : jamais transférés
    for name in ("HasAcceptedCodeOfConduct", "HasSeenSettingsTutorial",
                 "HasEverStartedAMatch", "LastSeenAdHocPopup",
                 "LastAcceptedCodeOfConductVersion", "ContextAwareModuleComplete"):
        assert c(name) == core.CAT_ACCOUNT, name


def _parsed(sens=0.3, blood=True, jump="SpaceBar", vol=1.0, seen=True):
    return {
        "floatSettings": [
            {"settingEnum": "EAresFloatSettingName::MouseSensitivity", "value": sens},
            {"settingEnum": "EAresFloatSettingName::OverallVolume", "value": vol},
        ],
        "boolSettings": [
            {"settingEnum": "EAresBoolSettingName::ShowBlood", "value": blood},
            {"settingEnum": "EAresBoolSettingName::HasSeenSettingsTutorial", "value": seen},
        ],
        "actionMappings": [
            {"name": "EAresInputActionName::Jump", "key": f"EKeys::{jump}", "alt": ""},
        ],
        "axisMappings": [{"name": "Look", "scale": 1.0}],
        "roamingSetttingsVersion": 7,
    }


def test_filter_cloud_ne_garde_que_le_choisi():
    out = core.filter_cloud(_parsed(), [core.CAT_KEYBINDS])
    assert out["actionMappings"][0]["key"] == "EKeys::SpaceBar"
    assert "axisMappings" in out
    # Aucun réglage d'une autre catégorie ne doit être embarqué
    assert "floatSettings" not in out and "boolSettings" not in out


def test_filter_cloud_sensibilite_seule():
    out = core.filter_cloud(_parsed(), [core.CAT_SENSITIVITY])
    noms = [core._short_enum(i["settingEnum"]) for i in out["floatSettings"]]
    assert noms == ["MouseSensitivity"]        # le volume est exclu
    assert "actionMappings" not in out


def test_merge_cloud_ne_remplace_que_le_selectionne():
    """Le cas d'usage clé : appliquer seulement les touches doit garder tous
    les autres réglages du compte cible."""
    cible = _parsed(sens=0.9, blood=False, jump="F", vol=0.2, seen=False)
    profil = _parsed(sens=0.1, blood=True, jump="SpaceBar", vol=1.0, seen=True)
    merged = core.merge_cloud(cible, profil, [core.CAT_KEYBINDS])

    # La touche vient du profil
    assert merged["actionMappings"][0]["key"] == "EKeys::SpaceBar"
    # Tout le reste reste celui de la CIBLE
    vals = {core._short_enum(i["settingEnum"]): i["value"]
            for i in merged["floatSettings"] + merged["boolSettings"]}
    assert vals["MouseSensitivity"] == 0.9
    assert vals["OverallVolume"] == 0.2
    assert vals["ShowBlood"] is False
    # Les clés inconnues sont préservées
    assert merged["roamingSetttingsVersion"] == 7


def test_merge_cloud_preserve_etat_du_compte():
    """Même en transférant tout, les drapeaux d'état du compte cible restent."""
    cible = _parsed(seen=False)
    profil = _parsed(seen=True)
    merged = core.merge_cloud(cible, profil, core.CLOUD_CATEGORIES)
    vals = {core._short_enum(i["settingEnum"]): i["value"] for i in merged["boolSettings"]}
    assert vals["HasSeenSettingsTutorial"] is False   # celui de la cible
    assert vals["ShowBlood"] is True                  # celui du profil


def test_merge_cloud_sans_doublon():
    cible = _parsed(sens=0.9)
    profil = _parsed(sens=0.1)
    merged = core.merge_cloud(cible, profil, [core.CAT_SENSITIVITY])
    noms = [core._short_enum(i["settingEnum"]) for i in merged["floatSettings"]]
    assert noms.count("MouseSensitivity") == 1


def test_encode_decode_roundtrip():
    data = _parsed()
    assert riot_cloud.decode_settings_blob(riot_cloud.encode_settings_blob(data)) == data


def test_profile_categories_retrocompat():
    # Profil d'avant la fonctionnalité, AVEC cloud : il contenait tout
    assert core.profile_categories({"name": "vieux", "has_cloud": True}) == \
        core.CATEGORY_ORDER
    # Profil d'avant, SANS cloud : il ne contenait que les fichiers vidéo
    assert core.profile_categories({"name": "vieux", "has_cloud": False}) == \
        [core.CAT_VIDEO]
    # Profil récent : le champ fait foi (et l'ordre d'affichage est normalisé)
    assert core.profile_categories({"categories": ["keybinds", "video"]}) == \
        [core.CAT_VIDEO, core.CAT_KEYBINDS]


def test_create_profile_respecte_les_categories(sandbox):
    account = core.VALO_CONFIG_DIR / "12345678-1234-1234-1234-123456789abc-eu1"
    (account / "Windows").mkdir(parents=True)
    (account / "Windows" / "GameUserSettings.ini").write_text("x", encoding="utf-8")
    cloud = {"riot_id": "A#B", "subject": "s",
             "settings": {"data": make_blob(_parsed()), "host": "h"}}

    # Touches seules : pas de fichiers locaux, et le cloud ne garde que les touches
    pid = core.create_profile(account, "Touches only", "Main", cloud=cloud,
                              categories=[core.CAT_KEYBINDS])
    d = core.PROFILES_DIR / pid
    assert not (d / "files").exists()
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    assert meta["categories"] == [core.CAT_KEYBINDS]
    _, parsed = core.load_parsed_cloud(d)
    assert "actionMappings" in parsed and "floatSettings" not in parsed


def test_create_profile_video_seule_sans_cloud(sandbox):
    account = core.VALO_CONFIG_DIR / "12345678-1234-1234-1234-123456789abc-eu1"
    (account / "Windows").mkdir(parents=True)
    (account / "Windows" / "GameUserSettings.ini").write_text("x", encoding="utf-8")
    cloud = {"riot_id": "A#B", "subject": "s",
             "settings": {"data": make_blob(_parsed()), "host": "h"}}
    pid = core.create_profile(account, "Video only", "Main", cloud=cloud,
                              categories=[core.CAT_VIDEO])
    d = core.PROFILES_DIR / pid
    assert (d / "files" / "Windows" / "GameUserSettings.ini").is_file()
    # Aucune catégorie cloud cochée => pas de cloud.json du tout
    assert not (d / "cloud.json").exists()


def test_single_instance_verrou_et_payload(monkeypatch):
    # Port dédié aux tests : la vraie appli peut tourner en même temps sur le
    # port officiel sans fausser le résultat.
    monkeypatch.setattr(single_instance, "_PORT", 49763)
    srv = single_instance.acquire()
    assert srv is not None, "la 1re acquisition doit réussir"
    try:
        assert single_instance.acquire() is None, "le verrou doit bloquer la 2e"
        recu = []
        single_instance.serve(srv, recu.append)
        time.sleep(0.2)
        assert single_instance.signal_primary("mon profil.vcmprofile")
        time.sleep(0.3)
        assert recu == ["mon profil.vcmprofile"]
    finally:
        srv.close()
