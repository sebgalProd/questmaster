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
