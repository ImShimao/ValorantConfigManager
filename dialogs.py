# -*- coding: utf-8 -*-
"""Boîtes de dialogue personnalisées (choix dans une liste, saisie)."""

import customtkinter as ctk

import theme
from appinfo import resource_path
from i18n import T
from theme import C_BG, C_CARD, C_CARD_HOVER, C_PANEL, C_RED, C_RED_HOVER, C_TEXT

# ----------------------------------------------------------------------------
# Boîtes de dialogue personnalisées
# ----------------------------------------------------------------------------
class _Dialog(ctk.CTkToplevel):
    def _finish_setup(self, master):
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.bind("<Escape>", lambda e: self._cancel())
        try:
            self.after(220, lambda: self.iconbitmap(str(resource_path("icon.ico"))))
        except Exception:
            pass

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
