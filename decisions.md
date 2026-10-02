# Décisions — parties permanentes, type « Salon », texte d'inscription

Date : 2026-10-02 — branche `feat/permanent-and-salon`

## 1. Parties permanentes (sans date ni durée)

- **Nouveau champ `permanent`** (booléen, `false` par défaut) sur la table `game`, plutôt que de
  déduire « permanent » d'une date vide. C'est explicite et ça se filtre facilement.
- Les colonnes `date` et `session_length` deviennent **facultatives** en base (elles étaient
  obligatoires). Une partie permanente a `date = NULL`, `session_length = NULL`,
  `frequency = NULL` et `length = "Permanent"`.
- **Formulaire** : un interrupteur « ∞ Permanent (sans date ni durée) » sous le type de session.
  Quand il est coché, les champs Date, Durée et Fréquence sont masqués et désactivés : ils ne
  sont plus obligatoires et ne sont pas envoyés.
- L'interrupteur reste **modifiable après publication** : on peut rendre une partie permanente
  (ou lui redonner une date) à tout moment, et l'annonce Discord se met à jour.
- **Pas de session initiale** à la publication d'une partie permanente : le calendrier et les
  statistiques ne la voient donc pas. Le MJ peut toujours ajouter des sessions à la main s'il
  veut caler un rendez-vous ponctuel.
- **Affichage** : « ∞ Permanent » à la place de la date sur la carte et sur la fiche. La durée
  n'est plus affichée.
- **Annonce Discord** : le champ Date affiche « Permanent » et le champ Durée disparaît.
- **Tri des annonces** : les annonces sans date sont classées avec les parties à venir, après
  celles qui ont une date.

## 2. Texte d'inscription sur Discord

- Le champ « Pour s'inscrire : » de l'annonce devient
  **« Pour s'inscrire et afficher le salon caché : »**, pour tous les types.
- Les annonces déjà publiées gardent l'ancien texte tant qu'elles ne sont pas modifiées. Toute
  modification ou tout changement de statut (ouverture, fermeture, inscription qui remplit la
  table) régénère le message avec le nouveau texte.

## 3. Nouveau type « Salon »

Un salon est une annonce qui n'est pas une partie : un salon Discord thématique qu'on rejoint
depuis QuestMaster (ex. `contre-les-coups-de-mou`, `bitcoin`, `la chouette d'or`).

- **Valeur `salon`** ajoutée à l'enum `game_type_enum`. On réutilise le modèle `Game` plutôt que
  de créer un modèle séparé : inscription, rôle Discord, salon caché, archivage et signalement
  marchent déjà et sont exactement ce qu'il faut.
- **Toujours permanent** : pas de date, pas de durée, pas de sessions.
- **Champs masqués dans le formulaire** pour un salon : système, VTT, nombre de joueur·euses,
  sélection, expérience, création des personnages, classification, ambiance, et l'interrupteur
  Permanent (implicite). Restent : nom, description (libellé « Description du salon »), infos
  complémentaires, image, avertissement (tout public / 16+ / 18+), thèmes sensibles, salon vocal.
- **Pas de système de jeu** : `system_id` devient facultatif en base. Pour les autres types, le
  système reste obligatoire (vérifié côté serveur, pas seulement dans le navigateur).
- **Pas de limite de membres** : `party_size` est fixé en interne à 10 000 (constante
  `SALON_PARTY_SIZE`), qui n'est jamais affiché. Le salon ne se ferme donc jamais
  automatiquement. On affiche « N membre(s) » à la place de « N/4 Joueur·euses », sans places
  vides.
- **Fiche** : le bouton s'appelle « Rejoindre le salon ». Les blocs Classification, Ambiance,
  Sessions, les badges expérience et personnages, et le bouton « Ajouter une session » sont
  masqués.
- **Couleur** : orange (`#FD7E14`) pour la carte, le rôle Discord et l'embed. Icône
  `bi-chat-dots`.
- **Rôle Discord** : nommé `Membre_<slug>` au lieu de `PJ_<slug>`.
- **Message épinglé dans le salon** : texte adapté (pas de « partie », pas de rappel sur les
  sessions jouées).
- **Annonce Discord** : champs « Créé par », « Type : Salon », « Avertissement » et le lien
  d'inscription. Pas de système, de date ni de durée.
- **Badges** : un salon archivé ne distribue aucun badge (comme les jeux vidéo).
- **Recherche** : nouveau filtre « Salons », coché par défaut comme les autres types.
- **Catégorie Discord** : si aucune catégorie de type `salon` n'est enregistrée dans l'admin
  (Admin → Channel, type « Salon »), les salons sont créés dans la catégorie One Shot la moins
  remplie. Pour les ranger à part, il suffit de créer la catégorie sur Discord et d'enregistrer
  son ID dans l'admin avec le type « Salon ». Le même repli s'applique aux jeux vidéo, qui
  plantaient jusqu'ici à la publication s'il n'y avait pas de catégorie « Jeu vidéo ».
- **Statistiques mensuelles** : un salon n'a pas de session, il n'y apparaît donc pas. Si un MJ
  en ajoute une quand même, le salon est rangé sous « Salon » au lieu de faire planter la page.

## 4. Base de données

- Migration `b4e1c7d2a9f3_add_salon_type_and_permanent_games` :
  - ajoute `salon` à `game_type_enum` ;
  - ajoute la colonne `permanent` ;
  - rend `date`, `session_length` et `system_id` facultatifs.
- Elle est appliquée automatiquement au démarrage du conteneur (`flask db upgrade` dans
  `entrypoint.sh`). Montée, descente puis remontée testées sur une base vierge.

## 5. Tests

- Nouveaux tests : service (parties permanentes, salons, repli de catégorie), embeds Discord,
  pages (création, fiche, liste, formulaire d'édition).
- Tests corrigés au passage parce qu'ils étaient restés en retard sur des changements précédents
  (10 échecs avant ce travail) : contexte Flask manquant pour l'embed « Tout est prêt », types par
  défaut de la recherche, test du dépôt Channel devenu obsolète depuis que `type` est une chaîne
  de caractères.
- Résultat : 609 tests unitaires et 87 tests de vues passent. Les 2 tests `test_e2e` échouent
  comme avant : ils appellent le vrai Discord.

## 6. Hors périmètre, repéré en passant

- ~~`website/services/discord.py:371` utilise `logger` sans l'importer (erreur flake8 F821, qui
  existait déjà).~~ Corrigé ensuite (commit `fix(discord)`), avec un test.

## 7. Une seule catégorie Discord pour les jeux de rôle (2026-10-02)

- La catégorie « Oneshots » est supprimée sur Discord. One Shots et Campagnes vont tous dans la
  catégorie `1501269649856139406`.
- Dans la table `channel`, l'ID est la clé primaire : une catégorie ne peut être enregistrée
  qu'avec **un seul type**. Plutôt que de changer le schéma, `ChannelService.get_category` utilise
  une table de repli (`CATEGORY_FALLBACKS`) :
  - oneshot → campaign, campaign → oneshot (les deux types de JDR partagent leurs catégories) ;
  - videogame et salon → oneshot, puis campaign.
- Côté admin, il suffit d'avoir une ligne `1501269649856139406` avec le type « Campagne » et de
  supprimer la ligne de l'ancienne catégorie Oneshots.
- Tant qu'aucune catégorie « Jeu vidéo » ou « Salon » n'est enregistrée, les jeux vidéo et les
  salons sont eux aussi créés dans cette catégorie JDR.
