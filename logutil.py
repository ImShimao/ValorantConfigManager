# -*- coding: utf-8 -*-
"""Journalisation vers un fichier, pour diagnostiquer les soucis chez les
utilisateurs (l'appli est distribuée en .exe sans console).

Le log est écrit dans %LOCALAPPDATA%\\ValorantConfigManager\\logs\\vcm.log,
avec rotation pour ne jamais grossir sans limite. Les exceptions non
rattrapées (thread principal, autres threads, callbacks Tk) y sont capturées.
"""

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from core import DATA_DIR

log = logging.getLogger("vcm")
_configured = False


def setup_logging():
    """Configure le logger racine « vcm » et capte les exceptions non gérées.

    Idempotent : sans effet si déjà appelé.
    """
    global _configured
    if _configured:
        return
    _configured = True

    log.setLevel(logging.INFO)
    try:
        log_dir = DATA_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "vcm.log", maxBytes=512 * 1024, backupCount=3,
            encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        log.addHandler(handler)
    except Exception:
        # Sans fichier de log accessible, on n'empêche pas l'appli de tourner.
        log.addHandler(logging.NullHandler())

    def _hook(exc_type, exc, tb):
        log.critical("Exception non rattrapée",
                     exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook

    # Threads (Python 3.8+)
    if hasattr(threading, "excepthook"):
        def _thook(args):
            log.critical("Exception non rattrapée dans un thread",
                         exc_info=(args.exc_type, args.exc_value,
                                   args.exc_traceback))
        threading.excepthook = _thook
