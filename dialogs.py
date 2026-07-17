# -*- coding: utf-8 -*-
"""Boîtes de dialogue personnalisées (choix dans une liste, saisie)."""

import customtkinter as ctk

import theme
from appinfo import resource_path
from i18n import T
from theme import (C_BG, C_CARD, C_CARD_HOVER, C_PANEL, C_RED, C_RED_HOVER,
                   C_TEXT, C_TEXT_DIM)


def place_over(win, master, on_escape=None):
    """Centre `win` sur `master`, lie la touche Échap et rétablit l'icône.

    Factorisé et réutilisé par toutes les boîtes de dialogue : un CTkToplevel
    n'hérite pas de l'icône de la fenêtre principale, et CustomTkinter la
    réécrit ~200 ms après l'ouverture — d'où le `after(220, ...)`."""
    win.update_idletasks()
    x = master.winfo_rootx() + (master.winfo_width() - win.winfo_width()) // 2
    y = master.winfo_rooty() + (master.winfo_height() - win.winfo_height()) // 2
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.bind("<Escape>", lambda e: (on_escape or win.destroy)())
    try:
        win.after(220, lambda: win.iconbitmap(str(resource_path("icon.ico"))))
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Boîtes de dialogue personnalisées
# ----------------------------------------------------------------------------
class _Dialog(ctk.CTkToplevel):
    def _finish_setup(self, master):
        place_over(self, master, on_escape=self._cancel)

    def _cancel(self):
        self.result = None
        self.destroy()

    def get(self):
        self.master.wait_window(self)
        return self.result


class ChoiceDialog(_Dialog):
    """Choisir un élément dans une liste (radio buttons)."""

    def __init__(self, master, title: str, message: str, choices: list[tuple[str, str]],
                 confirm_text: str | None = None, preselect: str | None = None):
        super().__init__(master)
        self.title(title)
        self.configure(fg_color=C_PANEL)
        self.resizable(False, False)
        self.result = None
        self.transient(master)
        self.grab_set()

        ctk.CTkLabel(self, text=message, font=(theme.FONT_UI, 14, "bold"),
                     text_color=C_TEXT, wraplength=430, justify="left").pack(
            padx=24, pady=(20, 10), anchor="w")

        default = preselect if preselect in [c[0] for c in choices] else (choices[0][0] if choices else "")
        self._var = ctk.StringVar(value=default)
        frame = ctk.CTkScrollableFrame(self, fg_color=C_BG, width=440,
                                       height=min(64 * max(len(choices), 1), 260))
        frame.pack(padx=24, pady=4, fill="both", expand=True)
        for value, label in choices:
            ctk.CTkRadioButton(
                frame, text=label, variable=self._var, value=value,
                font=(theme.FONT_UI, 13), text_color=C_TEXT,
                fg_color=C_RED, hover_color=C_RED_HOVER,
            ).pack(anchor="w", padx=12, pady=7)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(padx=24, pady=(12, 20), fill="x")
        ctk.CTkButton(btns, text=T("Annuler", "Cancel"), width=110, fg_color=C_CARD,
                      hover_color=C_CARD_HOVER, text_color=C_TEXT,
                      command=self._cancel).pack(side="left")
        ctk.CTkButton(btns, text=confirm_text or T("Valider", "Confirm"), width=160,
                      fg_color=C_RED, hover_color=C_RED_HOVER,
                      font=(theme.FONT_UI, 13, "bold"), command=self._ok).pack(side="right")
        self._finish_setup(master)

    def _ok(self):
        self.result = self._var.get()
        self.destroy()


class CheckDialog(_Dialog):
    """Choisir plusieurs éléments dans une liste (cases à cocher).

    `items` : [(valeur, libellé, description)]. `preselect` : valeurs cochées
    au départ. Retourne la liste des valeurs cochées, ou None si annulé."""

    def __init__(self, master, title: str, message: str,
                 items: list[tuple[str, str, str]], preselect=None,
                 confirm_text: str | None = None):
        super().__init__(master)
        self.title(title)
        self.configure(fg_color=C_PANEL)
        self.resizable(False, False)
        self.result = None
        self.transient(master)
        self.grab_set()

        ctk.CTkLabel(self, text=message, font=(theme.FONT_UI, 14, "bold"),
                     text_color=C_TEXT, wraplength=470, justify="left").pack(
            padx=24, pady=(20, 8), anchor="w")

        checked = set(preselect if preselect is not None else [v for v, _, _ in items])
        self._vars: dict[str, ctk.BooleanVar] = {}

        frame = ctk.CTkScrollableFrame(self, fg_color=C_BG, width=480,
                                       height=min(62 * max(len(items), 1), 330))
        frame.pack(padx=24, pady=4, fill="both", expand=True)
        for value, label, desc in items:
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=6)
            var = ctk.BooleanVar(value=value in checked)
            self._vars[value] = var
            ctk.CTkCheckBox(row, text=label, variable=var,
                            font=(theme.FONT_UI, 13, "bold"), text_color=C_TEXT,
                            fg_color=C_RED, hover_color=C_RED_HOVER,
                            checkbox_width=20, checkbox_height=20,
                            command=self._update_state).pack(anchor="w")
            if desc:
                ctk.CTkLabel(row, text=desc, font=(theme.FONT_UI, 11),
                             text_color=C_TEXT_DIM, wraplength=430,
                             justify="left", anchor="w").pack(
                    anchor="w", fill="x", padx=(30, 0))

        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(padx=24, pady=(6, 0), fill="x")
        ctk.CTkButton(tools, text=T("Tout cocher", "Select all"), width=110, height=26,
                      fg_color=C_CARD, hover_color=C_CARD_HOVER, text_color=C_TEXT,
                      font=(theme.FONT_UI, 11),
                      command=lambda: self._set_all(True)).pack(side="left")
        ctk.CTkButton(tools, text=T("Tout décocher", "Select none"), width=110, height=26,
                      fg_color=C_CARD, hover_color=C_CARD_HOVER, text_color=C_TEXT,
                      font=(theme.FONT_UI, 11),
                      command=lambda: self._set_all(False)).pack(side="left", padx=8)
        self._hint = ctk.CTkLabel(tools, text="", font=(theme.FONT_UI, 11),
                                  text_color=C_TEXT_DIM)
        self._hint.pack(side="right")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(padx=24, pady=(12, 20), fill="x")
        ctk.CTkButton(btns, text=T("Annuler", "Cancel"), width=110, fg_color=C_CARD,
                      hover_color=C_CARD_HOVER, text_color=C_TEXT,
                      command=self._cancel).pack(side="left")
        self._ok_btn = ctk.CTkButton(btns, text=confirm_text or T("Valider", "Confirm"),
                                     width=160, fg_color=C_RED, hover_color=C_RED_HOVER,
                                     font=(theme.FONT_UI, 13, "bold"), command=self._ok)
        self._ok_btn.pack(side="right")

        self._update_state()
        self._finish_setup(master)

    def _set_all(self, value: bool):
        for var in self._vars.values():
            var.set(value)
        self._update_state()

    def _selected(self) -> list:
        return [v for v, var in self._vars.items() if var.get()]

    def _update_state(self):
        """Valider est désactivé tant que rien n'est coché : un profil vide
        n'aurait aucun sens."""
        n = len(self._selected())
        self._hint.configure(text=T(f"{n} sélectionnée(s)", f"{n} selected"))
        self._ok_btn.configure(state="normal" if n else "disabled")

    def _ok(self):
        selected = self._selected()
        if selected:
            self.result = selected
            self.destroy()


class TextDialog(_Dialog):
    """Saisie de texte (nom de profil / de compte)."""

    def __init__(self, master, title: str, message: str, initial: str = ""):
        super().__init__(master)
        self.title(title)
        self.configure(fg_color=C_PANEL)
        self.resizable(False, False)
        self.result = None
        self.transient(master)
        self.grab_set()

        ctk.CTkLabel(self, text=message, font=(theme.FONT_UI, 14, "bold"),
                     text_color=C_TEXT, wraplength=400, justify="left").pack(
            padx=24, pady=(20, 10), anchor="w")
        self._entry = ctk.CTkEntry(self, width=400, height=36, font=(theme.FONT_UI, 13),
                                   fg_color=C_BG, border_color=C_RED, text_color=C_TEXT)
        self._entry.pack(padx=24, pady=4)
        self._entry.insert(0, initial)
        self._entry.select_range(0, "end")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(padx=24, pady=(14, 20), fill="x")
        ctk.CTkButton(btns, text=T("Annuler", "Cancel"), width=110, fg_color=C_CARD,
                      hover_color=C_CARD_HOVER, text_color=C_TEXT,
                      command=self._cancel).pack(side="left")
        ctk.CTkButton(btns, text=T("Valider", "Confirm"), width=140, fg_color=C_RED,
                      hover_color=C_RED_HOVER, font=(theme.FONT_UI, 13, "bold"),
                      command=self._ok).pack(side="right")

        self._entry.bind("<Return>", lambda e: self._ok())
        self._finish_setup(master)
        self.after(120, self._entry.focus_set)

    def _ok(self):
        text = self._entry.get().strip()
        if text:
            self.result = text
            self.destroy()
