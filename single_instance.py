# -*- coding: utf-8 -*-
"""Instance unique, via un socket en boucle locale.

La 1re instance réserve 127.0.0.1:<port> et l'écoute. Un lancement suivant
échoue à réserver le port, se connecte donc à la 1re pour lui demander de se
montrer (en lui transmettant un éventuel fichier .vcmprofile à importer), puis
se termine.

Boucle locale (127.0.0.1) uniquement : pas d'invite du pare-feu Windows, rien
d'exposé sur le réseau. La réservation exclusive du port sert de verrou : c'est
elle qui garantit qu'une seule instance peut être « primaire ».

Poignée de main : la 1re instance s'annonce par « VCM1 » dès la connexion. Si
le port est occupé par un AUTRE programme, l'annonce manque et signal_primary
retourne False — l'appli démarre alors normalement au lieu de croire, à tort,
qu'une instance tourne déjà.
"""

import socket
import threading

_HOST = "127.0.0.1"
_PORT = 49731  # port fixe dans la plage dynamique, peu susceptible d'être pris
_MAGIC = b"VCM1\n"


def acquire():
    """Socket serveur si on est la 1re instance, sinon None (une autre tourne)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((_HOST, _PORT))
        s.listen(8)
    except OSError:
        s.close()
        return None
    return s


def signal_primary(payload: str = "") -> bool:
    """Demande à l'instance déjà ouverte de se montrer.

    True seulement si l'interlocuteur s'est annoncé comme notre appli."""
    try:
        with socket.create_connection((_HOST, _PORT), timeout=2) as c:
            c.settimeout(2)
            if not c.recv(len(_MAGIC)).startswith(_MAGIC.strip()):
                return False
            c.sendall(("SHOW|" + payload).encode("utf-8"))
        return True
    except OSError:
        return False


def serve(server_sock, on_signal):
    """Écoute les demandes des lancements suivants ; appelle on_signal(payload)."""
    def loop():
        while True:
            try:
                conn, _ = server_sock.accept()
            except OSError:
                break  # socket fermé (arrêt de l'appli)
            try:
                with conn:
                    conn.sendall(_MAGIC)
                    data = conn.recv(4096).decode("utf-8", "ignore")
            except OSError:
                continue
            if not data.startswith("SHOW"):
                continue
            payload = data.split("|", 1)[1] if "|" in data else ""
            on_signal(payload.strip())

    threading.Thread(target=loop, daemon=True).start()
