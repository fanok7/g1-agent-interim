"""
rps_controller.py — Chef d'orchestre Pierre Feuille Ciseaux G1
==============================================================
Relie vision + main + logique + réaction robot.

Pipeline :
    1. Robot choisit son coup (aléatoire)
    2. Robot joue le coup avec sa main
    3. Caméra détecte le geste de l'adversaire
    4. Arbitre détermine le gagnant
    5. Robot réagit (wave=victoire, reject=défaite, clap=égalité)

Lancement sur la Jetson :
    python3.8 rps_controller.py

    # Tests PC (sans mains) :
    python3.8 rps_controller.py --no-hands --source /dev/video9
"""

import time
import socket
import threading
import argparse

from rps_game   import RPSGame
from rps_vision import RPSVision
from rps_hand   import RPSHand

# ── Config ───────────────────────────────────────────────────────────────────
ROBOT_SOCKET   = ("127.0.0.1", 9999)   # robot_controller.py
DETECT_TIMEOUT = 6.0                    # secondes pour détecter le geste
PLAY_DURATION  = 2.0                    # secondes pour jouer le coup main

# Réactions robot selon résultat
REACTIONS = {
    "victoire": "wave",
    "defaite":  "reject",
    "egalite":  "clap",
    "rate":     None,
}

# ── Envoi commande robot ──────────────────────────────────────────────────────
def send_robot_action(action):
    if action is None: return
    try:
        s = socket.socket()
        s.connect(ROBOT_SOCKET)
        s.sendall(f"{action}\n".encode())
        s.close()
        print(f"[ROBOT] Action : {action}")
    except Exception as e:
        print(f"[WARN] Socket robot : {e}")

# ── Contrôleur principal ──────────────────────────────────────────────────────
class RPSController:
    def __init__(self, model_path, source, hand_side, no_hands=False):
        self.game     = RPSGame()
        self.vision   = RPSVision(model_path, source)
        self.hand     = RPSHand(side=hand_side) if not no_hands else None
        self.no_hands = no_hands

    def start(self):
        self.vision.start()
        print("\n══════════════════════════════════════")
        print("  PIERRE FEUILLE CISEAUX — G1")
        print("══════════════════════════════════════")
        print("  Entrée → jouer un round")
        print("  s     → voir le score")
        print("  r     → reset score")
        print("  q     → quitter")
        print("══════════════════════════════════════\n")

    def play_round(self):
        print("\n─── Nouveau round ───")

        # 1. Robot choisit son coup
        robot_gesture = self.game.robot_choice()
        print(f"  Robot choisit : {robot_gesture}")

        # 2. Robot joue avec sa main
        if self.hand:
            print(f"  Main robot → {robot_gesture}")
            threading.Thread(target=self.hand.play,
                             args=(robot_gesture,), daemon=True).start()
            time.sleep(PLAY_DURATION)

        # 3. Détecter le geste de l'adversaire
        print(f"  Détection geste adversaire ({DETECT_TIMEOUT}s)...")
        player_gesture = self.vision.capture_gesture(timeout=DETECT_TIMEOUT)

        if player_gesture:
            print(f"  Adversaire : {player_gesture}")
        else:
            print("  Aucun geste détecté")

        # 4. Arbitre
        result = self.game.play_round(player_gesture, robot_gesture)
        print(f"\n  {result['message']}")
        self.game.print_score()

        # 5. Réaction robot
        action = REACTIONS.get(result["result"])
        if action:
            threading.Thread(target=send_robot_action,
                             args=(action,), daemon=True).start()

        # 6. Ouvrir la main après le round
        if self.hand:
            time.sleep(2.0)
            self.hand.open()

        return result

    def run(self):
        self.start()
        try:
            while True:
                cmd = input("\n> ").strip().lower()
                if cmd == "q":
                    break
                elif cmd == "s":
                    self.game.print_score()
                elif cmd == "r":
                    self.game.reset_score()
                    print("  Score remis à zéro")
                elif cmd == "":
                    self.play_round()
                else:
                    print(f"  Commande inconnue : '{cmd}'")
        except KeyboardInterrupt:
            print("\n[INFO] Arrêt")
        finally:
            self.vision.stop()
            if self.hand:
                self.hand.disconnect()

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model",     default="yolo11-rps-detection.pt")
    ap.add_argument("--source",    default="0",
                    help="0=D435i Jetson  /dev/video9=PC test")
    ap.add_argument("--hand",      default="r",
                    help="r=droite  l=gauche")
    ap.add_argument("--no-hands",  action="store_true",
                    help="Désactiver les mains (test vision seule)")
    args = ap.parse_args()

    ctrl = RPSController(
        model_path=args.model,
        source=args.source,
        hand_side=args.hand,
        no_hands=args.no_hands,
    )
    ctrl.run()
