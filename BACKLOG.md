# Idées et chantiers à venir

## Vraie sélection des joueur·euses (noté le 2026-10-02)

**Constat** : l'option « Sélection de joueur·euses » ne filtre personne.
- Avec l'option, l'inscription passe toujours (`register_player(..., force=game.party_selection)`
  dans `website/views/games.py`) : pas de limite de places, pas de fermeture automatique.
- Chaque inscrit reçoit tout de suite le rôle, donc l'accès au salon caché, avant d'avoir été
  choisi. Le MJ trie après coup avec « Gérer », ce bouton n'apparaissant qu'une fois la partie
  fermée.
- Défaut : `force=True` ignore aussi le statut « fermée ». Le bouton est masqué, mais une requête
  POST directe sur `/annonces/<slug>/inscription/` passe quand même.

**Proposition** :
- Les joueur·euses **candidatent** et arrivent dans une liste « En attente », sans rôle ni accès
  au salon.
- Le MJ **accepte ou refuse** chaque candidat depuis la fiche. Une fois accepté, le joueur reçoit
  le rôle et un message de bienvenue est posté dans le salon.
- Les candidatures restent possibles au-delà du nombre de places. Les acceptations, elles, sont
  limitées au nombre de places, sauf si le MJ force.
- Corriger le défaut : une partie fermée refuse les inscriptions et les candidatures, même sur
  sélection.

**À prévoir** : une nouvelle table (candidatures : partie, joueur, statut, date) et sa migration,
des méthodes de service (candidater, accepter, refuser), les boutons sur la fiche, un message
Discord à l'acceptation, une entrée dans le journal d'activité, des tests.

## Jeux Steam en commun — finitions repérées en relecture (noté le 2026-10-02)

Points mineurs relevés par la relecture de la branche `feat/steam-common-games`, non corrigés :
- Vérifier la fraîcheur de `X-Signature-Timestamp` (refuser au-delà de 5 min) contre le rejeu.
- Signaler dans les journaux une `DISCORD_PUBLIC_KEY` mal formée (aujourd'hui : 401 silencieux).
- Signaler une `STEAM_API_KEY` absente (aujourd'hui : « Steam ne répond pas » pour tout le monde).
- Utiliser le pseudo de serveur des membres cités (`resolved.members[id].nick`).
- Ignorer une connexion Steam révoquée (`revoked`) à la liaison.
- Échapper toute la mise en forme Markdown dans les noms de jeux (`* _ ~ \` |`).
- Fils d'exécution illimités ; un redéploiement pendant un calcul laisse « réfléchit… ».
