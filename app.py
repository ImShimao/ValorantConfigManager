# -*- coding: utf-8 -*-
"""Fenêtre principale de l'application."""

import ctypes
import json
import os
import re
import shutil
import threading
import uuid
import webbrowser
import zipfile
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox, filedialog
from PIL import Image

import i18n
import riot_cloud
import theme
from appinfo import (APP_ID, APP_NAME, APP_VERSION, GITHUB_URL, PROFILE_EXT,
                     resource_path)
from core import (VALO_CONFIG_DIR, BACKUPS_DIR, DATA_DIR, PROFILES_DIR,
                  apply_files, backup_account, backup_cloud_only,
                  cloud_settings_map, create_profile, ensure_dirs,
                  extract_profile_archive, fmt_date, folder_for_puuid,
                  is_valorant_running, keybind_map, list_accounts,
                  list_backups, list_profiles, load_account_names,
                  load_settings, profile_summary, read_profile_cloud,
                  save_account_names, save_settings, short_id,
                  write_profile_archive)
from dialogs import ChoiceDialog, TextDialog
from i18n import T
from riot_cloud import RiotClientError
from theme import (C_BG, C_BORDER, C_CARD, C_CARD_HOVER, C_GREEN, C_ORANGE,
                   C_PANEL, C_RED, C_RED_HOVER, C_TEXT, C_TEXT_DIM, icon)

# ----------------------------------------------------------------------------
# Application principale
# ----------------------------------------------------------------------------
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.geometry("1100x720")
        self.minsize(960, 600)
        self.configure(fg_color=C_BG)
        self._set_window_icon()
        theme.init_fonts()

        self.settings = load_settings()
        self.account_names = load_account_names()
        self.connected_riot_id = ""     # Riot ID du compte connecté au client Riot
        self.connected_subject = ""     # PUUID du compte connecté
        self._last_seen_subject = ""    # dernier PUUID vu (pour détecter un changement)
        self._snapshotted = set()       # comptes déjà photographiés cette session
        self._banner = None
        self.tray = None

        self._build_ui()
        self.refresh()
        self._poll_status()
        self._setup_tray()
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

    def _build_ui(self):
        for w in self.winfo_children():
            w.destroy()
        self._banner = None
        self._build_header()
        self._build_statusbar()
        self._build_body()

    def _set_window_icon(self):
        ico = resource_path("icon.ico")
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
        if ico.is_file():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass
            # CustomTkinter remet son icône par défaut ~200 ms après le démarrage :
            # on repasse derrière lui.
            self.after(300, lambda: self._safe_iconbitmap(ico))

    def _safe_iconbitmap(self, ico: Path):
        try:
            self.iconbitmap(str(ico))
        except Exception:
            pass

    # ------------------------------------------------------------------ UI --
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0, height=72)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=20)
        logo = None
        try:
            ico = resource_path("icon.ico")
            if ico.is_file():
                logo = ctk.CTkImage(Image.open(ico).convert("RGBA"), size=(38, 38))
        except Exception:
            pass
        if logo is not None:
            ctk.CTkLabel(left, image=logo, text="").pack(side="left", padx=(0, 12))
        ctk.CTkLabel(left, text="VALORANT", font=(theme.FONT_TITLE, 26, "bold"),
                     text_color=C_RED).pack(side="left")
        ctk.CTkLabel(left, text=" CONFIG MANAGER", font=(theme.FONT_TITLE, 26),
                     text_color=C_TEXT).pack(side="left")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", padx=20)
        ctk.CTkButton(right, text=T(" Actualiser", " Refresh"), width=124, height=34,
                      image=icon("refresh", 15), compound="left", corner_radius=8,
                      fg_color=C_CARD, hover_color=C_CARD_HOVER, text_color=C_TEXT,
                      border_width=1, border_color=C_BORDER,
                      font=(theme.FONT_UI, 12), command=self.refresh).pack(side="right", padx=(10, 0))
        ctk.CTkButton(right, text=T(" Transfert express", " Express transfer"),
                      width=176, height=34,
                      image=icon("bolt", 15, "#ffffff"), compound="left", corner_radius=8,
                      fg_color=C_RED, hover_color=C_RED_HOVER,
                      font=(theme.FONT_UI, 12, "bold"),
                      command=self.express_transfer).pack(side="right", padx=(10, 0))
        ctk.CTkButton(right, text=T(" Lancer Valorant", " Launch Valorant"),
                      width=162, height=34,
                      image=icon("play", 15), compound="left", corner_radius=8,
                      fg_color=C_CARD, hover_color=C_CARD_HOVER, text_color=C_TEXT,
                      border_width=1, border_color=C_BORDER,
                      font=(theme.FONT_UI, 12),
                      command=self.launch_valorant).pack(side="right", padx=(10, 0))

    def _show_banner(self, riot_id: str):
        self._hide_banner()
        self._banner = ctk.CTkFrame(self, fg_color="#233648", corner_radius=0, height=44)
        self._banner.pack(fill="x", side="top", before=self.tabs)
        self._banner.pack_propagate(False)
        ctk.CTkLabel(self._banner, image=icon("user", 16, C_GREEN), compound="left",
                     text=T(f"  {riot_id} vient de se connecter — appliquer un profil sur ce compte ?",
                            f"  {riot_id} just logged in — apply a profile to this account?"),
                     font=(theme.FONT_UI, 13), text_color=C_TEXT).pack(side="left", padx=14)
        ctk.CTkButton(self._banner, text="", image=icon("close", 13, C_TEXT_DIM),
                      width=32, height=26,
                      fg_color="transparent", hover_color=C_CARD_HOVER, text_color=C_TEXT_DIM,
                      command=self._hide_banner).pack(side="right", padx=(0, 12))
        ctk.CTkButton(self._banner, text=T(" Transfert express", " Express transfer"),
                      image=icon("bolt", 14, "#ffffff"), compound="left",
                      width=155, height=28, corner_radius=8,
                      fg_color=C_RED, hover_color=C_RED_HOVER,
                      font=(theme.FONT_UI, 12, "bold"),
                      command=lambda: (self._hide_banner(), self.express_transfer())).pack(
            side="right", padx=8)

    def _hide_banner(self):
        if self._banner is not None:
            self._banner.destroy()
            self._banner = None

    def _build_body(self):
        self.tabs = ctk.CTkTabview(
            self, fg_color="transparent",
            segmented_button_fg_color=C_PANEL,
            segmented_button_selected_color=C_RED,
            segmented_button_selected_hover_color=C_RED_HOVER,
            segmented_button_unselected_color=C_PANEL,
            segmented_button_unselected_hover_color=C_CARD_HOVER,
            text_color=C_TEXT, command=self._on_tab_change)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(4, 6))
        name_manage = T("  Gestion  ", "  Manage  ")
        name_help = T("  Aide  ", "  Help  ")
        name_settings = T("  Paramètres  ", "  Settings  ")
        tab_main = self.tabs.add(name_manage)
        tab_help = self.tabs.add(name_help)
        tab_settings = self.tabs.add(name_settings)
        try:
            self.tabs._segmented_button.configure(font=(theme.FONT_TITLE, 14))
        except Exception:
            pass

        # Construction paresseuse : seul l'onglet Gestion est bâti tout de suite.
        # Aide et Paramètres (nombreux widgets) ne sont montés qu'à la première
        # ouverture — moins de widgets vivants = changement d'onglet fluide.
        self._lazy_tabs = {
            name_help: (tab_help, self._build_help),
            name_settings: (tab_settings, self._build_settings),
        }

        self._build_manage(tab_main)

    def _on_tab_change(self):
        name = self.tabs.get()
        builder = self._lazy_tabs.pop(name, None)
        if builder is not None:
            frame, build = builder
            build(frame)

    def _build_manage(self, tab_main):
        body = ctk.CTkFrame(tab_main, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=11, uniform="col")
        body.grid_columnconfigure(1, weight=10, uniform="col")
        body.grid_rowconfigure(0, weight=1)

        # --- Colonne comptes ---
        acc_panel = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=14,
                                 border_width=1, border_color=C_BORDER)
        acc_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(acc_panel, text=T("COMPTES DÉTECTÉS SUR CE PC", "ACCOUNTS FOUND ON THIS PC"),
                     image=icon("user", 17, C_RED), compound="left",
                     font=(theme.FONT_TITLE, 16), text_color=C_TEXT).pack(
            anchor="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(acc_panel,
                     text=T("Le compte utilisé le plus récemment apparaît en premier.",
                            "The most recently used account appears first."),
                     font=(theme.FONT_UI, 11), text_color=C_TEXT_DIM).pack(anchor="w", padx=18)
        self.accounts_frame = ctk.CTkScrollableFrame(acc_panel, fg_color="transparent")
        self.accounts_frame.pack(fill="both", expand=True, padx=10, pady=(8, 12))

        # --- Colonne profils ---
        prof_panel = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=14,
                                  border_width=1, border_color=C_BORDER)
        prof_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        top = ctk.CTkFrame(prof_panel, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(14, 2))
        ctk.CTkLabel(top, text=T("PROFILS ENREGISTRÉS", "SAVED PROFILES"),
                     image=icon("save", 17, C_RED), compound="left",
                     font=(theme.FONT_TITLE, 16),
                     text_color=C_TEXT).pack(side="left")
        ctk.CTkLabel(prof_panel, image=icon("cloud", 13, C_GREEN), compound="left",
                     text=T("  = crosshair, sensi et keybinds inclus (paramètres cloud Riot).",
                            "  = crosshair, sensitivity and keybinds included (Riot cloud settings)."),
                     font=(theme.FONT_UI, 11), text_color=C_TEXT_DIM).pack(anchor="w", padx=18)
        actions = ctk.CTkFrame(prof_panel, fg_color="transparent")
        actions.pack(fill="x", padx=18, pady=(8, 0))
        for label_fr, label_en, glyph, cmd in (
                (" Importer", " Import", "import", self.import_profile),
                (" Comparer", " Compare", "compare", self.compare_profiles),
                (" Restaurer", " Restore", "restore", self.restore_backup)):
            ctk.CTkButton(actions, text=T(label_fr, label_en), height=28,
                          image=icon(glyph, 13), compound="left", corner_radius=8,
                          fg_color=C_CARD, hover_color=C_CARD_HOVER, text_color=C_TEXT,
                          border_width=1, border_color=C_BORDER,
                          font=(theme.FONT_UI, 11), command=cmd).pack(
                side="left", fill="x", expand=True, padx=(0, 6))
        self.profiles_frame = ctk.CTkScrollableFrame(prof_panel, fg_color="transparent")
        self.profiles_frame.pack(fill="both", expand=True, padx=10, pady=(8, 12))

    def _build_help(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        def card(icon_name: str, title: str):
            c = ctk.CTkFrame(scroll, fg_color=C_PANEL, corner_radius=14,
                             border_width=1, border_color=C_BORDER)
            c.pack(fill="x", padx=4, pady=(0, 12))
            ctk.CTkLabel(c, image=icon(icon_name, 17, C_RED), compound="left",
                         text="  " + title.upper(), font=(theme.FONT_TITLE, 15),
                         text_color=C_RED).pack(anchor="w", padx=18, pady=(12, 2))
            body = ctk.CTkFrame(c, fg_color="transparent")
            body.pack(fill="x", padx=18, pady=(2, 14))
            return body

        def text(parent_, s: str, dim: bool = False):
            ctk.CTkLabel(parent_, text=s, font=(theme.FONT_UI, 12),
                         text_color=C_TEXT_DIM if dim else C_TEXT,
                         wraplength=830, justify="left", anchor="w").pack(
                anchor="w", fill="x", pady=2)

        def icon_row(parent_, icon_name: str, icon_color: str, name: str, desc: str):
            row = ctk.CTkFrame(parent_, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, image=icon(icon_name, 15, icon_color), text="",
                         width=30).pack(side="left")
            ctk.CTkLabel(row, text=name, font=(theme.FONT_UI, 12, "bold"), text_color=C_TEXT,
                         width=200, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=desc, font=(theme.FONT_UI, 12), text_color=C_TEXT_DIM,
                         wraplength=560, justify="left", anchor="w").pack(
                side="left", fill="x", expand=True)

        def step_row(parent_, n: int, s: str):
            row = ctk.CTkFrame(parent_, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=str(n), font=(theme.FONT_TITLE, 12),
                         text_color="#ffffff", fg_color=C_RED, corner_radius=12,
                         width=24, height=24).pack(side="left")
            ctk.CTkLabel(row, text=s, font=(theme.FONT_UI, 12), text_color=C_TEXT,
                         wraplength=780, justify="left", anchor="w").pack(
                side="left", padx=10, fill="x", expand=True)

        def qa(parent_, q: str, a: str):
            ctk.CTkLabel(parent_, text=q, font=(theme.FONT_UI, 12, "bold"),
                         text_color=C_TEXT, wraplength=830, justify="left",
                         anchor="w").pack(anchor="w", fill="x", pady=(8, 0))
            ctk.CTkLabel(parent_, text=a, font=(theme.FONT_UI, 12), text_color=C_TEXT_DIM,
                         wraplength=830, justify="left", anchor="w").pack(
                anchor="w", fill="x")

        # --- Comment ça marche -------------------------------------------------
        body = card("cloud", T("Comment ça marche ?", "How does it work?"))
        duo = ctk.CTkFrame(body, fg_color="transparent")
        duo.pack(fill="x", pady=(2, 6))
        duo.grid_columnconfigure((0, 1), weight=1, uniform="duo")
        for col, (title, desc) in enumerate((
                (T("FICHIERS LOCAUX", "LOCAL FILES"),
                 T("Réglages vidéo, stockés sur ce PC — un dossier par compte.",
                   "Video settings, stored on this PC — one folder per account.")),
                (T("CLOUD RIOT", "RIOT CLOUD"),
                 T("Crosshair, sensibilité, keybinds… stockés chez Riot et resynchronisés "
                   "à chaque connexion.",
                   "Crosshair, sensitivity, keybinds… stored on Riot's servers and re-synced "
                   "at every login.")))):
            box = ctk.CTkFrame(duo, fg_color=C_BG, corner_radius=10,
                               border_width=1, border_color=C_BORDER)
            box.grid(row=0, column=col, sticky="nsew", padx=(0, 8) if col == 0 else 0)
            ctk.CTkLabel(box, text=title, font=(theme.FONT_TITLE, 13),
                         text_color=C_ORANGE).pack(anchor="w", padx=14, pady=(10, 0))
            ctk.CTkLabel(box, text=desc, font=(theme.FONT_UI, 12), text_color=C_TEXT,
                         wraplength=370, justify="left", anchor="w").pack(
                anchor="w", padx=14, pady=(2, 12), fill="x")
        text(body, T("Au lancement, le jeu écrase les fichiers locaux avec le cloud : copier "
                     "des fichiers ne suffit donc pas. Ce logiciel transfère les deux, en "
                     "utilisant la session déjà ouverte du client Riot.",
                     "On launch, the game overwrites local files with the cloud: copying files "
                     "is not enough. This tool transfers both, using the session already open "
                     "in the Riot Client."))
        text(body, T("Aucun mot de passe demandé ni stocké, rien d'automatisé en jeu.",
                     "No password asked or stored, nothing automated in-game."), dim=True)

        # --- Pas à pas ---------------------------------------------------------
        body = card("bolt", T("Transférer sa config en 6 étapes",
                              "Transfer your config in 6 steps"))
        for n, s in enumerate((
                T("Ferme le JEU Valorant — le client Riot, lui, doit rester ouvert.",
                  "Close the Valorant GAME — the Riot Client must stay open."),
                T("Connecte le compte SOURCE dans le client Riot (la pilule en bas à droite "
                  "affiche son pseudo).",
                  "Log into the SOURCE account in the Riot Client (the bottom-right pill "
                  "shows its name)."),
                T("Clique « Sauvegarder en profil » sur ce compte → le profil gagne le nuage "
                  "vert (crosshair, sensi et keybinds inclus).",
                  "Click \"Save as profile\" on that account → the profile gets the green "
                  "cloud (crosshair, sensitivity and keybinds included)."),
                T("Dans le client Riot, déconnecte-toi puis connecte le compte CIBLE.",
                  "In the Riot Client, log out and log into the TARGET account."),
                T("Clique « Transfert express » et choisis le profil — une sauvegarde "
                  "automatique est créée avant.",
                  "Click \"Express transfer\" and pick the profile — an automatic backup is "
                  "created first."),
                T("Le jeu se lance : tous tes réglages sont là.",
                  "The game launches: all your settings are there.")), start=1):
            step_row(body, n, s)

        # --- Boutons -----------------------------------------------------------
        body = card("save", T("Les boutons", "The buttons"))
        for name_icon, color, name, desc in (
                ("bolt", C_RED,
                 T("Transfert express", "Express transfer"),
                 T("applique un profil au compte connecté puis lance le jeu — tout en un clic.",
                   "applies a profile to the logged in account then launches the game — all "
                   "in one click.")),
                ("play", C_RED,
                 T("Appliquer sur un compte", "Apply to an account"),
                 T("transfère le profil sur le compte de ton choix.",
                   "transfers the profile to the account you pick.")),
                ("eye", C_TEXT,
                 T("Détails", "Details"),
                 T("montre le contenu : sensibilité, crosshairs, touches modifiées…",
                   "shows the content: sensitivity, crosshairs, custom keybinds…")),
                ("export", C_TEXT,
                 T("Exporter", "Export"),
                 T("crée un fichier .vcmprofile à garder ou partager avec un ami.",
                   "creates a .vcmprofile file to keep or share with a friend.")),
                ("edit", C_TEXT,
                 T("Renommer", "Rename"),
                 T("change le nom du profil ou du compte.",
                   "changes the profile or account name.")),
                ("delete", C_TEXT,
                 T("Supprimer", "Delete"),
                 T("supprime définitivement le profil.",
                   "permanently deletes the profile.")),
                ("import", C_TEXT,
                 T("Importer", "Import"),
                 T("charge un .vcmprofile — double-cliquer sur le fichier marche aussi.",
                   "loads a .vcmprofile — double-clicking the file also works.")),
                ("compare", C_TEXT,
                 T("Comparer", "Compare"),
                 T("met deux profils côte à côte, différences en orange.",
                   "puts two profiles side by side, differences in orange.")),
                ("restore", C_TEXT,
                 T("Restaurer", "Restore"),
                 T("revient à une sauvegarde précédente d'un compte.",
                   "rolls an account back to a previous backup.")),
                ("cloud", C_GREEN,
                 T("Nuage vert", "Green cloud"),
                 T("le profil est complet : paramètres cloud inclus. Sans lui : vidéo "
                   "uniquement.",
                   "the profile is complete: cloud settings included. Without it: video "
                   "only."))):
            icon_row(body, name_icon, color, name, desc)

        # --- Sauvegardes -------------------------------------------------------
        body = card("restore", T("Sauvegardes automatiques", "Automatic backups"))
        text(body, T("Avant chaque application de profil, les réglages actuels du compte "
                     "cible sont sauvegardés (fichiers + cloud). Un instantané « auto » du "
                     "compte connecté est aussi pris à chaque session.",
                     "Before every profile application, the target account's current settings "
                     "are backed up (files + cloud). An \"auto\" snapshot of the logged in "
                     "account is also taken each session."))
        text(body, T("« Restaurer » permet de revenir en arrière — les 20 dernières "
                     "sauvegardes de chaque compte sont conservées.",
                     "\"Restore\" lets you roll back — the last 20 backups of each account "
                     "are kept."))
        text(body, T("Emplacement : %LOCALAPPDATA%\\ValorantConfigManager\\",
                     "Location: %LOCALAPPDATA%\\ValorantConfigManager\\"), dim=True)

        # --- Barre système -----------------------------------------------------
        body = card("close", T("Icône de la barre système", "System tray icon"))
        text(body, T("Fermer la fenêtre ne quitte pas le logiciel : il se réduit à côté de "
                     "l'horloge et continue de surveiller les connexions. Double-clic sur "
                     "l'icône = rouvrir, clic droit → Quitter = fermer complètement.",
                     "Closing the window does not quit the app: it minimizes next to the "
                     "clock and keeps watching for logins. Double-click the icon to reopen, "
                     "right-click → Quit to exit completely."))

        # --- FAQ ----------------------------------------------------------------
        body = card("help", T("Questions fréquentes", "FAQ"))
        qa(body,
           T("« Le jeu a remis mes anciens réglages ! »",
             "\"The game restored my old settings!\""),
           T("Le profil appliqué n'avait pas le nuage vert, ou le client Riot était connecté "
             "à un autre compte. Refais le transfert en suivant les 6 étapes.",
             "The applied profile had no green cloud, or the Riot Client was logged into a "
             "different account. Redo the transfer following the 6 steps."))
        qa(body,
           T("« Le client Riot doit vraiment être ouvert ? »",
             "\"Does the Riot Client really need to be open?\""),
           T("Oui : c'est lui qui fournit la session sécurisée du compte. Sans lui, seuls "
             "les fichiers locaux (vidéo) sont copiés.",
             "Yes: it provides the account's secure session. Without it, only local (video) "
             "files are copied."))
        qa(body,
           T("« C'est risqué pour mon compte ? »",
             "\"Is this risky for my account?\""),
           T("Le logiciel utilise l'API officielle du client Riot — celle que le jeu utilise "
             "lui-même pour synchroniser tes réglages. Rien d'automatisé en jeu, rien d'autre "
             "que tes préférences.",
             "The tool uses the official Riot Client API — the same one the game itself uses "
             "to sync your settings. Nothing automated in-game, nothing but your preferences."))
        qa(body,
           T("« Un profil exporté contient quoi ? »",
             "\"What does an exported profile contain?\""),
           T("Uniquement tes réglages (crosshair, sensi, keybinds, vidéo). Jamais "
             "d'identifiants ni de jetons de session.",
             "Only your settings (crosshair, sensitivity, keybinds, video). Never credentials "
             "or session tokens."))

    def _build_settings(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        def card(icon_name: str, title: str):
            c = ctk.CTkFrame(scroll, fg_color=C_PANEL, corner_radius=14,
                             border_width=1, border_color=C_BORDER)
            c.pack(fill="x", padx=4, pady=(0, 12))
            ctk.CTkLabel(c, image=icon(icon_name, 17, C_RED), compound="left",
                         text="  " + title.upper(), font=(theme.FONT_TITLE, 15),
                         text_color=C_RED).pack(anchor="w", padx=18, pady=(12, 2))
            body = ctk.CTkFrame(c, fg_color="transparent")
            body.pack(fill="x", padx=18, pady=(2, 14))
            return body

        def toggle_row(parent_, key: str, default: bool, label: str, desc: str):
            row = ctk.CTkFrame(parent_, fg_color="transparent")
            row.pack(fill="x", pady=5)
            texts = ctk.CTkFrame(row, fg_color="transparent")
            texts.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(texts, text=label, font=(theme.FONT_UI, 13, "bold"),
                         text_color=C_TEXT, anchor="w").pack(anchor="w", fill="x")
            ctk.CTkLabel(texts, text=desc, font=(theme.FONT_UI, 11),
                         text_color=C_TEXT_DIM, anchor="w", justify="left",
                         wraplength=620).pack(anchor="w", fill="x")
            var = ctk.BooleanVar(value=self._setting(key, default))
            ctk.CTkSwitch(row, text="", variable=var, width=44,
                          progress_color=C_RED, button_color=C_TEXT,
                          command=lambda k=key, v=var: self._save_toggle(k, v)).pack(
                side="right", padx=(12, 0))

        # --- Langue ------------------------------------------------------------
        body = card("globe", T("Langue", "Language"))
        ctk.CTkLabel(body, text=T("Langue de l'interface :", "Interface language:"),
                     font=(theme.FONT_UI, 12), text_color=C_TEXT_DIM).pack(
            anchor="w", pady=(0, 6))
        lang_var = ctk.StringVar(value="Français" if i18n.LANG == "fr" else "English")
        ctk.CTkSegmentedButton(
            body, values=["Français", "English"], variable=lang_var,
            selected_color=C_RED, selected_hover_color=C_RED_HOVER,
            unselected_color=C_CARD, unselected_hover_color=C_CARD_HOVER,
            fg_color=C_BG, text_color=C_TEXT, font=(theme.FONT_UI, 12, "bold"),
            command=lambda v: self._set_lang("fr" if v == "Français" else "en",
                                             return_to_settings=True)).pack(anchor="w")

        # --- Comportement ------------------------------------------------------
        body = card("bolt", T("Comportement", "Behavior"))
        toggle_row(body, "close_to_tray", True,
                   T("Réduire dans la barre système à la fermeture",
                     "Minimize to system tray on close"),
                   T("Fermer la fenêtre garde l'appli active près de l'horloge pour "
                     "surveiller les connexions. Décoché : la croix quitte l'appli.",
                     "Closing the window keeps the app running near the clock to watch "
                     "logins. Unchecked: the close button quits the app."))
        toggle_row(body, "auto_snapshot", True,
                   T("Instantanés automatiques", "Automatic snapshots"),
                   T("Prend une sauvegarde silencieuse (fichiers + cloud) du compte "
                     "connecté une fois par session.",
                     "Takes a silent backup (files + cloud) of the logged in account "
                     "once per session."))
        toggle_row(body, "login_banner", True,
                   T("Alerte de changement de compte",
                     "Account-change alert"),
                   T("Affiche une bannière (et une notification) quand un autre compte "
                     "se connecte au client Riot.",
                     "Shows a banner (and a notification) when another account logs into "
                     "the Riot Client."))

        # --- Données -----------------------------------------------------------
        body = card("restore", T("Données", "Data"))
        ctk.CTkLabel(body, text=T("Profils et sauvegardes sont stockés dans :",
                                  "Profiles and backups are stored in:"),
                     font=(theme.FONT_UI, 12), text_color=C_TEXT_DIM).pack(
            anchor="w")
        ctk.CTkLabel(body, text=str(DATA_DIR), font=("Consolas", 11),
                     text_color=C_TEXT).pack(anchor="w", pady=(0, 8))
        ctk.CTkButton(body, text=T(" Ouvrir le dossier", " Open folder"),
                      image=icon("import", 14), compound="left",
                      width=190, height=30, corner_radius=8,
                      fg_color=C_CARD, hover_color=C_CARD_HOVER, text_color=C_TEXT,
                      border_width=1, border_color=C_BORDER,
                      font=(theme.FONT_UI, 12),
                      command=self._open_data_folder).pack(anchor="w")

        # --- À propos ----------------------------------------------------------
        body = card("help", T("À propos", "About"))
        ctk.CTkLabel(body, text=f"{APP_NAME}  v{APP_VERSION}",
                     font=(theme.FONT_UI, 13, "bold"), text_color=C_TEXT).pack(anchor="w")
        ctk.CTkLabel(body,
                     text=T("Transfert de configs Valorant entre comptes Riot.",
                            "Transfer Valorant configs between Riot accounts."),
                     font=(theme.FONT_UI, 12), text_color=C_TEXT_DIM).pack(
            anchor="w", pady=(0, 8))
        ctk.CTkButton(body, text=" GitHub", image=icon("globe", 14), compound="left",
                      width=150, height=30, corner_radius=8,
                      fg_color=C_CARD, hover_color=C_CARD_HOVER, text_color=C_TEXT,
                      border_width=1, border_color=C_BORDER,
                      font=(theme.FONT_UI, 12),
                      command=lambda: webbrowser.open(GITHUB_URL)).pack(anchor="w")

    def _save_toggle(self, key: str, var):
        self.settings[key] = bool(var.get())
        save_settings(self.settings)

    def _open_data_folder(self):
        try:
            ensure_dirs()
            os.startfile(str(DATA_DIR))  # noqa: S606 (Windows, chemin interne)
        except OSError as e:
            messagebox.showerror(APP_NAME, T(f"Impossible d'ouvrir le dossier :\n{e}",
                                             f"Could not open the folder:\n{e}"))

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0, height=40)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.status = ctk.CTkLabel(
            bar, text=T("Prêt.", "Ready."), font=(theme.FONT_UI, 11), text_color=C_TEXT_DIM)
        self.status.pack(side="left", padx=16)

        self.riot_pill = ctk.CTkFrame(bar, fg_color=C_BG, corner_radius=13,
                                      border_width=1, border_color=C_BORDER)
        self.riot_pill.pack(side="right", padx=(6, 16), pady=6)
        self.riot_status = ctk.CTkLabel(self.riot_pill,
                                        text=T("●  Client Riot : vérification…",
                                               "●  Riot Client: checking…"),
                                        font=(theme.FONT_UI, 11), text_color=C_TEXT_DIM)
        self.riot_status.pack(padx=12, pady=1)

        self.valo_pill = ctk.CTkFrame(bar, fg_color=C_BG, corner_radius=13,
                                      border_width=1, border_color=C_BORDER)
        self.valo_pill.pack(side="right", padx=6, pady=6)
        self.valo_status = ctk.CTkLabel(self.valo_pill,
                                        text=T("●  Jeu Valorant : vérification…",
                                               "●  Valorant game: checking…"),
                                        font=(theme.FONT_UI, 11), text_color=C_TEXT_DIM)
        self.valo_status.pack(padx=12, pady=1)

    def set_status(self, text: str, color: str = C_TEXT_DIM):
        self.status.configure(text=text, text_color=color)

    def _set_lang(self, lang: str, return_to_settings: bool = False):
        if lang == i18n.LANG:
            return
        i18n.set_lang(lang)
        self.settings["lang"] = i18n.LANG
        save_settings(self.settings)
        self._build_ui()
        self.refresh()
        self._update_status_ui(self._last_game_running, self.connected_riot_id,
                               self.connected_subject)
        if return_to_settings:
            # Rester sur l'onglet Paramètres après la reconstruction de l'UI.
            self.tabs.set(T("  Paramètres  ", "  Settings  "))
            self._on_tab_change()

    def _setting(self, key: str, default):
        return self.settings.get(key, default)

    # ------------------------------------------------------------ Rendu -----
    def refresh(self):
        self.accounts = list_accounts()
        self.profiles = list_profiles()
        self._render_accounts()
        self._render_profiles()

    def _render_accounts(self):
        for w in self.accounts_frame.winfo_children():
            w.destroy()

        if not VALO_CONFIG_DIR.is_dir():
            ctk.CTkLabel(
                self.accounts_frame,
                text=T("Dossier de configuration Valorant introuvable.\n"
                       "Lance Valorant au moins une fois sur ce PC.",
                       "Valorant configuration folder not found.\n"
                       "Launch Valorant at least once on this PC."),
                font=(theme.FONT_UI, 13), text_color=C_ORANGE, justify="left").pack(
                padx=14, pady=20, anchor="w")
            return

        if not self.accounts:
            ctk.CTkLabel(
                self.accounts_frame,
                text=T("Aucun compte détecté.\nConnecte-toi à Valorant puis clique sur Actualiser.",
                       "No account found.\nLog into Valorant then click Refresh."),
                font=(theme.FONT_UI, 13), text_color=C_TEXT_DIM, justify="left").pack(
                padx=14, pady=20, anchor="w")
            return

        for i, (folder, path, last) in enumerate(self.accounts):
            card = ctk.CTkFrame(self.accounts_frame, fg_color=C_CARD, corner_radius=12,
                                border_width=1, border_color=C_BORDER)
            card.pack(fill="x", padx=6, pady=5)

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=14, pady=10)

            name = self.account_names.get(folder, "")
            title_row = ctk.CTkFrame(info, fg_color="transparent")
            title_row.pack(anchor="w", fill="x")
            display = name if name else T(f"Compte sans nom ({short_id(folder)}…)",
                                          f"Unnamed account ({short_id(folder)}…)")
            ctk.CTkLabel(title_row, text=display,
                         font=(theme.FONT_UI, 14, "bold"),
                         text_color=C_TEXT if name else C_ORANGE).pack(side="left")
            if self.connected_subject and folder.lower().startswith(self.connected_subject.lower()):
                ctk.CTkLabel(title_row, text=T("  ● CONNECTÉ", "  ● LOGGED IN"),
                             font=(theme.FONT_UI, 9, "bold"), text_color=C_GREEN).pack(side="left")
            elif i == 0:
                ctk.CTkLabel(title_row, text=T("  DERNIER UTILISÉ", "  LAST USED"),
                             font=(theme.FONT_UI, 9, "bold"), text_color=C_TEXT_DIM).pack(side="left")

            ctk.CTkLabel(info, text=f"ID : {folder}",
                         font=("Consolas", 10), text_color=C_TEXT_DIM).pack(anchor="w")
            ctk.CTkLabel(info, text=T(f"Dernière activité : {fmt_date(last)}",
                                      f"Last activity: {fmt_date(last)}"),
                         font=(theme.FONT_UI, 11), text_color=C_TEXT_DIM).pack(anchor="w")

            btns = ctk.CTkFrame(card, fg_color="transparent")
            btns.pack(side="right", padx=12, pady=10)
            ctk.CTkButton(btns, text=T(" Sauvegarder en profil", " Save as profile"),
                          image=icon("save", 14, "#ffffff"), compound="left",
                          width=175, height=30, corner_radius=8,
                          fg_color=C_RED, hover_color=C_RED_HOVER,
                          font=(theme.FONT_UI, 12, "bold"),
                          command=lambda f=folder, p=path: self.save_profile(f, p)).pack(pady=(0, 5))
            ctk.CTkButton(btns, text=T(" Renommer", " Rename"),
                          image=icon("edit", 13), compound="left",
                          width=175, height=26, corner_radius=8,
                          fg_color=C_PANEL, hover_color=C_CARD_HOVER, text_color=C_TEXT,
                          border_width=1, border_color=C_BORDER,
                          font=(theme.FONT_UI, 11),
                          command=lambda f=folder: self.rename_account(f)).pack()

    def _render_profiles(self):
        for w in self.profiles_frame.winfo_children():
            w.destroy()

        if not self.profiles:
            ctk.CTkLabel(
                self.profiles_frame,
                text=T("Aucun profil pour l'instant.\n\n"
                       "Clique sur « Sauvegarder en profil » sur un compte\n"
                       "pour enregistrer ses paramètres ici.",
                       "No profiles yet.\n\n"
                       "Click \"Save as profile\" on an account\n"
                       "to store its settings here."),
                font=(theme.FONT_UI, 13), text_color=C_TEXT_DIM, justify="left").pack(
                padx=14, pady=20, anchor="w")
            return

        for prof in self.profiles:
            card = ctk.CTkFrame(self.profiles_frame, fg_color=C_CARD, corner_radius=12,
                                border_width=1, border_color=C_BORDER)
            card.pack(fill="x", padx=6, pady=5)

            name_row = ctk.CTkFrame(card, fg_color="transparent")
            name_row.pack(anchor="w", fill="x", padx=14, pady=(10, 0))
            ctk.CTkLabel(name_row, text=prof["name"], font=(theme.FONT_UI, 14, "bold"),
                         text_color=C_TEXT, wraplength=380, justify="left").pack(side="left")
            if prof.get("has_cloud"):
                ctk.CTkLabel(name_row, text="", image=icon("cloud", 15, C_GREEN)).pack(
                    side="left", padx=(8, 0))
            else:
                ctk.CTkLabel(name_row, text=T("  (local uniquement)", "  (local only)"),
                             font=(theme.FONT_UI, 10),
                             text_color=C_ORANGE).pack(side="left")
            created = prof.get("created", "?").replace("T", " ")
            src = prof.get("riot_id") or prof.get("source_name") or short_id(prof.get("source_folder", "?")) + "…"
            ctk.CTkLabel(card, text=T(f"Depuis : {src}   •   Créé le {created}",
                                      f"From: {src}   •   Created {created}"),
                         font=(theme.FONT_UI, 11), text_color=C_TEXT_DIM,
                         wraplength=440, justify="left").pack(anchor="w", padx=14)

            btns = ctk.CTkFrame(card, fg_color="transparent")
            btns.pack(fill="x", padx=12, pady=(8, 10))
            ctk.CTkButton(btns, text=T(" Appliquer sur un compte", " Apply to an account"),
                          image=icon("play", 14, "#ffffff"), compound="left",
                          height=30, width=60, corner_radius=8,
                          fg_color=C_RED, hover_color=C_RED_HOVER,
                          font=(theme.FONT_UI, 12, "bold"),
                          command=lambda p=prof: self.apply_profile(p)).pack(
                side="left", fill="x", expand=True, padx=(0, 6))
            for glyph, cmd, hover in (
                    ("eye", lambda p=prof: self.profile_details(p), C_CARD_HOVER),
                    ("export", lambda p=prof: self.export_profile(p), C_CARD_HOVER),
                    ("edit", lambda p=prof: self.rename_profile(p), C_CARD_HOVER),
                    ("delete", lambda p=prof: self.delete_profile(p), "#5a2731")):
                ctk.CTkButton(btns, text="", image=icon(glyph, 14),
                              width=34, height=30, corner_radius=8,
                              fg_color=C_PANEL, hover_color=hover, text_color=C_TEXT,
                              border_width=1, border_color=C_BORDER,
                              command=cmd).pack(side="left", padx=(0, 5))

    # ------------------------------------------------------------ Actions ---
    def _account_label(self, folder: str) -> str:
        return self.account_names.get(folder) or T(f"Compte {short_id(folder)}…",
                                                   f"Account {short_id(folder)}…")

    def rename_account(self, folder: str):
        name = TextDialog(self, T("Renommer le compte", "Rename account"),
                          T("Donne un nom à ce compte (ex : Main, Smurf...) :",
                            "Give this account a name (e.g. Main, Smurf...):"),
                          initial=self.account_names.get(folder, "")).get()
        if name:
            self.account_names[folder] = name
            save_account_names(self.account_names)
            self.refresh()
            self.set_status(T(f"Compte renommé en « {name} ».",
                              f"Account renamed to \"{name}\"."), C_GREEN)

    def _fetch_cloud_for_save(self, folder: str):
        """Récupère les paramètres cloud si le compte connecté correspond au dossier.

        Retourne le dict cloud, None (profil local uniquement) ou 'ABORT'."""
        try:
            tokens = riot_cloud.get_tokens()
        except RiotClientError:
            choice = messagebox.askyesnocancel(
                APP_NAME,
                T("Le client Riot n'est pas ouvert (ou personne n'est connecté).\n\n"
                  "Sans lui, le profil ne contiendra QUE les paramètres locaux : le "
                  "crosshair, la sensibilité et les keybinds n'y seront PAS inclus.\n\n"
                  "• Oui : ouvrir le client Riot maintenant (connecte-toi au compte, "
                  "puis refais « Sauvegarder en profil »)\n"
                  "• Non : créer quand même un profil local uniquement\n"
                  "• Annuler : ne rien faire",
                  "The Riot Client is not open (or nobody is logged in).\n\n"
                  "Without it, the profile will ONLY contain local settings: crosshair, "
                  "sensitivity and keybinds will NOT be included.\n\n"
                  "• Yes: open the Riot Client now (log into the account, then save "
                  "the profile again)\n"
                  "• No: create a local-only profile anyway\n"
                  "• Cancel: do nothing"))
            if choice is None:
                return "ABORT"
            if choice:
                riot_cloud.launch_riot_client()
                messagebox.showinfo(
                    APP_NAME,
                    T("Le client Riot s'ouvre.\n\nConnecte-toi au compte, attends que "
                      "l'en-tête affiche « Client Riot : TonPseudo#TAG » (quelques "
                      "secondes), puis refais « Sauvegarder en profil ».",
                      "The Riot Client is opening.\n\nLog into the account, wait until "
                      "the header shows \"Riot Client: YourName#TAG\" (a few seconds), "
                      "then click \"Save as profile\" again."))
                return "ABORT"
            return None

        subject = tokens.get("subject", "")
        riot_id = riot_cloud.get_riot_id()
        matches = folder.lower().startswith(subject.lower()) if subject else False

        if not matches:
            ok = messagebox.askyesno(
                APP_NAME,
                T(f"Le compte actuellement connecté au client Riot est :\n"
                  f"« {riot_id or 'inconnu'} »\n\n"
                  f"Impossible de confirmer que c'est bien le compte de ce dossier.\n"
                  f"Est-ce le bon compte ? (Si oui, ses paramètres cloud — crosshair, "
                  f"sensi, keybinds — seront inclus dans le profil.)",
                  f"The account currently logged into the Riot Client is:\n"
                  f"\"{riot_id or 'unknown'}\"\n\n"
                  f"Cannot confirm it matches this folder.\n"
                  f"Is it the right account? (If yes, its cloud settings — crosshair, "
                  f"sensitivity, keybinds — will be included in the profile.)"))
            if not ok:
                messagebox.showinfo(
                    APP_NAME,
                    T("Profil créé avec les paramètres locaux uniquement.\n"
                      "Connecte le bon compte dans le client Riot puis refais la "
                      "sauvegarde pour un profil complet.",
                      "Profile created with local settings only.\n"
                      "Log the right account into the Riot Client and save again "
                      "for a complete profile."))
                return None
        try:
            settings = riot_cloud.get_cloud_settings(tokens)
        except RiotClientError as e:
            messagebox.showwarning(
                APP_NAME,
                T(f"Paramètres cloud non récupérés : {e}\nLe profil sera local uniquement.",
                  f"Cloud settings not retrieved: {e}\nThe profile will be local only."))
            return None
        return {"riot_id": riot_id, "subject": subject, "settings": settings}

    def _resolve_profile_name(self, name: str, exclude_id: str | None = None):
        """Gère les noms de profils déjà pris.

        Retourne (nom_final, [profils_à_remplacer]) ou None si annulé."""
        while True:
            existing = [p for p in self.profiles
                        if p["name"] == name and p["id"] != exclude_id]
            if not existing:
                return name, []
            choice = messagebox.askyesnocancel(
                APP_NAME,
                T(f"Un profil nommé « {name} » existe déjà.\n\n"
                  "• Oui : le REMPLACER (l'ancien est supprimé)\n"
                  "• Non : choisir un autre nom\n"
                  "• Annuler : abandonner",
                  f"A profile named \"{name}\" already exists.\n\n"
                  "• Yes: REPLACE it (the old one is deleted)\n"
                  "• No: pick another name\n"
                  "• Cancel: abort"))
            if choice is None:
                return None
            if choice:
                return name, existing
            new_name = TextDialog(self, T("Nom déjà pris", "Name already taken"),
                                  T("Choisis un autre nom :", "Pick another name:"),
                                  initial=name).get()
            if not new_name:
                return None
            name = new_name

    def save_profile(self, folder: str, path: Path):
        default = self._account_label(folder)
        generic = default.startswith(T("Compte ", "Account "))
        name = TextDialog(self, T("Nouveau profil", "New profile"),
                          T("Nom du profil (ex : Config main, Setup tournoi...) :",
                            "Profile name (e.g. Main config, Tournament setup...):"),
                          initial="" if generic else T(f"Config {default}", f"{default} config")).get()
        if not name:
            return
        resolved = self._resolve_profile_name(name)
        if resolved is None:
            return
        name, to_replace = resolved
        cloud = self._fetch_cloud_for_save(folder)
        if cloud == "ABORT":
            return
        try:
            create_profile(path, name, self.account_names.get(folder, ""), cloud=cloud)
        except OSError as e:
            messagebox.showerror(APP_NAME, T(f"Impossible de créer le profil :\n{e}",
                                             f"Could not create the profile:\n{e}"))
            return
        for old in to_replace:
            shutil.rmtree(old["path"], ignore_errors=True)
        self.refresh()
        extra = T(" (avec paramètres cloud)", " (with cloud settings)") if cloud \
            else T(" (local uniquement)", " (local only)")
        self.set_status(T(f"Profil « {name} » enregistré{extra} ✔",
                          f"Profile \"{name}\" saved{extra} ✔"), C_GREEN)

    # ------------------------------------------------- Application de profil
    def _do_apply(self, prof: dict, target_folder: str | None, tokens: dict | None,
                  cloud: dict | None) -> bool:
        """Sauvegarde puis applique un profil. Retourne True si OK."""
        try:
            # Les paramètres cloud actuels du compte connecté sont toujours
            # sauvegardés avant écrasement, même si aucun dossier local ne
            # correspond à ce compte sur ce PC.
            backup_cloud = None
            if cloud and tokens:
                try:
                    backup_cloud = {
                        "riot_id": self.connected_riot_id,
                        "subject": tokens.get("subject", ""),
                        "settings": riot_cloud.get_cloud_settings(tokens),
                    }
                except RiotClientError:
                    pass
            if target_folder:
                target_path = VALO_CONFIG_DIR / target_folder
                backup_account(target_path, cloud=backup_cloud)
                apply_files(prof["path"] / "files", target_path)
            elif backup_cloud:
                backup_cloud_only(backup_cloud["subject"], backup_cloud)
            if cloud and tokens:
                riot_cloud.put_cloud_settings(tokens, cloud["settings"])
        except (OSError, RiotClientError) as e:
            messagebox.showerror(APP_NAME,
                                 T(f"Erreur pendant l'application du profil :\n{e}",
                                   f"Error while applying the profile:\n{e}"))
            return False
        return True

    def apply_profile(self, prof: dict):
        if not self.accounts:
            messagebox.showwarning(APP_NAME, T("Aucun compte détecté sur ce PC.",
                                               "No account found on this PC."))
            return

        if is_valorant_running():
            messagebox.showwarning(
                APP_NAME,
                T("Valorant est en cours d'exécution !\n\n"
                  "Ferme complètement le JEU avant d'appliquer un profil (le client "
                  "Riot peut rester ouvert, c'est même nécessaire pour le cloud).",
                  "Valorant is running!\n\n"
                  "Fully close the GAME before applying a profile (the Riot Client "
                  "can stay open — it's even required for the cloud)."))
            return

        cloud = read_profile_cloud(prof["path"]) if prof.get("has_cloud") else None

        # --- Partie cloud : nécessite le client Riot connecté au compte cible ---
        tokens = None
        connected_riot_id = ""
        if cloud:
            try:
                tokens = riot_cloud.get_tokens()
                connected_riot_id = riot_cloud.get_riot_id()
            except RiotClientError:
                choice = messagebox.askyesnocancel(
                    APP_NAME,
                    T("Ce profil contient des paramètres cloud (crosshair, sensi, "
                      "keybinds), mais le client Riot n'est pas connecté.\n\n"
                      "SANS le cloud, ces réglages ne seront pas transférés (Riot "
                      "les resynchronise à la connexion).\n\n"
                      "• Oui : ouvrir le client Riot maintenant (connecte-toi au "
                      "compte CIBLE, sans lancer le jeu, puis réessaie)\n"
                      "• Non : appliquer quand même uniquement les fichiers locaux\n"
                      "• Annuler : ne rien faire",
                      "This profile contains cloud settings (crosshair, sensitivity, "
                      "keybinds), but the Riot Client is not logged in.\n\n"
                      "WITHOUT the cloud, those settings won't transfer (Riot re-syncs "
                      "them at login).\n\n"
                      "• Yes: open the Riot Client now (log into the TARGET account, "
                      "without launching the game, then retry)\n"
                      "• No: apply local files only anyway\n"
                      "• Cancel: do nothing"))
                if choice is None:
                    return
                if choice:
                    riot_cloud.launch_riot_client()
                    messagebox.showinfo(
                        APP_NAME,
                        T("Le client Riot s'ouvre.\n\nConnecte-toi au compte CIBLE, "
                          "attends que l'en-tête affiche « Client Riot : Pseudo#TAG », "
                          "puis re-clique sur « Appliquer sur un compte ».",
                          "The Riot Client is opening.\n\nLog into the TARGET account, "
                          "wait until the header shows \"Riot Client: Name#TAG\", "
                          "then click \"Apply to an account\" again."))
                    return
                cloud = None

        # --- Choix du compte cible (fichiers locaux) ---
        preselect = None
        if tokens:
            preselect = folder_for_puuid(tokens.get("subject", ""))
        choices = [(folder, f"{self._account_label(folder)}   —   {short_id(folder)}…")
                   for folder, _, _ in self.accounts]
        target = ChoiceDialog(self, T("Appliquer le profil", "Apply profile"),
                              T(f"Appliquer « {prof['name']} » sur quel compte ?",
                                f"Apply \"{prof['name']}\" to which account?"),
                              choices, confirm_text=T("Appliquer", "Apply"),
                              preselect=preselect).get()
        if not target:
            return

        label = self._account_label(target)

        # Cohérence compte connecté / compte cible
        if cloud and tokens:
            subject = tokens.get("subject", "")
            if subject and not target.lower().startswith(subject.lower()):
                connected_folder = folder_for_puuid(subject)
                who = self._account_label(connected_folder) if connected_folder \
                    else (connected_riot_id or T("un autre compte", "another account"))
                if not messagebox.askyesno(
                        APP_NAME,
                        T(f"⚠ Attention : le compte connecté au client Riot semble être "
                          f"« {who} », pas « {label} ».\n\n"
                          f"Les paramètres cloud seront appliqués au compte CONNECTÉ "
                          f"({connected_riot_id or '?'}), pas au dossier choisi.\n\n"
                          f"→ Recommandé : Annuler et se connecter au bon compte dans le "
                          f"client Riot.\n\nContinuer quand même ?",
                          f"⚠ Warning: the account logged into the Riot Client seems to be "
                          f"\"{who}\", not \"{label}\".\n\n"
                          f"Cloud settings will be applied to the LOGGED IN account "
                          f"({connected_riot_id or '?'}), not the selected folder.\n\n"
                          f"→ Recommended: cancel and log into the right account in the "
                          f"Riot Client.\n\nContinue anyway?")):
                    return

        msg = T(f"Les paramètres actuels de « {label} » vont être remplacés par le "
                f"profil « {prof['name']} ».",
                f"The current settings of \"{label}\" will be replaced by the "
                f"profile \"{prof['name']}\".")
        if cloud:
            msg += T(f"\n\nParamètres cloud inclus — appliqués au compte connecté : "
                     f"{connected_riot_id or '?'}.",
                     f"\n\nCloud settings included — applied to the logged in account: "
                     f"{connected_riot_id or '?'}.")
        msg += T("\n\nUne sauvegarde automatique sera créée avant. Continuer ?",
                 "\n\nAn automatic backup will be created first. Continue?")
        if not messagebox.askyesno(APP_NAME, msg):
            return

        if not self._do_apply(prof, target, tokens, cloud):
            return

        self.refresh()
        self.set_status(T(f"Profil « {prof['name']} » appliqué sur « {label} » ✔",
                          f"Profile \"{prof['name']}\" applied to \"{label}\" ✔"), C_GREEN)
        if cloud:
            messagebox.showinfo(
                APP_NAME,
                T(f"Profil appliqué sur « {label} » ✔\n\n"
                  "Fichiers locaux + paramètres cloud (crosshair, sensi, keybinds) "
                  "transférés.\n\nLance Valorant : tout sera chargé automatiquement.",
                  f"Profile applied to \"{label}\" ✔\n\n"
                  "Local files + cloud settings (crosshair, sensitivity, keybinds) "
                  "transferred.\n\nLaunch Valorant: everything will load automatically."))
        else:
            messagebox.showinfo(
                APP_NAME,
                T(f"Fichiers locaux appliqués sur « {label} » ✔\n\n"
                  "⚠ Ce profil ne contenait pas les paramètres cloud : le crosshair, "
                  "la sensi et les keybinds risquent d'être resynchronisés par Riot à "
                  "la connexion. Pour un transfert complet, recrée le profil avec le "
                  "client Riot connecté au compte source.",
                  f"Local files applied to \"{label}\" ✔\n\n"
                  "⚠ This profile had no cloud settings: crosshair, sensitivity and "
                  "keybinds may be re-synced by Riot at login. For a full transfer, "
                  "recreate the profile with the Riot Client logged into the source "
                  "account."))

    def express_transfer(self):
        """Applique un profil au compte connecté + lance Valorant, en un clic."""
        if not self.profiles:
            messagebox.showinfo(APP_NAME,
                                T("Aucun profil enregistré. Crée d'abord un profil avec "
                                  "« Sauvegarder en profil ».",
                                  "No saved profiles. First create one with "
                                  "\"Save as profile\"."))
            return
        if is_valorant_running():
            messagebox.showwarning(APP_NAME,
                                   T("Ferme d'abord le jeu Valorant.",
                                     "Close the Valorant game first."))
            return
        try:
            tokens = riot_cloud.get_tokens()
            riot_id = riot_cloud.get_riot_id()
        except RiotClientError:
            if messagebox.askyesno(
                    APP_NAME,
                    T("Le transfert express nécessite le client Riot connecté au compte "
                      "cible.\n\nOuvrir le client Riot maintenant ?",
                      "Express transfer needs the Riot Client logged into the target "
                      "account.\n\nOpen the Riot Client now?")):
                riot_cloud.launch_riot_client()
                messagebox.showinfo(
                    APP_NAME,
                    T("Connecte-toi au compte cible, puis re-clique sur "
                      "« Transfert express ».",
                      "Log into the target account, then click "
                      "\"Express transfer\" again."))
            return

        subject = tokens.get("subject", "")
        target_folder = folder_for_puuid(subject)
        choices = [(p["id"], p["name"] + ("  (cloud)" if p.get("has_cloud") else
                                          T("  (local uniquement)", "  (local only)")))
                   for p in self.profiles]
        chosen = ChoiceDialog(
            self, T("Transfert express", "Express transfer"),
            T(f"Compte connecté : {riot_id or '?'}\n"
              f"Quel profil appliquer sur ce compte ?",
              f"Logged in account: {riot_id or '?'}\n"
              f"Which profile should be applied to this account?"),
            choices, confirm_text=T("Appliquer et jouer", "Apply and play")).get()
        if not chosen:
            return
        prof = next(p for p in self.profiles if p["id"] == chosen)
        cloud = read_profile_cloud(prof["path"]) if prof.get("has_cloud") else None
        if target_folder is None:
            if not cloud:
                messagebox.showwarning(
                    APP_NAME,
                    T("Ce compte n'a pas de dossier de configuration sur ce PC et le "
                      "profil choisi ne contient pas de paramètres cloud : il n'y a "
                      "rien à transférer.",
                      "This account has no configuration folder on this PC and the "
                      "chosen profile has no cloud settings: there is nothing to "
                      "transfer."))
                return
            if not messagebox.askyesno(
                    APP_NAME,
                    T("Ce compte n'a pas encore de dossier de configuration sur ce PC "
                      "(le jeu n'y a jamais été lancé avec ce compte).\n\n"
                      "Seuls les paramètres cloud (crosshair, sensi, keybinds) seront "
                      "transférés — pas les réglages vidéo locaux.\n\nContinuer ?",
                      "This account has no configuration folder on this PC yet "
                      "(the game was never launched with it here).\n\n"
                      "Only cloud settings (crosshair, sensitivity, keybinds) will be "
                      "transferred — not the local video settings.\n\nContinue?")):
                return
        if not cloud:
            if not messagebox.askyesno(
                    APP_NAME,
                    T("Ce profil est local uniquement (sans cloud) : le crosshair, la "
                      "sensi et les keybinds ne seront pas transférés.\n\nContinuer ?",
                      "This profile is local only (no cloud): crosshair, sensitivity and "
                      "keybinds won't transfer.\n\nContinue?")):
                return

        if not self._do_apply(prof, target_folder, tokens, cloud):
            return
        self.refresh()
        self.set_status(T(f"Profil « {prof['name']} » appliqué sur {riot_id} — lancement du jeu... ✔",
                          f"Profile \"{prof['name']}\" applied to {riot_id} — launching game... ✔"),
                        C_GREEN)
        riot_cloud.launch_riot_client(product="valorant")

    def compare_profiles(self):
        if len(self.profiles) < 2:
            messagebox.showinfo(APP_NAME,
                                T("Il faut au moins deux profils pour comparer.",
                                  "You need at least two profiles to compare."))
            return
        choices = [(p["id"], p["name"] + ("  (cloud)" if p.get("has_cloud") else ""))
                   for p in self.profiles]
        a_id = ChoiceDialog(self, T("Comparer", "Compare"),
                            T("Premier profil :", "First profile:"),
                            choices, confirm_text=T("Suivant", "Next")).get()
        if not a_id:
            return
        rest = [c for c in choices if c[0] != a_id]
        b_id = ChoiceDialog(self, T("Comparer", "Compare"),
                            T("Deuxième profil :", "Second profile:"),
                            rest, confirm_text=T("Comparer", "Compare")).get()
        if not b_id:
            return
        a = next(p for p in self.profiles if p["id"] == a_id)
        b = next(p for p in self.profiles if p["id"] == b_id)
        sa, sb = profile_summary(a), profile_summary(b)

        def fmt(summary, key):
            v = summary.get(key)
            if v is None:
                return "—"
            if key == "cloud":
                return T("oui", "yes") if v else T("non", "no")
            if key == "crosshairs":
                return f"{len(v)} : " + ", ".join(v[:4]) + ("…" if len(v) > 4 else "")
            if key == "keybinds":
                return str(len(v))
            return str(v)

        # --- Construction de toutes les lignes : (libellé, valA, valB, diffère) ---
        all_rows = []
        for label, key in [
                (T("Paramètres cloud", "Cloud settings"), "cloud"),
                (T("Sensibilité souris", "Mouse sensitivity"), "sens"),
                (T("Multiplicateur visée (ADS)", "ADS multiplier"), "ads"),
                (T("Crosshairs", "Crosshairs"), "crosshairs"),
                (T("Touches personnalisées", "Custom keybinds"), "keybinds"),
                (T("Résolution", "Resolution"), "resolution"),
                (T("Limite FPS", "FPS limit"), "fps_limit"),
                (T("Mode d'affichage", "Display mode"), "screen_mode")]:
            va, vb = fmt(sa, key), fmt(sb, key)
            if va == "—" and vb == "—":
                continue
            all_rows.append((label, va, vb, sa.get(key) != sb.get(key)))

        # Touches : détail des actions dont l'assignation change
        ka, kb = keybind_map(a), keybind_map(b)
        if ka is not None and kb is not None:
            for action in sorted(set(ka) | set(kb)):
                va, vb = ka.get(action, "—"), kb.get(action, "—")
                all_rows.append((T(f"Touche · {action}", f"Key · {action}"),
                                 va, vb, va != vb))

        # Tous les autres réglages cloud (audio, HUD, minimap, souris...)
        ma, mb = cloud_settings_map(a), cloud_settings_map(b)
        if ma is not None and mb is not None:
            for enum in sorted(set(ma) | set(mb)):
                va = ma.get(enum, "—")
                vb = mb.get(enum, "—")
                sva = str(va) if not isinstance(va, bool) else (T("oui", "yes") if va else T("non", "no"))
                svb = str(vb) if not isinstance(vb, bool) else (T("oui", "yes") if vb else T("non", "no"))
                all_rows.append((enum, sva, svb, va != vb))

        n_diff = sum(1 for r in all_rows if r[3])

        dlg = ctk.CTkToplevel(self)
        dlg.title(T("Comparaison de profils", "Profile comparison"))
        dlg.configure(fg_color=C_PANEL)
        dlg.transient(self)
        dlg.grab_set()
        dlg.geometry("760x560")
        dlg.minsize(680, 420)

        header = ctk.CTkFrame(dlg, fg_color="transparent")
        header.pack(fill="x", padx=26, pady=(16, 4))
        ctk.CTkLabel(header, text="", width=230).pack(side="left")
        for prof in (a, b):
            ctk.CTkLabel(header, text=prof["name"], font=(theme.FONT_UI, 13, "bold"),
                         text_color=C_RED, width=210, anchor="w",
                         wraplength=200).pack(side="left", padx=4)

        summary_lbl = ctk.CTkLabel(
            dlg, font=(theme.FONT_UI, 11), text_color=C_TEXT_DIM, anchor="w")
        summary_lbl.pack(anchor="w", padx=26)

        grid = ctk.CTkScrollableFrame(dlg, fg_color=C_BG, corner_radius=10)
        grid.pack(padx=22, pady=6, fill="both", expand=True)

        show_all = ctk.BooleanVar(value=False)

        def render_rows():
            for w in grid.winfo_children():
                w.destroy()
            rows = all_rows if show_all.get() else [r for r in all_rows if r[3]]
            if not rows:
                ctk.CTkLabel(grid,
                             text=T("Aucune différence entre ces deux profils !",
                                    "No differences between these two profiles!"),
                             font=(theme.FONT_UI, 13), text_color=C_GREEN).pack(pady=24)
            for label, va, vb, differs in rows:
                row = ctk.CTkFrame(grid, fg_color="transparent")
                row.pack(fill="x", padx=10, pady=2)
                ctk.CTkLabel(row, text=label, font=(theme.FONT_UI, 12, "bold"),
                             text_color=C_TEXT_DIM, width=230, anchor="nw",
                             justify="left", wraplength=220).pack(side="left")
                color = C_ORANGE if differs else C_TEXT
                for v in (va, vb):
                    ctk.CTkLabel(row, text=v, font=(theme.FONT_UI, 12), text_color=color,
                                 width=210, anchor="nw", justify="left",
                                 wraplength=200).pack(side="left", padx=4)
            shown = len(rows)
            summary_lbl.configure(text=T(
                f"{n_diff} différence(s) sur {len(all_rows)} réglages comparés — "
                f"{shown} ligne(s) affichée(s). En orange : les différences.",
                f"{n_diff} difference(s) out of {len(all_rows)} compared settings — "
                f"{shown} row(s) shown. Orange = differences."))

        bottom = ctk.CTkFrame(dlg, fg_color="transparent")
        bottom.pack(fill="x", padx=22, pady=(4, 16))
        ctk.CTkCheckBox(bottom,
                        text=T("Afficher aussi les réglages identiques",
                               "Also show identical settings"),
                        variable=show_all, command=render_rows,
                        font=(theme.FONT_UI, 12), text_color=C_TEXT,
                        fg_color=C_RED, hover_color=C_RED_HOVER,
                        checkbox_width=20, checkbox_height=20).pack(side="left")
        ctk.CTkButton(bottom, text=T("Fermer", "Close"), width=120, fg_color=C_RED,
                      hover_color=C_RED_HOVER, font=(theme.FONT_UI, 12, "bold"),
                      command=dlg.destroy).pack(side="right")

        render_rows()
        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        try:
            dlg.after(220, lambda: dlg.iconbitmap(str(resource_path("icon.ico"))))
        except Exception:
            pass

    def rename_profile(self, prof: dict):
        name = TextDialog(self, T("Renommer le profil", "Rename profile"),
                          T("Nouveau nom du profil :", "New profile name:"),
                          initial=prof["name"]).get()
        if not name or name == prof["name"]:
            return
        resolved = self._resolve_profile_name(name, exclude_id=prof["id"])
        if resolved is None:
            return
        name, to_replace = resolved
        meta_file = prof["path"] / "meta.json"
        prof_meta = {k: v for k, v in prof.items() if k not in ("id", "path", "has_cloud")}
        prof_meta["name"] = name
        meta_file.write_text(json.dumps(prof_meta, indent=2, ensure_ascii=False), encoding="utf-8")
        for old in to_replace:
            shutil.rmtree(old["path"], ignore_errors=True)
        self.refresh()

    def profile_details(self, prof: dict):
        lines = []
        src = prof.get("riot_id") or prof.get("source_name") or "?"
        lines.append((T("Compte source", "Source account"), src))
        lines.append((T("Créé le", "Created"), prof.get("created", "?").replace("T", " à " if i18n.LANG == "fr" else " at ")))
        s = profile_summary(prof)
        if not s.get("cloud"):
            lines.append((T("Contenu", "Content"),
                          T("Fichiers locaux uniquement (réglages vidéo).\n"
                            "Pas de paramètres cloud : crosshair, sensi et\n"
                            "keybinds ne sont pas dans ce profil.",
                            "Local files only (video settings).\n"
                            "No cloud settings: crosshair, sensitivity and\n"
                            "keybinds are not in this profile.")))
        else:
            if "sens" in s:
                lines.append((T("Sensibilité souris", "Mouse sensitivity"), str(s["sens"])))
            if "ads" in s:
                lines.append((T("Multiplicateur visée (ADS)", "ADS multiplier"), str(s["ads"])))
            if s.get("crosshairs"):
                names = s["crosshairs"]
                lines.append((T(f"Crosshairs ({len(names)})", f"Crosshairs ({len(names)})"),
                              "\n".join(names[:10])))
            if "keybinds" in s:
                lines.append((T("Touches personnalisées", "Custom keybinds"),
                              str(len(s["keybinds"]))))
            if "n_settings" in s:
                lines.append((T("Autres réglages", "Other settings"),
                              T(f"{s['n_settings']} valeurs (audio, HUD, minimap...)",
                                f"{s['n_settings']} values (audio, HUD, minimap...)")))
        for key, label in (("resolution", T("Résolution", "Resolution")),
                           ("fps_limit", T("Limite FPS", "FPS limit")),
                           ("screen_mode", T("Mode d'affichage", "Display mode"))):
            if key in s:
                lines.append((label, str(s[key])))

        dlg = ctk.CTkToplevel(self)
        dlg.title(T(f"Détails — {prof['name']}", f"Details — {prof['name']}"))
        dlg.configure(fg_color=C_PANEL)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        ctk.CTkLabel(dlg, text=prof["name"], font=(theme.FONT_UI, 16, "bold"),
                     text_color=C_TEXT).pack(padx=26, pady=(18, 8), anchor="w")
        grid = ctk.CTkFrame(dlg, fg_color=C_BG, corner_radius=10)
        grid.pack(padx=22, pady=4, fill="both")
        for label, value in lines:
            row = ctk.CTkFrame(grid, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=5)
            ctk.CTkLabel(row, text=label, font=(theme.FONT_UI, 12, "bold"),
                         text_color=C_TEXT_DIM, width=200, anchor="nw",
                         justify="left").pack(side="left")
            ctk.CTkLabel(row, text=value, font=(theme.FONT_UI, 12), text_color=C_TEXT,
                         anchor="nw", justify="left", wraplength=300).pack(
                side="left", fill="x", expand=True)
        ctk.CTkButton(dlg, text=T("Fermer", "Close"), width=120, fg_color=C_RED,
                      hover_color=C_RED_HOVER, font=(theme.FONT_UI, 12, "bold"),
                      command=dlg.destroy).pack(pady=(14, 18))
        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        try:
            dlg.after(220, lambda: dlg.iconbitmap(str(resource_path("icon.ico"))))
        except Exception:
            pass

    def export_profile(self, prof: dict):
        safe = re.sub(r'[\\/:*?"<>|]', "_", prof["name"]).strip() or "profil"
        path = filedialog.asksaveasfilename(
            title=T("Exporter le profil", "Export profile"),
            initialfile=f"{safe}{PROFILE_EXT}",
            defaultextension=PROFILE_EXT,
            filetypes=[(T("Profil Valorant Config Manager", "Valorant Config Manager profile"),
                        f"*{PROFILE_EXT}")])
        if not path:
            return
        try:
            write_profile_archive(prof["path"], path)
        except OSError as e:
            messagebox.showerror(APP_NAME, T(f"Export impossible :\n{e}",
                                             f"Export failed:\n{e}"))
            return
        self.set_status(T(f"Profil exporté : {Path(path).name} ✔",
                          f"Profile exported: {Path(path).name} ✔"), C_GREEN)

    def import_profile(self, path: str | None = None):
        if not path:
            path = filedialog.askopenfilename(
                title=T("Importer un profil", "Import a profile"),
                filetypes=[(T("Profil Valorant Config Manager",
                              "Valorant Config Manager profile"), f"*{PROFILE_EXT}"),
                           (T("Tous les fichiers", "All files"), "*.*")])
        if not path:
            return
        ensure_dirs()
        profile_id = uuid.uuid4().hex[:12]
        dest = PROFILES_DIR / profile_id
        try:
            meta = extract_profile_archive(path, dest)
        except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as e:
            shutil.rmtree(dest, ignore_errors=True)
            messagebox.showerror(APP_NAME, T(f"Import impossible :\n{e}",
                                             f"Import failed:\n{e}"))
            return
        resolved = self._resolve_profile_name(
            str(meta.get("name") or T("Profil importé", "Imported profile")))
        if resolved is None:
            shutil.rmtree(dest, ignore_errors=True)
            return
        name, to_replace = resolved
        meta["name"] = name
        meta.pop("id", None)
        meta.pop("path", None)
        (dest / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        for old in to_replace:
            shutil.rmtree(old["path"], ignore_errors=True)
        self.refresh()
        has_cloud = (dest / "cloud.json").is_file()
        extra = " (cloud)" if has_cloud else T(" (local uniquement)", " (local only)")
        self.set_status(T(f"Profil « {name} » importé{extra} ✔",
                          f"Profile \"{name}\" imported{extra} ✔"), C_GREEN)

    def delete_profile(self, prof: dict):
        if messagebox.askyesno(APP_NAME,
                               T(f"Supprimer définitivement le profil « {prof['name']} » ?",
                                 f"Permanently delete the profile \"{prof['name']}\"?")):
            shutil.rmtree(prof["path"], ignore_errors=True)
            self.refresh()
            self.set_status(T(f"Profil « {prof['name']} » supprimé.",
                              f"Profile \"{prof['name']}\" deleted."), C_ORANGE)

    def restore_backup(self):
        if not self.accounts:
            messagebox.showwarning(APP_NAME, T("Aucun compte détecté.", "No account found."))
            return
        acc_choices = []
        seen = set()
        for folder, _, _ in self.accounts:
            seen.add(folder)
            n = len(list_backups(folder))
            if n:
                acc_choices.append((folder, f"{self._account_label(folder)}   ({n} "
                                            + T("sauvegarde(s))", "backup(s))")))
        # Sauvegardes "cloud uniquement" : comptes sans dossier local sur ce PC
        if BACKUPS_DIR.is_dir():
            for d in BACKUPS_DIR.iterdir():
                if d.is_dir() and d.name not in seen and list_backups(d.name):
                    n = len(list_backups(d.name))
                    acc_choices.append(
                        (d.name, self._account_label(d.name)
                         + T("   (cloud uniquement)", "   (cloud only)")
                         + f"   ({n} " + T("sauvegarde(s))", "backup(s))")))
        if not acc_choices:
            messagebox.showinfo(APP_NAME,
                                T("Aucune sauvegarde disponible.\nDes sauvegardes sont créées "
                                  "automatiquement à chaque application de profil.",
                                  "No backup available.\nBackups are created automatically "
                                  "every time a profile is applied."))
            return
        folder = ChoiceDialog(self, T("Restaurer", "Restore"),
                              T("Restaurer une sauvegarde de quel compte ?",
                                "Restore a backup of which account?"),
                              acc_choices, confirm_text=T("Suivant", "Next")).get()
        if not folder:
            return
        backups = list_backups(folder)
        bk_choices = []
        for b in backups:
            base = b.name.replace("_auto", "")
            label = base.replace("_", "  ").replace("-", "/", 2)
            if b.name.endswith("_auto"):
                label += "   (auto)"
            if (b / "cloud.json").is_file():
                label += "   (cloud)"
            bk_choices.append((str(b), label))
        chosen = ChoiceDialog(self, T("Restaurer", "Restore"),
                              T("Quelle sauvegarde restaurer ?", "Which backup to restore?"),
                              bk_choices, confirm_text=T("Restaurer", "Restore")).get()
        if not chosen:
            return
        if is_valorant_running():
            messagebox.showwarning(APP_NAME,
                                   T("Ferme Valorant avant de restaurer une sauvegarde.",
                                     "Close Valorant before restoring a backup."))
            return
        chosen_path = Path(chosen)
        # Anciennes sauvegardes (v1.0) : fichiers à la racine ; nouvelles : sous
        # files/ ; sauvegardes "cloud uniquement" : aucun fichier local.
        files_src = chosen_path / "files"
        if not files_src.is_dir():
            files_src = chosen_path if any(
                f.name != "cloud.json" for f in chosen_path.iterdir()) else None
        try:
            if files_src is not None:
                apply_files(files_src, VALO_CONFIG_DIR / folder)
            loc_msg = T("Fichiers locaux restaurés ✔", "Local files restored ✔") \
                if files_src is not None \
                else T("Cette sauvegarde ne contient que les paramètres cloud.",
                       "This backup only contains cloud settings.")
            cloud_file = chosen_path / "cloud.json"
            if cloud_file.is_file():
                cloud = json.loads(cloud_file.read_text(encoding="utf-8"))
                try:
                    tokens = riot_cloud.get_tokens()
                    if tokens.get("subject", "").lower() == cloud.get("subject", "").lower():
                        riot_cloud.put_cloud_settings(tokens, cloud["settings"])
                        self.set_status(
                            T("Sauvegarde restaurée (fichiers + cloud) ✔",
                              "Backup restored (files + cloud) ✔") if files_src is not None
                            else T("Sauvegarde restaurée (cloud) ✔",
                                   "Backup restored (cloud) ✔"), C_GREEN)
                    else:
                        messagebox.showinfo(
                            APP_NAME,
                            loc_msg + T("\n\nLes paramètres cloud n'ont pas été "
                                        "restaurés : le compte connecté au client Riot "
                                        "n'est pas celui de cette sauvegarde.",
                                        "\n\nCloud settings were not restored: the "
                                        "account logged into the Riot Client is not the "
                                        "one from this backup."))
                except RiotClientError:
                    messagebox.showinfo(
                        APP_NAME,
                        loc_msg + T("\n\nParamètres cloud non restaurés (client Riot "
                                    "fermé). Connecte-toi puis recommence si besoin.",
                                    "\n\nCloud settings not restored (Riot Client "
                                    "closed). Log in and retry if needed."))
            else:
                self.set_status(T("Sauvegarde restaurée (fichiers locaux) ✔",
                                  "Backup restored (local files) ✔"), C_GREEN)
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showerror(APP_NAME, T(f"Erreur pendant la restauration :\n{e}",
                                             f"Error while restoring:\n{e}"))
            return
        self.refresh()

    def launch_valorant(self):
        if is_valorant_running():
            messagebox.showinfo(APP_NAME, T("Valorant est déjà lancé.",
                                            "Valorant is already running."))
            return
        if riot_cloud.launch_riot_client(product="valorant"):
            self.set_status(T("Lancement de Valorant...", "Launching Valorant..."), C_GREEN)
        else:
            messagebox.showerror(APP_NAME, T("Client Riot introuvable sur ce PC.",
                                             "Riot Client not found on this PC."))

    # ---------------------------------------------------------- Barre système
    def _setup_tray(self):
        try:
            import pystray
            from PIL import Image
            ico = resource_path("icon.ico")
            image = Image.open(ico) if ico.is_file() else Image.new("RGB", (64, 64), "#ff4655")
            menu = pystray.Menu(
                pystray.MenuItem(T("Ouvrir", "Open"), self._tray_show, default=True),
                pystray.MenuItem(T("Quitter", "Quit"), self._tray_quit),
            )
            self.tray = pystray.Icon(APP_ID, image, APP_NAME, menu)
            threading.Thread(target=self.tray.run, daemon=True).start()
        except Exception:
            self.tray = None

    def _tray_show(self, icon=None, item=None):
        self.after(0, self._show_window)

    def _tray_quit(self, icon=None, item=None):
        self.after(0, self.destroy)

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_close_window(self):
        if self.tray is None or not self._setting("close_to_tray", True):
            self.destroy()
            return
        self.withdraw()
        if not self.settings.get("tray_notice_shown"):
            self.settings["tray_notice_shown"] = True
            save_settings(self.settings)
            try:
                self.tray.notify(
                    T("Toujours actif à côté de l'horloge. Double-clic pour rouvrir, "
                      "clic droit → Quitter pour fermer.",
                      "Still running next to the clock. Double-click to reopen, "
                      "right-click → Quit to exit."), APP_NAME)
            except Exception:
                pass

    def destroy(self):
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
            self.tray = None
        super().destroy()

    # ------------------------------------------------------------ Divers ----
    _last_game_running = False

    def _poll_status(self):
        def worker():
            game = is_valorant_running()
            riot_id, subject = "", ""
            try:
                tokens = riot_cloud.get_tokens()
                subject = tokens.get("subject", "")
                riot_id = riot_cloud.get_riot_id()
            except RiotClientError:
                pass
            try:
                self.after(0, lambda: self._update_status_ui(game, riot_id, subject))
            except RuntimeError:
                pass

        threading.Thread(target=worker, daemon=True).start()
        self.after(6000, self._poll_status)

    def _update_status_ui(self, game_running: bool, riot_id: str, subject: str):
        self._last_game_running = game_running
        if game_running:
            self.valo_status.configure(
                text=T("●  Jeu Valorant : EN COURS — ferme-le pour transférer",
                       "●  Valorant game: RUNNING — close it to transfer"),
                text_color=C_RED)
            self.valo_pill.configure(border_color="#6b2a33")
        else:
            self.valo_status.configure(text=T("●  Jeu Valorant : fermé",
                                              "●  Valorant game: closed"),
                                       text_color=C_GREEN)
            self.valo_pill.configure(border_color="#20563c")

        changed = (subject != self.connected_subject)
        self.connected_riot_id, self.connected_subject = riot_id, subject
        if subject:
            self.riot_status.configure(
                text=T(f"●  Client Riot : connecté en tant que {riot_id or '?'}",
                       f"●  Riot Client: logged in as {riot_id or '?'}"),
                text_color=C_GREEN)
            self.riot_pill.configure(border_color="#20563c")
            folder = folder_for_puuid(subject)
            # Nommage automatique du compte connecté
            if folder and riot_id and not self.account_names.get(folder):
                self.account_names[folder] = riot_id
                save_account_names(self.account_names)
                changed = True
            # Détection de changement de compte (pas au premier compte vu)
            if (self._last_seen_subject and subject != self._last_seen_subject
                    and self.profiles and self._setting("login_banner", True)):
                if self.state() == "withdrawn" and self.tray is not None:
                    try:
                        self.tray.notify(
                            T(f"{riot_id} vient de se connecter.",
                              f"{riot_id} just logged in."), APP_NAME)
                    except Exception:
                        pass
                self._show_banner(riot_id or T("Nouveau compte", "New account"))
            if subject != self._last_seen_subject:
                self._last_seen_subject = subject
            # Historique automatique : un instantané par compte et par session
            if (folder and subject not in self._snapshotted and not game_running
                    and self._setting("auto_snapshot", True)):
                self._snapshotted.add(subject)
                threading.Thread(target=self._auto_snapshot,
                                 args=(folder,), daemon=True).start()
        else:
            self.riot_status.configure(
                text=T("●  Client Riot : personne n'est connecté",
                       "●  Riot Client: nobody is logged in"),
                text_color=C_ORANGE)
            self.riot_pill.configure(border_color="#6b542a")
        if changed:
            self._render_accounts()

    def _auto_snapshot(self, folder: str):
        """Instantané silencieux du compte connecté (fichiers + cloud)."""
        try:
            cloud = None
            try:
                tokens = riot_cloud.get_tokens()
                cloud = {
                    "riot_id": self.connected_riot_id,
                    "subject": tokens.get("subject", ""),
                    "settings": riot_cloud.get_cloud_settings(tokens),
                }
            except RiotClientError:
                pass
            backup_account(VALO_CONFIG_DIR / folder, cloud=cloud, auto=True)
            label = self._account_label(folder)
            self.after(0, lambda: self.set_status(
                T(f"Instantané automatique de « {label} » créé ✔",
                  f"Automatic snapshot of \"{label}\" created ✔"), C_TEXT_DIM))
        except (OSError, RuntimeError):
            pass
