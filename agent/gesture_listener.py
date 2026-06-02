"""
agent/gesture_listener.py

Écoute les gestes envoyés par gesture_multi.py sur le port 9998.
Format reçu : "gesture:<nom>"   ex: "gesture:wave"

Ce module est démarré en thread par session.py ou events.py.
Il expose :
  - get_last_gesture()       → str ou None
  - get_gesture_context()    → str à injecter dans le system prompt

Intégration dans agent/session.py :
    import agent.gesture_listener as gesture_listener
    # dans run() ou connect() :
    gesture_listener.start()

Intégration dans le system prompt (agent/session.py, juste avant l'envoi) :
    ctx = gesture_listener.get_gesture_context()
    if ctx:
        # Ajouter ctx dans session.update instructions
"""

import socket
import threading
import time

# ── Config ────────────────────────────────────────────────────────────────────
AGENT_GESTURE_PORT = 9998
GESTURE_TIMEOUT    = 10.0   # secondes avant que le geste soit considéré "expiré"

# ── État ──────────────────────────────────────────────────────────────────────
_lock         = threading.Lock()
_last_gesture = None   # str : "wave", "hug", "handshake", "bigwave"
_last_time    = 0.0
_started      = False

# Mapping geste → description naturelle pour le contexte
GESTURE_LABELS = {
    "wave":     "La personne en face de toi vient de faire un signe de la main (wave).",
    "hug":      "La personne en face de toi a les bras écartés en T (position câlin).",
    "handshake": "La personne en face de toi tend la main pour te serrer la main.",
    "bigwave":  "ALERTE : une chute vient d'être détectée devant toi.",
}


def _listen_loop():
    global _last_gesture, _last_time

    while True:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(('127.0.0.1', AGENT_GESTURE_PORT))
            srv.listen(5)
            print(f"[GestureListener] En écoute sur port {AGENT_GESTURE_PORT}")

            while True:
                try:
                    conn, _ = srv.accept()
                    with conn:
                        data = conn.recv(256).decode().strip()
                    if data.startswith("gesture:"):
                        gesture = data[len("gesture:"):]
                        with _lock:
                            _last_gesture = gesture
                            _last_time    = time.time()
                        print(f"[GestureListener] Geste reçu : {gesture}")
                except Exception as e:
                    print(f"[GestureListener] Erreur connexion : {e}")

        except Exception as e:
            print(f"[GestureListener] Erreur serveur : {e}, retry dans 3s")
            time.sleep(3)


def start():
    """Démarre le listener en thread daemon. Idempotent."""
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_listen_loop, daemon=True).start()


def get_last_gesture() -> str | None:
    """Retourne le dernier geste détecté s'il date de moins de GESTURE_TIMEOUT s."""
    with _lock:
        if _last_gesture and (time.time() - _last_time) < GESTURE_TIMEOUT:
            return _last_gesture
    return None


def get_gesture_context() -> str:
    """
    Retourne une phrase décrivant le geste récent, ou "" si rien.
    À injecter dans les instructions de session OpenAI Realtime.
    """
    g = get_last_gesture()
    if g:
        return GESTURE_LABELS.get(g, f"Geste détecté : {g}.")
    return ""


def clear():
    """Efface le geste courant (après que l'agent y ait réagi)."""
    global _last_gesture, _last_time
    with _lock:
        _last_gesture = None
        _last_time    = 0.0
