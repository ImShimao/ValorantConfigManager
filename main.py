# -*- coding: utf-8 -*-
"""Valorant Config Manager — point d'entrée.

Sauvegarde et transfère les paramètres Valorant (vidéo, crosshair,
sensibilité, keybinds...) entre plusieurs comptes Riot sur ce PC.

Modules :
  appinfo.py    — métadonnées de l'appli et ressources embarquées
  i18n.py       — langue de l'interface (FR/EN)
  theme.py      — couleurs, polices, icônes
  core.py       — logique sans interface (comptes, profils, sauvegardes)
  riot_cloud.py — accès au client Riot local + paramètres cloud
  dialogs.py    — boîtes de dialogue personnalisées
  app.py        — fenêtre principale
"""

import sys
from pathlib import Path

import customtkinter as ctk

import i18n
from app import App
from appinfo import PROFILE_EXT
from core import ensure_dirs, load_settings, register_file_association


def main():
    ensure_dirs()
    settings = load_settings()
    i18n.set_lang(settings.get("lang", "fr"))
    register_file_association()
    ctk.set_appearance_mode("dark")
    app = App()
    # Fichier .vcmprofile passé en argument (double-clic)
    import_args = [a for a in sys.argv[1:]
                   if a.lower().endswith(PROFILE_EXT) and Path(a).is_file()]
    if import_args:
        app.after(700, lambda: app.import_profile(path=import_args[0]))
    if "--selftest" in sys.argv:
        app.after(2500, app.destroy)
    app.mainloop()


if __name__ == "__main__":
    main()
