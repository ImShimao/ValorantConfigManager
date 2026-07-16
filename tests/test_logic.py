# -*- coding: utf-8 -*-
"""Tests de la logique sans interface (pytest).

Lancer avec :  python -m pytest
Tous les chemins de données (profils, sauvegardes, config Valorant) sont
redirigés vers des dossiers temporaires : rien ne touche aux vraies données.
"""

import base64
import json
import zipfile
import zlib
from pathlib import Path

import pytest

import main
import riot_cloud


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
    monkeypatch.setattr(main, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(main, "PROFILES_DIR", tmp_path / "data" / "profiles")
    monkeypatch.setattr(main, "BACKUPS_DIR", tmp_path / "data" / "backups")
    monkeypatch.setattr(main, "VALO_CONFIG_DIR", tmp_path / "valo_config")
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
    out = main.parse_video_settings(prof)
    assert out["resolution"] == "1920x1080"
    assert out["fps_limit"] == "240"
    assert out["screen_mode"] == "Plein écran"  # LANG par défaut : fr


def test_profile_summary_complet(tmp_path):
    prof_path = make_profile_dir(tmp_path, CLOUD_PAYLOAD)
    prof = {"path": prof_path, "has_cloud": True}
    s = main.profile_summary(prof)
    assert s["cloud"] is True
    assert s["sens"] == 0.35
    assert s["ads"] == 1.0
    assert s["crosshairs"] == ["Dot", "Cross"]
    assert len(s["keybinds"]) == 2
    assert s["resolution"] == "1920x1080"


def test_keybind_map(tmp_path):
    prof_path = make_profile_dir(tmp_path, CLOUD_PAYLOAD)
    binds = main.keybind_map({"path": prof_path})
    assert binds["Jump"] == "SpaceBar"
    assert binds["Walk"] == "LeftShift"


def test_cloud_settings_map_exclut_les_enums_a_part(tmp_path):
    prof_path = make_profile_dir(tmp_path, CLOUD_PAYLOAD)
    m = main.cloud_settings_map({"path": prof_path})
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
    (main.VALO_CONFIG_DIR / folder).mkdir(parents=True)
    (main.VALO_CONFIG_DIR / "pas-un-compte").mkdir()
    assert main.folder_for_puuid(puuid) == folder
    assert main.folder_for_puuid(puuid.upper()) == folder
    assert main.folder_for_puuid("00000000-0000-0000-0000-000000000000") is None
    assert main.folder_for_puuid("") is None


# ----------------------------------------------------------------------------
# Export / import de profils (.vcmprofile)
# ----------------------------------------------------------------------------
def test_export_retire_le_puuid(tmp_path):
    prof = make_profile_dir(tmp_path, CLOUD_PAYLOAD, subject="secret-puuid")
    out = tmp_path / "export.vcmprofile"
    main.write_profile_archive(prof, str(out))
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
    main.write_profile_archive(prof, str(out))
    dest = tmp_path / "imported"
    meta = main.extract_profile_archive(str(out), dest)
    assert meta["name"] == "Test"
    assert (dest / "cloud.json").is_file()
    assert (dest / "files" / "Windows" / "GameUserSettings.ini").is_file()


def test_import_refuse_sans_meta(tmp_path):
    bad = tmp_path / "bad.vcmprofile"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("cloud.json", "{}")
    with pytest.raises(ValueError):
        main.extract_profile_archive(str(bad), tmp_path / "dest")


def test_import_refuse_zip_slip(tmp_path):
    evil = tmp_path / "evil.vcmprofile"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("meta.json", "{}")
        z.writestr("../evil.txt", "pwned")
    with pytest.raises(ValueError):
        main.extract_profile_archive(str(evil), tmp_path / "dest")
    assert not (tmp_path / "evil.txt").exists()


# ----------------------------------------------------------------------------
# Sauvegardes
# ----------------------------------------------------------------------------
def test_backup_account_et_rotation(sandbox):
    account = main.VALO_CONFIG_DIR / "12345678-1234-1234-1234-123456789abc-eu1"
    (account / "Windows").mkdir(parents=True)
    (account / "Windows" / "GameUserSettings.ini").write_text("x")

    dest = main.backup_account(account, cloud={"subject": "abc"})
    assert (dest / "files" / "Windows" / "GameUserSettings.ini").is_file()
    assert (dest / "cloud.json").is_file()

    # Rotation : au-delà de MAX_BACKUPS_PER_ACCOUNT, les plus anciennes partent
    parent = main.BACKUPS_DIR / account.name
    for i in range(main.MAX_BACKUPS_PER_ACCOUNT + 5):
        (parent / f"2020-01-01_00-00-{i:02d}").mkdir(parents=True, exist_ok=True)
    main._rotate_backups(parent)
    restants = [d for d in parent.iterdir() if d.is_dir()]
    assert len(restants) == main.MAX_BACKUPS_PER_ACCOUNT
    # Les plus récentes (tri par nom) sont conservées
    assert max(d.name for d in restants) in {d.name for d in restants}


def test_backup_cloud_only(sandbox):
    cloud = {"riot_id": "X#Y", "subject": "ABC-123", "settings": {"data": "d"}}
    dest = main.backup_cloud_only("ABC-123", cloud)
    assert dest.parent.name == "abc-123"        # PUUID normalisé en minuscules
    saved = json.loads((dest / "cloud.json").read_text(encoding="utf-8"))
    assert saved == cloud


def test_backup_cloud_only_sujet_vide(sandbox):
    dest = main.backup_cloud_only("", {"settings": {}})
    assert dest.parent.name == "inconnu"


def test_list_backups_tri_recent_d_abord(sandbox):
    parent = main.BACKUPS_DIR / "compte"
    for name in ("2024-01-01_10-00-00", "2025-06-15_08-30-00_auto", "2023-12-31_23-59-59"):
        (parent / name).mkdir(parents=True)
    backups = main.list_backups("compte")
    assert [b.name for b in backups] == [
        "2025-06-15_08-30-00_auto", "2024-01-01_10-00-00", "2023-12-31_23-59-59"]
