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
  single_instance.py — verrou d'instance unique
"""

import sys
from pathlib import Path

import customtkinter as ctk

import i18n
import single_instance
from app import App
from appinfo import PROFILE_EXT
from core import ensure_dirs, load_settings, register_file_association
from logutil import log, setup_logging


def main():
    ensure_dirs()
    setup_logging()
    log.info("Démarrage %s", " ".join(sys.argv[1:]) or "(sans argument)")
    settings = load_settings()
    i18n.set_lang(settings.get("lang", "fr"))

    # Fichier .vcmprofile passé en argument (double-clic)
    import_args = [a for a in sys.argv[1:]
                   if a.lower().endswith(PROFILE_EXT) and Path(a).is_file()]
    first_import = import_args[0] if import_args else ""
    selftest = "--selftest" in sys.argv

    # Instance unique : si une fenêtre tourne déjà, on la réactive (en lui
    # transmettant le fichier à importer) et on ne rouvre pas de 2e fenêtre.
    server_sock = None if selftest else single_instance.acquire()
    if server_sock is None and not selftest:
        if single_instance.signal_primary(first_import):
            return
        # L'autre instance ne répond pas (fermeture en cours ?) : on démarre
        # quand même, sans écouter — un cas de course rare.

    register_file_association()
    ctk.set_appearance_mode("dark")
    app = App()
    if server_sock is not None:
        single_instance.serve(server_sock, app.handle_activation)
    if first_import:
        app.after(700, lambda: app.import_profile(path=first_import))
    if selftest:
        app.after(2500, app.destroy)
    app.mainloop()


if __name__ == "__main__":
    main()
