"""
tools/vision_tool.py - Tool "voir" pour l'agent G1

Se connecte au vision_server.py (socket 127.0.0.1:9997) et expose deux fonctions :
  - get_vision_context() → résumé textuel de ce que le robot voit (pour le system prompt)
  - Le tool "voir" appelable par l'agent via Realtime API

Enregistrement automatique dans le registry à l'import (comme gesture_tool.py).
"""

import json
import socket
import threading
import time

# ── État partagé ─────────────────────────────────────────────────────────────
_lock         = threading.Lock()
_last_objects = []     # liste de dicts {"label","conf","dist","x","y"}
_connected    = False
VISION_PORT   = 9997

# ── Connexion background ──────────────────────────────────────────────────────

def _connect_loop():
    global _connected, _last_objects

    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(('127.0.0.1', VISION_PORT))
            sock.settimeout(None)
            _connected = True
            print(f"[VisionTool] Connecté au vision_server (port {VISION_PORT})")

            buf = ""
            while True:
                chunk = sock.recv(4096).decode(errors='ignore')
                if not chunk:
                    break
                buf += chunk
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            with _lock:
                                _last_objects = data.get("objects", [])
                        except Exception:
                            pass

        except Exception as e:
            _connected = False
            print(f"[VisionTool] vision_server non dispo, retry dans 3s ({e})")
            time.sleep(3)


threading.Thread(target=_connect_loop, daemon=True).start()

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_vision_context() -> str:
    """
    Renvoie un résumé textuel de ce que le robot voit.
    Utilisé pour enrichir le contexte de chaque échange.
    Exemple : "Devant toi : 1 personne à 1.2m, 1 chaise à 2.5m."
    """
    with _lock:
        objects = list(_last_objects)

    if not objects:
        if not _connected:
            return ""   # vision_server pas lancé → on n'injecte rien
        return "Rien de détecté devant toi."

    parts = []
    for o in objects:
        label = o.get("label", "objet")
        dist  = o.get("dist", -1)
        if dist and dist > 0:
            parts.append(f"{label} à {dist:.1f}m")
        else:
            parts.append(label)

    return "Devant toi : " + ", ".join(parts) + "."


def get_objects_list():
    """Retourne la liste brute des objets détectés."""
    with _lock:
        return list(_last_objects)


# ── Définition du tool Realtime OpenAI ───────────────────────────────────────

TOOL_DEFINITION = {
    "type": "function",
    "name": "voir",
    "description": (
        "Regarde ce qu'il y a devant toi grâce à ta caméra. "
        "Retourne la liste des objets/personnes détectés et leur distance. "
        "Appelle ce tool quand on te demande ce que tu vois, "
        "qui est devant toi, ou si tu as besoin d'une info visuelle."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def handle_voir(_args: dict) -> str:
    """Exécute le tool 'voir' et retourne le résultat en texte."""
    with _lock:
        objects = list(_last_objects)

    if not _connected:
        return "Ma caméra n'est pas disponible pour l'instant."

    if not objects:
        return "Je ne détecte rien de particulier devant moi."

    lines = []
    for o in objects:
        label = o.get("label", "objet")
        conf  = o.get("conf", 0)
        dist  = o.get("dist", -1)
        if dist and dist > 0:
            lines.append(f"- {label} (confiance {int(conf*100)}%) à {dist:.1f} mètre(s)")
        else:
            lines.append(f"- {label} (confiance {int(conf*100)}%)")

    return "Voici ce que je vois :\n" + "\n".join(lines)


# ── Enregistrement dans le registry de l'agent ───────────────────────────────
# Même pattern que gesture_tool.py — l'import de ce fichier suffit.

try:
    from agent.registry import register_tool
    register_tool(
        definition=TOOL_DEFINITION,
        handler=handle_voir,
    )
    print("[VisionTool] Tool 'voir' enregistré dans le registry agent.")
except ImportError:
    # Standalone (test direct)
    print("[VisionTool] registry non disponible (mode standalone)")
