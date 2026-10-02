"""Definitions of QuestMaster's Discord slash commands."""

USER_OPTION = 6
MAX_PLAYERS = 9

DISCORD_COMMANDS = [
    {
        "name": "steam-statut",
        "description": "Vérifier si ton compte Steam est relié à QuestMaster",
        "type": 1,
    },
    {
        "name": "jeux-en-commun",
        "description": "Trouver les jeux Steam que vous possédez tous",
        "type": 1,
        "options": [
            {
                "name": f"joueur{i}",
                "description": "Un joueur avec qui comparer ta bibliothèque Steam",
                "type": USER_OPTION,
                "required": i == 1,
            }
            for i in range(1, MAX_PLAYERS + 1)
        ],
    },
]
