# Valorant Config Manager

Sauvegarde et transfère tes paramètres Valorant (vidéo, crosshair, sensibilité, keybinds…)
entre plusieurs comptes Riot sur le même PC.

## Comment ça marche

Valorant stocke les paramètres à deux endroits :

1. **Fichiers locaux** (paramètres vidéo, propres au PC) :
   `%LOCALAPPDATA%\VALORANT\Saved\Config\<identifiant-du-compte>\`
2. **Cloud Riot** (crosshair, sensibilité, keybinds…) : synchronisé par les serveurs Riot
   à chaque connexion. *C'est pour ça qu'une simple copie de fichiers ne suffit pas —
   le jeu réécrase tout avec le cloud au lancement.*

Le logiciel gère **les deux** : il copie les fichiers locaux ET lit/écrit les paramètres
cloud via l'API du client Riot (la même que le jeu utilise). Aucun mot de passe n'est
demandé ni stocké : il utilise la session déjà ouverte dans le client Riot.

## Utilisation (transfert complet)

1. **Ferme le jeu Valorant** (le client Riot peut rester ouvert — il le faut, même).
2. Ouvre le **client Riot** et connecte-toi au compte **source** (celui dont tu veux
   copier les paramètres). L'en-tête de l'appli affiche « Client Riot : Pseudo#TAG ».
3. Clique sur **💾 Sauvegarder en profil** sur ce compte → le profil affiche **☁**
   (= crosshair, sensi et keybinds inclus).
4. Dans le client Riot, **déconnecte-toi et connecte-toi au compte cible**.
5. Clique sur **▶ Appliquer sur un compte** sur le profil, choisis le compte cible.
6. Lance Valorant : tous les paramètres sont là.

L'appli vérifie que le compte connecté correspond au compte cible (grâce au PUUID),
crée une **sauvegarde automatique** avant chaque application (locaux + cloud), et le
bouton **↩ Restaurer une sauvegarde** permet de revenir en arrière.

Les comptes sont **nommés automatiquement** avec leur Riot ID dès qu'ils sont connectés
au client Riot pendant que l'appli tourne. Tu peux aussi les renommer à la main.

Profils et sauvegardes sont stockés dans `%LOCALAPPDATA%\ValorantConfigManager\`.

## Fonctions

- ⚡ **Transfert express** : applique un profil au compte connecté + lance le jeu, en un clic.
- 🔄 **Détection de changement de compte** : bannière (et notification) quand un autre
  compte se connecte au client Riot, avec transfert express direct.
- 📸 **Historique automatique** : instantané silencieux (fichiers + cloud) du compte
  connecté à chaque session, marqué « auto » dans les sauvegardes.
- ⇆ **Comparateur de profils** : différences côte à côte (sensi, ADS, crosshairs,
  touches, résolution, FPS…).
- 🔔 **Icône barre système** : fermer la fenêtre réduit l'appli à côté de l'horloge
  (double-clic pour rouvrir, clic droit → Quitter).
- 📁 **Double-clic sur un `.vcmprofile`** : l'extension est associée automatiquement,
  le fichier s'importe tout seul.
- 🌐 **Bilingue** : bouton FR/EN dans l'en-tête.

## Développement

Python 3 + CustomTkinter, découpé en modules :

- `main.py` — point d'entrée (arguments, langue, lancement)
- `app.py` — fenêtre principale
- `core.py` — logique sans interface : comptes, profils, sauvegardes, archives
- `riot_cloud.py` — accès local au client Riot + service player-preferences
  (serveurs `player-preferences-*.pp.sgp.pvp.net`, trouvés via la config publique
  du client Riot ; l'ancien `playerpreferences.riotgames.com` est mort)
- `dialogs.py` — boîtes de dialogue personnalisées
- `theme.py` — couleurs, polices, icônes · `i18n.py` — langue FR/EN ·
  `appinfo.py` — métadonnées · `make_icon.py` — génère `icon.ico`
- Dépendances : `pip install -r requirements.txt` (dev : `-r requirements-dev.txt`)
- Tests : `python -m pytest` (logique pure, sans interface ni données réelles)
- Build : `python -m PyInstaller --noconfirm --onefile --windowed --name ValorantConfigManager --icon icon.ico --add-data "icon.ico;." --collect-all customtkinter main.py`
- Installateur : compiler `installer.iss` avec Inno Setup (`iscc installer.iss`)

## Avertissement

Le logiciel ne modifie que des fichiers de configuration et les préférences de jeu
du compte connecté. Il ne demande jamais d'identifiants et n'automatise rien dans le
jeu. Les jetons de session ne sont jamais écrits sur le disque.
