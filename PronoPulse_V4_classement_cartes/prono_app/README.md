# PronoPulse

Application Flask de pronostics et de collection virtuelle.

## Lancement

1. Installer Python 3.
2. Ouvrir un terminal dans ce dossier.
3. `python -m pip install flask`
4. `python app.py`
5. Ouvrir `http://127.0.0.1:5000`

Le script `lancer_site.bat` à la racine du projet lance l'application automatiquement.

## Compte admin automatique

Au premier lancement, le compte est créé :

- Identifiant : `admin`
- Mot de passe : `PronoPulseAdmin123!`

Tu peux changer le mot de passe via la variable d'environnement `ADMIN_PASSWORD` avant le premier lancement.

## Cartes

Place tes images dans :

`prono_app/static/cards/`

Puis, dans **⚙ Gestion**, ajoute une carte avec son nom de fichier (ex. `joueur.png`).

Prix : Hommes 100 pts, Femmes 50 pts, Réserve 25 pts.
Valeur pour le classement collection : Homme 3, Femme 2, Réserve 1.

## Nouveautés

- Bouton de fermeture de l'animation de récompense corrigé : le timer est annulé quand on ferme l'animation.
- Classement : tri par points ou par valeur de collection (3/2/1).
- Collection : progression `cartes débloquées / cartes totales`.
- Une carte ne peut être achetée qu'une seule fois par compte, mais reste achetable par les autres comptes.
- Tous les 5 bons résultats, le compte reçoit un pack gratuit.
- Le pack gratuit permet de choisir n'importe quelle carte encore bloquée, toutes catégories confondues.
