# Jeux Steam en commun — conception

Date : 2026-10-02 · Statut : validée oralement, à relire

## Objectif

Depuis Discord, un membre tape `/jeux-en-commun @Alice @Bob` et le bot QuestMaster répond avec
la liste des jeux que **tous** possèdent dans leur bibliothèque Steam. Le but : savoir à quoi on
peut jouer ensemble.

### Ce que Séb a demandé
- Trouver les **jeux en commun** (pas remplir une annonce, pas suggérer un jeu au hasard).
- Entre des **membres choisis librement**, pas forcément inscrits à une annonce.
- Lancé par une **commande Discord**.
- Compte Steam relié **via les connexions Discord** du membre.

### Décisions prises pendant la conception
- La personne qui lance la commande est **toujours incluse** dans le groupe.
- Un membre sans Steam relié, ou avec un profil privé, est **exclu du calcul**, et le message le
  dit.
- La commande arrive dans l'application Flask existante par **HTTP** (Interactions Endpoint de
  Discord). Pas de bot connecté en permanence, pas de nouveau conteneur.

### Hors périmètre
- Lier Steam autrement que par Discord (bouton Steam OpenID, commande `/steam <url>`).
- Page « jeux en commun » sur le site.
- Groupe déduit d'une annonce ou d'un salon vocal.
- Suggestion de jeu, filtres par genre ou multijoueur. Steam ne dit pas de manière fiable si un
  jeu est multijoueur : la liste contient donc aussi des jeux solo.

## Expérience utilisateur

### Relier Steam
1. Le membre relie Steam dans Discord : Paramètres → Connexions → Steam. Il n'a rien à faire si
   c'est déjà fait.
2. Il se connecte (ou se reconnecte) au site QuestMaster. Discord lui demande en plus
   l'autorisation « Accéder à vos connexions ».
3. QuestMaster enregistre son identifiant Steam (SteamID64).

Les membres déjà connectés doivent se reconnecter une fois : l'ancienne autorisation ne couvrait
pas les connexions.

Pour que ses jeux soient lisibles, le membre doit aussi mettre dans Steam : Profil → Modifier le
profil → Confidentialité → **Détails des jeux : Public**.

### `/steam-statut`
Réponse visible seulement par l'auteur (message éphémère), dans l'un de ces cas :
- **Steam non relié** : comment relier, puis se reconnecter au site (avec le lien de connexion).
- **Relié, profil privé** : comment passer les détails de jeu en Public.
- **Relié, profil lisible** : « N jeux trouvés dans ta bibliothèque. »
- **Steam ne répond pas** : « réessaie plus tard ».

### `/jeux-en-commun joueur1 [joueur2 … joueur9]`
- Options de type *utilisateur* Discord : `joueur1` obligatoire, `joueur2` à `joueur9`
  facultatives. L'auteur s'ajoute automatiquement. Les doublons sont ignorés, et un groupe réduit
  à l'auteur seul est refusé avec un message clair.
- Réponse publique dans le salon :
  1. tout de suite : « Je cherche les jeux en commun… » (réponse différée de Discord) ;
  2. puis le résultat, qui remplace ce message.
- **Résultat (embed)** :
  - Titre : « 🎮 Jeux en commun — Alice, Bob, Carole ».
  - Liste : jusqu'à **25 jeux**, triés par **temps de jeu cumulé du groupe** (le plus joué
    d'abord). Chaque nom renvoie vers sa page `https://store.steampowered.com/app/<appid>`.
  - Ligne de total si la liste est coupée : « 47 jeux en commun, voici les 25 plus joués. »
  - Pied du message, si besoin : les exclus et la raison (« Bob : Steam non relié », « Carole :
    profil Steam privé »). Pour un membre qui n'a jamais utilisé le site, on indique « Steam non
    relié ».
- **Cas limites** :
  - Moins de 2 membres lisibles : pas de calcul, message expliquant qui est exclu et pourquoi.
  - 0 jeu en commun : « Aucun jeu en commun entre … ».
  - Steam indisponible pour un membre : il est exclu avec la raison « Steam n'a pas répondu ».

## Architecture

Le découpage suit les couches du projet (models → repositories → services → views, plus client).

### Modèle (`website/models/user.py`)
- Nouvelle colonne `steam_id = db.Column(db.String(), nullable=True)`, sans index : le groupe fait
  au plus 10 personnes.
- Migration Alembic : ajout de la colonne.

### Liaison à la connexion (`website/views/auth.py`, `website/services/user.py`)
- `login()` : `scope=["identify", "connections"]`.
- `callback()` : après `get_or_create`, appel à `UserService.link_steam_from_connections(user,
  connections)` avec `connections = discord.fetch_connections()`. L'appel est entouré d'un
  `try/except` : la moindre erreur est journalisée en avertissement et **n'empêche jamais la
  connexion**.
- `UserService.link_steam_from_connections(user, connections)` :
  - prend la première connexion de `type == "steam"` et enregistre son `id` dans `user.steam_id`
    (commit seulement si la valeur change) ;
  - ne fait rien s'il n'y a pas de connexion Steam (on ne supprime pas un `steam_id` existant :
    l'utilisateur a pu refuser la permission « connexions » cette fois-ci).

### Client Steam (`website/client/steam.py`, nouveau)
- Classe `Steam(api_key)`, sur le modèle de `website/client/discord.py` (requests + tenacity).
- `get_owned_games(steam_id) -> list[dict] | None` :
  - appel `GET https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/` avec `key`,
    `steamid`, `include_appinfo=1`, `include_played_free_games=1`, `format=json` ;
  - renvoie une liste de `{"appid": int, "name": str, "playtime_forever": int}` (minutes) ;
  - renvoie `None` quand la réponse ne contient pas de clé `games` (profil ou détails de jeu
    privés : Steam renvoie alors `{"response": {}}`). Une bibliothèque publique et vide renvoie
    `[]` ;
  - nouvelles tentatives sur les erreurs réseau et les codes 429/5xx (3 essais, attente
    exponentielle), puis levée de `SteamAPIError` (nouvelle exception, à côté de
    `DiscordAPIError`) ;
  - délai d'attente de 10 s par requête.

### Service Steam (`website/services/steam.py`, nouveau)
- `SteamService(client=None, cache=None)`, avec injection pour les tests.
- `get_library(user) -> LibraryResult` :
  - `status` parmi `"ok" | "not_linked" | "private" | "unavailable"`, plus `games` ;
  - cache Redis via Flask-Caching, clé `steam:library:<steam_id>`, durée **6 h** pour `ok` et
    `private`. `unavailable` n'est jamais mis en cache.
- `common_games(users) -> CommonGamesResult` :
  - récupère chaque bibliothèque avec `get_library` ;
  - `included` : utilisateurs au statut `ok` ; `excluded` : couples (utilisateur, statut) ;
  - si moins de 2 inclus : `games = []` et `too_few = True` ;
  - sinon, intersection sur `appid`. Score = somme des `playtime_forever` du groupe ; tri par
    score décroissant, puis par nom (ordre stable) ;
  - renvoie `games` (liste complète triée) et `total`.
- Les structures de résultat sont de simples `dataclass` définies dans le module.

### Commandes Discord (`website/views/interactions.py`, nouveau blueprint `interactions_bp`)
- Route `POST /discord/interactions/`, avec la barre oblique finale (cf. le piège des
  redirections derrière le proxy), exemptée de CSRF (`csrf.exempt`).
- **Vérification de signature** obligatoire avant tout traitement : en-têtes
  `X-Signature-Ed25519` et `X-Signature-Timestamp`, message `timestamp + corps brut`, clé
  `DISCORD_PUBLIC_KEY`, via `nacl.signing.VerifyKey`. Échec → `401`. Fonction isolée
  `verify_discord_signature(public_key, signature, timestamp, body) -> bool` dans
  `website/utils/discord_signature.py`.
- Type `1` (PING) → `{"type": 1}`. Discord l'exige pour valider l'adresse.
- Type `2` (commande) → routage par `data.name` :
  - `steam-statut` : réponse immédiate `type 4`, `flags: 64` (éphémère) ;
  - `jeux-en-commun` : réponse immédiate `type 5` (différée, publique), puis lancement d'un
    `threading.Thread(daemon=True)` qui s'exécute dans un contexte d'application
    (`app.app_context()`), calcule le résultat et modifie la réponse via
    `PATCH /webhooks/<application_id>/<interaction_token>/messages/@original`. Le jeton
    d'interaction suffit, sans jeton de bot ; il est valable 15 minutes.
- Les utilisateurs mentionnés sont lus dans `data.options` (identifiants) et
  `data.resolved.users` (pseudos d'affichage), puis chargés avec `UserService` ; un membre
  inconnu de QuestMaster est traité comme « Steam non relié ».
- Construction des messages dans `website/utils/steam_embeds.py` (fonctions pures, testables),
  sur le modèle de `game_embeds.py`.
- Toute erreur dans le fil d'exécution est attrapée : la réponse est remplacée par « Une erreur
  est survenue, réessaie plus tard. » et l'erreur est journalisée.

### Client Discord (`website/client/discord.py`)
- Nouvelles méthodes :
  - `edit_interaction_response(application_id, token, payload)` : le PATCH ci-dessus, sans
    en-tête d'autorisation du bot ;
  - `register_guild_commands(application_id, commands)` : `PUT
    /applications/<id>/guilds/<guild_id>/commands`. Commandes **de serveur** plutôt que
    globales : elles apparaissent tout de suite et seulement sur le serveur du club.

### Enregistrement des commandes (`website/extensions.py`, commande CLI)
- `flask register-discord-commands` : définit `steam-statut` et `jeux-en-commun` (1 option
  obligatoire et 8 facultatives de type USER = 6, noms `joueur1` à `joueur9`) et les enregistre.
  À lancer une fois après le déploiement, et à chaque modification des commandes. La commande est
  idempotente : un PUT remplace la liste.

### Configuration (`config/settings.py`, variables Portainer)
- `STEAM_API_KEY` : clé d'API Steam, à créer sur https://steamcommunity.com/dev/apikey.
- `DISCORD_PUBLIC_KEY` : clé publique de l'application Discord (portail développeur → General
  Information).
- `DISCORD_CLIENT_ID` sert déjà d'identifiant d'application ; on le réutilise.
- Si `DISCORD_PUBLIC_KEY` est absente, la route répond `503` et journalise une erreur, plutôt que
  d'accepter des requêtes sans les vérifier.
- Dépendance ajoutée : `PyNaCl` (version figée).

### Réglage Discord (manuel, une fois)
Dans le portail développeur, application QuestMaster → General Information → **Interactions
Endpoint URL** : `https://questmaster.sebgal.net/discord/interactions/`. Discord envoie un PING
signé pour valider l'adresse : le déploiement doit donc être fait avant ce réglage.

## Erreurs et sécurité
- Signature invalide ou absente : `401`, sans traitement.
- Le corps brut est lu avec `request.get_data()` **avant** tout décodage JSON (la signature porte
  sur les octets exacts).
- La clé Steam n'apparaît jamais dans les journaux ni dans les messages. Les URL d'appel Steam
  sont journalisées sans le paramètre `key`.
- Les SteamID ne sont jamais affichés dans Discord, seulement des pseudos.
- Appels Steam : au plus 10 par commande, et beaucoup moins grâce au cache. Steam autorise
  environ 100 000 appels par jour et par clé.

## Tests
- `tests/utils/test_discord_signature.py` : signature valide acceptée ; corps, horodatage ou
  signature modifiés refusés ; clé générée dans le test avec `nacl.signing.SigningKey.generate()`.
- `tests/client/test_steam_client.py` : requests simulé ; liste de jeux, profil privé (`None`),
  bibliothèque vide (`[]`), 5xx qui se rétablit au deuxième essai, échec définitif →
  `SteamAPIError`.
- `tests/services/test_steam_service.py` : intersection, tri par temps de jeu cumulé puis par
  nom, exclusions (`not_linked`, `private`, `unavailable`), `too_few`, cache utilisé au deuxième
  appel, `unavailable` jamais mis en cache.
- `tests/services/test_user_service.py` : `link_steam_from_connections` (Steam trouvé, absent,
  valeur inchangée).
- `tests/views/test_interactions.py` : PING ; signature invalide → 401 ; `steam-statut` pour
  chaque statut ; `jeux-en-commun` → réponse de type 5, puis le fil appelle
  `edit_interaction_response` avec l'embed attendu (fil exécuté de façon synchrone dans les
  tests).
- `tests/views/test_auth.py` : la connexion réussit même si `fetch_connections` lève une
  exception.
- `tests/utils/test_steam_embeds.py` : titre, liste coupée à 25 avec total, pied avec les exclus,
  messages des cas limites.

## Mise en service
1. Créer la clé d'API Steam et copier la clé publique Discord.
2. Ajouter `STEAM_API_KEY` et `DISCORD_PUBLIC_KEY` dans Portainer, puis « Pull and redeploy » (la
   migration `steam_id` s'applique au démarrage).
3. Dans le conteneur : `flask register-discord-commands`.
4. Portail Discord : renseigner l'Interactions Endpoint URL.
5. Chaque membre : Steam relié dans Discord, détails des jeux en Public, une reconnexion au site.
