"""
rps_game.py — Logique du jeu Pierre Feuille Ciseaux
====================================================
Arbitre : détermine qui gagne, gère le score.

Utilisation comme module :
    from rps_game import RPSGame
    game = RPSGame()
    result = game.play_round('pierre', 'ciseaux')
    print(result)  # {'result': 'victoire', 'player': 'pierre', 'robot': 'ciseaux'}
"""

import random

GESTES = ["pierre", "feuille", "ciseaux"]

# pierre bat ciseaux, ciseaux bat feuille, feuille bat pierre
BEATS = {
    "pierre":  "ciseaux",
    "ciseaux": "feuille",
    "feuille": "pierre",
}

EMOJI = {
    "pierre":  "✊",
    "feuille": "✋",
    "ciseaux": "✌️",
}

class RPSGame:
    def __init__(self):
        self.score_robot  = 0
        self.score_player = 0
        self.history      = []

    def robot_choice(self):
        """Le robot choisit aléatoirement."""
        return random.choice(GESTES)

    def who_wins(self, player, robot):
        """
        Retourne 'victoire', 'defaite' ou 'egalite'.
        Du point de vue du joueur humain.
        """
        if player == robot:
            return "egalite"
        if BEATS[player] == robot:
            return "victoire"
        return "defaite"

    def play_round(self, player_gesture, robot_gesture=None):
        """
        Joue un round.
        player_gesture : geste détecté de l'adversaire
        robot_gesture  : si None, le robot choisit aléatoirement
        Retourne un dict avec le résultat.
        """
        if robot_gesture is None:
            robot_gesture = self.robot_choice()

        if player_gesture not in GESTES:
            return {"result": "rate", "player": None,
                    "robot": robot_gesture, "message": "Geste non reconnu"}

        result = self.who_wins(player_gesture, robot_gesture)

        if result == "victoire":  self.score_player += 1
        elif result == "defaite": self.score_robot  += 1

        round_data = {
            "result":  result,
            "player":  player_gesture,
            "robot":   robot_gesture,
            "score_player": self.score_player,
            "score_robot":  self.score_robot,
            "message": self._message(result, player_gesture, robot_gesture),
        }
        self.history.append(round_data)
        return round_data

    def _message(self, result, player, robot):
        p = f"{EMOJI[player]} {player}"
        r = f"{EMOJI[robot]} {robot}"
        if result == "victoire":
            return f"{p} bat {r} — Vous gagnez !"
        elif result == "defaite":
            return f"{r} bat {p} — Robot gagne !"
        else:
            return f"{p} = {r} — Égalité !"

    def reset_score(self):
        self.score_robot  = 0
        self.score_player = 0
        self.history      = []

    def print_score(self):
        print(f"  Score — Joueur : {self.score_player} | Robot : {self.score_robot}")

# ── Test standalone ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    game = RPSGame()
    print("=== Test logique RPS ===\n")
    for player, robot in [
        ("pierre",  "ciseaux"),
        ("feuille", "pierre"),
        ("ciseaux", "ciseaux"),
        ("pierre",  "feuille"),
    ]:
        r = game.play_round(player, robot)
        print(f"  {r['message']}")
    print()
    game.print_score()
