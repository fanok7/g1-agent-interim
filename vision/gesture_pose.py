#!/usr/bin/env python3
"""
vision/gesture_pose.py - A lancer avec miniconda python3 sur le ROBOT
Détecte 4 gestes via YOLO-pose et exécute les actions via g1-agent-interim.

Gestes → Actions :
    main levée          → tope_la
    bras en T           → calin
    main tendue caméra  → serrer_main
    chute détectée      → grande_salutation

Lancement :
    /home/unitree/miniconda3/bin/python3 /home/unitree/g1_agent_interim/vision/gesture_pose.py

Accès navigateur :
    http://192.168.123.164:8082
"""

import os
import sys
import time
import threading
import cv2
from flask import Flask, Response
from ultralytics import YOLO

GESTURE_CMD_FILE = "/tmp/gesture_cmd"   # main.py (python3.8) surveille ce fichier


def execute_gesture(geste: str) -> None:
    """Écrit le geste dans /tmp/gesture_cmd — main.py l'exécute côté SDK."""
    try:
        with open(GESTURE_CMD_FILE, 'w') as f:
            f.write(geste)
    except Exception as e:
        print(f"[GESTURE] Impossible d'écrire le geste '{geste}' : {e}", flush=True)

# ── Config ────────────────────────────────────────────────────────────────────
PORT       = 8082    # 8080 = vision_server, 8081 = face_id
WIDTH      = 640
HEIGHT     = 480
QUALITY    = 80
CONFIDENCE = 0.5
YOLO_SKIP  = 10
COOLDOWN_S = 5.0
KP_MIN_CONF = 0.5

VISION_STREAM    = "http://127.0.0.1:8080/stream"  # flux MJPEG de vision_server
RESPONDING_FLAG  = "/tmp/agent_responding"
RESPONDING_GRACE = 1.5

GESTURE_MAP = {
    "tope_la":           "tope_la",
    "calin":             "calin",
    "serrer_main":       "serrer_main",
    "grande_salutation": "grande_salutation",
}

# Keypoints COCO-17
NOSE       = 0
L_SHOULDER = 5
R_SHOULDER = 6
L_WRIST    = 9
R_WRIST    = 10
L_HIP      = 11
R_HIP      = 12

app = Flask(__name__)


def open_stream(url: str, retries: int = 10) -> cv2.VideoCapture:
    """Ouvre le stream MJPEG de vision_server (attend qu'il soit prêt)."""
    for i in range(retries):
        cap = cv2.VideoCapture(url)
        if cap.isOpened():
            print(f"[GESTURE] Stream connecté : {url}", flush=True)
            return cap
        print(f"[GESTURE] Attente stream vision_server ({i+1}/{retries})...", flush=True)
        time.sleep(3)
    raise RuntimeError(f"[GESTURE] Impossible de se connecter à {url}")


cap   = open_stream(VISION_STREAM)
model = YOLO('yolo26n-pose.pt')
print(f"[GESTURE] YOLO26-pose prêt", flush=True)


# ── Détection gestes ───────────────────────────────────────────────────────────
def ok(kps_conf, idx):
    return kps_conf[idx] > KP_MIN_CONF


def detect_gesture(kps, kps_conf):
    """Retourne (geste, label) ou (None, None). Priorité : chute > tope_la > calin > serrer_main."""

    # Chute : nez sous les hanches
    if ok(kps_conf, NOSE) and ok(kps_conf, L_HIP) and ok(kps_conf, R_HIP):
        hip_y = (kps[L_HIP][1] + kps[R_HIP][1]) / 2
        if kps[NOSE][1] > hip_y:
            return "grande_salutation", "CHUTE DETECTEE"

    # Tope là : 1 poignet au-dessus du nez
    if ok(kps_conf, NOSE):
        nose_y = kps[NOSE][1]
        l_up = ok(kps_conf, L_WRIST) and kps[L_WRIST][1] < nose_y
        r_up = ok(kps_conf, R_WRIST) and kps[R_WRIST][1] < nose_y
        if l_up or r_up:
            return "tope_la", "TOPE LA"

    # Câlin : bras en T
    if (ok(kps_conf, L_WRIST) and ok(kps_conf, R_WRIST) and
            ok(kps_conf, L_SHOULDER) and ok(kps_conf, R_SHOULDER)):
        shoulder_y   = (kps[L_SHOULDER][1] + kps[R_SHOULDER][1]) / 2
        shoulder_w   = abs(kps[R_SHOULDER][0] - kps[L_SHOULDER][0])
        wrist_spread = abs(kps[R_WRIST][0]    - kps[L_WRIST][0])
        l_level = abs(kps[L_WRIST][1] - shoulder_y) < shoulder_w * 0.4
        r_level = abs(kps[R_WRIST][1] - shoulder_y) < shoulder_w * 0.4
        arms_wide = wrist_spread > shoulder_w * 1.6
        if l_level and r_level and arms_wide:
            return "calin", "CALIN (BRAS EN T)"

    # Serrer la main : 1 poignet tendu vers caméra (zone centrale, mi-corps)
    if ok(kps_conf, NOSE) and ok(kps_conf, L_HIP) and ok(kps_conf, R_HIP):
        hip_y    = (kps[L_HIP][1] + kps[R_HIP][1]) / 2
        nose_y   = kps[NOSE][1]
        body_h   = hip_y - nose_y
        cx       = WIDTH / 2
        zone     = WIDTH * 0.45   # élargi : 288px sur 640 au lieu de 160px
        for wrist_idx in (L_WRIST, R_WRIST):
            if not ok(kps_conf, wrist_idx):
                continue
            wx, wy = kps[wrist_idx]
            # Zone verticale élargie : 20% au-dessus du nez → 20% sous les hanches
            if abs(wx - cx) < zone and (nose_y - body_h * 0.2) < wy < (hip_y + body_h * 0.2):
                return "serrer_main", "SERRER LA MAIN"

    return None, None


# ── Génération flux vidéo ──────────────────────────────────────────────────────
gesture_status      = {"label": "", "last_time": 0}
last_cmd_time       = 0
last_responding_end = 0   # timestamp de la dernière fin de réponse agent
frame_count         = 0


def _agent_is_busy() -> bool:
    """True si l'agent parle ou vient de finir de parler (grace period)."""
    if os.path.exists(RESPONDING_FLAG):
        return True
    return (time.time() - last_responding_end) < RESPONDING_GRACE


def generate():
    global frame_count, last_cmd_time, cap

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[GESTURE] Reconnexion stream...", flush=True)
            cap.release()
            time.sleep(3)
            cap = open_stream(VISION_STREAM)
            continue

        if frame_count % YOLO_SKIP == 0:
            results = model(frame, conf=CONFIDENCE, verbose=False)
            result  = results[0]
            frame   = result.plot()

            if result.keypoints is not None and len(result.keypoints.xy) > 0:
                kps      = result.keypoints.xy[0].cpu().numpy()
                kps_conf = result.keypoints.conf[0].cpu().numpy()

                if len(kps) >= 13:
                    geste, label = detect_gesture(kps, kps_conf)
                    if geste is not None:
                        now = time.time()
                        if now - last_cmd_time > COOLDOWN_S and not _agent_is_busy():
                            print(f"[GESTURE] {label} détecté !", flush=True)
                            last_cmd_time               = now
                            gesture_status["label"]     = label
                            gesture_status["last_time"] = now
                            threading.Thread(
                                target=execute_gesture,
                                args=(geste,),
                                daemon=True
                            ).start()
                        elif _agent_is_busy():
                            print(f"[GESTURE] {label} ignoré (agent en cours)", flush=True)

        if time.time() - gesture_status["last_time"] < 2.0:
            cv2.putText(frame, gesture_status["label"], (20, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 0), 3)

        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, QUALITY])
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
               + buffer.tobytes() + b'\r\n')
        frame_count += 1


@app.route('/')
def index():
    return '''<html><head><title>G1 Gesture Pose</title><meta charset="utf-8">
<style>body{background:#111;display:flex;justify-content:center;align-items:center;
min-height:100vh;margin:0;flex-direction:column;gap:12px;padding:20px;}
img{border:2px solid #444;max-width:100%;}h1{color:white;font-family:monospace;margin:0;}
table{font-family:monospace;border-collapse:collapse;}
td{color:#ccc;padding:3px 16px;}td:first-child{color:#fff;}</style></head><body>
<h1>Unitree G1 — Gesture Pose</h1>
<table>
  <tr><td>&#x270B; Main lev&#xe9;e</td><td>&#x2192; tope_la</td></tr>
  <tr><td>&#x1F917; Bras en T</td><td>&#x2192; calin</td></tr>
  <tr><td>&#x1F91D; Main tendue cam&#xe9;ra</td><td>&#x2192; serrer_main</td></tr>
  <tr><td>&#x1F6A8; Chute d&#xe9;tect&#xe9;e</td><td>&#x2192; grande_salutation</td></tr>
</table>
<img src="/stream"></body></html>'''


@app.route('/stream')
def stream():
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == '__main__':
    print(f"[GESTURE] Stream sur http://192.168.123.164:{PORT}", flush=True)
    app.run(host='0.0.0.0', port=PORT, threaded=True)
