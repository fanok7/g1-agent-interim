"""
launch.py — Superviseur du G1.
Seul programme à ouvrir le port série vers l'ESP32.
Pilote la bouche (émotions) et lance/arrête main.py et les autres scripts.
Reçoit les émotions de main.py via socket local (127.0.0.1:9876).
"""
import serial
import json
import time
import subprocess
import threading
import os
import socket

PORT = "/dev/ttyUSB0"
BAUD = 115200
SOCKET_HOST = "127.0.0.1"
SOCKET_PORT = 9876

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPTS_AUTORISES = {
    "main": ["python3.8", os.path.join(BASE_DIR, "main.py")],
    "vision": ["python3.8", os.path.join(BASE_DIR, "vision", "vision_server.py")],
    "damping":  ["python3.8", os.path.join(BASE_DIR, "robot", "mode_damping.py")],
    "standing": ["python3.8", os.path.join(BASE_DIR, "robot", "mode_standing.py")],
    "regular":  ["python3.8", os.path.join(BASE_DIR, "robot", "mode_regular.py")],
    "seating": ["python3.8", os.path.join(BASE_DIR, "robot", "mode_seating.py")],
}

_processus = {}
_ser = None
_lock = threading.Lock()


# ───────────── Communication ESP32 (port série) ─────────────

def send_emotion(emotion: str):
    if _ser is None:
        return
    try:
        with _lock:
            payload = json.dumps({"cmd": "emotion", "value": emotion}) + "\n"
            _ser.write(payload.encode())
    except Exception as e:
        print(f"[Launch] Erreur envoi emotion : {e}")


def _repondre(payload: dict):
    if _ser is None:
        return
    try:
        with _lock:
            _ser.write((json.dumps(payload) + "\n").encode())
    except Exception as e:
        print(f"[Launch] Erreur reponse : {e}")


# ───────────── Gestion des scripts (run/stop/status) ─────────────

def lancer(nom):
    if nom not in SCRIPTS_AUTORISES:
        return {"ok": False, "error": "script inconnu"}
    if nom in _processus and _processus[nom].poll() is None:
        return {"ok": False, "error": "deja lance"}
    proc = subprocess.Popen(SCRIPTS_AUTORISES[nom])
    _processus[nom] = proc
    print(f"[Launch] Lance {nom} (PID {proc.pid})")
    return {"ok": True, "pid": proc.pid, "script": nom}


def arreter(nom):
    proc = _processus.get(nom)
    if proc and proc.poll() is None:
        proc.terminate()
        print(f"[Launch] Arrete {nom}")
        return {"ok": True, "script": nom}
    return {"ok": False, "error": "pas en cours"}


def statut():
    return {nom: (p.poll() is None) for nom, p in _processus.items()}


# ───────────── Boucle ESP32 → Jetson ─────────────

def _ecoute_esp32():
    global _ser
    while True:
        if _ser is None or not _ser.in_waiting:
            time.sleep(0.05)
            continue
        try:
            with _lock:
                ligne = _ser.readline().decode(errors="ignore").strip()
            if not ligne:
                continue
            data = json.loads(ligne)
            event = data.get("event")

            if event == "run":
                rep = lancer(data.get("script"))
            elif event == "stop":
                rep = arreter(data.get("script"))
            elif event == "status":
                rep = {"ok": True, "statuts": statut()}
            else:
                continue

            _repondre(rep)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        except Exception as e:
            print(f"[Launch] Erreur lecture ESP32 : {e}")


# ───────────── Serveur socket : main.py → launch.py ─────────────

def _serveur_socket():
    """Écoute les émotions envoyées par main.py (ou tout autre script lancé)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((SOCKET_HOST, SOCKET_PORT))
    srv.listen(5)
    print(f"[Launch] Socket emotions en ecoute sur {SOCKET_HOST}:{SOCKET_PORT}")

    while True:
        conn, _ = srv.accept()
        threading.Thread(target=_gerer_client, args=(conn,), daemon=True).start()


def _gerer_client(conn):
    with conn:
        try:
            data = conn.recv(1024).decode(errors="ignore").strip()
            if not data:
                return
            payload = json.loads(data)
            emotion = payload.get("emotion")
            if emotion:
                send_emotion(emotion)
                conn.sendall(b'{"ok": true}')
        except Exception as e:
            print(f"[Launch] Erreur socket client : {e}")
            try:
                conn.sendall(b'{"ok": false}')
            except Exception:
                pass


# ───────────── Main ─────────────

def main():
    global _ser
    try:
        _ser = serial.Serial(PORT, BAUD, timeout=0.1)
        print(f"[Launch] Connecte sur {PORT}")
        time.sleep(2)
    except Exception as e:
        print(f"[Launch] ESP32 non disponible : {e}")
        _ser = None

    threading.Thread(target=_serveur_socket, daemon=True).start()

    print("[Launch] Pret. En attente de commandes ESP32 et emotions main.py...")
    _ecoute_esp32()


if __name__ == "__main__":
    main()