#!/usr/bin/env python3
"""
vision/vision_server.py — Détection YOLO sur 2 caméras en parallèle.

Threads :
  _capture_rs_loop  : lit RealSense (D435i) en continu        → _raw_rs
  _yolo_ugreen_loop : YOLO toutes les 2s sur frame UGREEN      → _dets_ugreen
                      (lit /tmp/latest_ugreen.jpg fourni par face_id.py)
  _yolo_rs_loop     : YOLO toutes les 2s sur RealSense         → _dets_realsense
  _merge_loop       : fusionne les 2 listes, écrit vision_state.json

IPC fichiers :
  /tmp/latest_ugreen.jpg   → frame UGREEN écrite par face_id.py (lecture seule ici)
  /tmp/vision_state.json   → {"objects":[{label,conf,x,y,cam}], "ts":…}
  /tmp/vision_pause        → RPS game : stoppe la capture RealSense

HTTP (port 8080) :
  /stream            → MJPEG UGREEN annoté (relu depuis face_id)
  /stream/realsense  → MJPEG RealSense annoté
  /detections        → JSON détections courantes
"""

import json
import os
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response
from ultralytics import YOLO

try:
    import pyrealsense2 as rs
    USE_REALSENSE = True
    print("[VISION] RealSense D435i disponible")
except ImportError:
    USE_REALSENSE = False
    print("[VISION] pyrealsense2 absent — YOLO RealSense désactivé")

# RealSense : capture couleur uniquement (pas de YOLO RS — réservée au scan QR).
# YOLO RS désactivé : le D435i décrochait en USB et spammait des erreurs.
USE_REALSENSE = True

# ── Config ────────────────────────────────────────────────────────────────────
MODEL_PATH      = '/home/unitree/yolo26n.engine'
UGREEN_FRAME    = '/tmp/latest_ugreen.jpg'    # fourni par face_id.py
RS_FRAME        = '/tmp/latest_realsense.jpg' # fourni par _capture_rs_loop (partagé avec qr_tool)
PAUSE_FILE      = '/tmp/vision_pause'
STATE_FILE      = '/tmp/vision_state.json'
QR_STATE_FILE   = '/tmp/qr_state.json'
QR_INTERVAL     = 1.0    # secondes entre deux tentatives de scan
QR_COOLDOWN     = 30.0   # secondes avant de re-signaler le même code
UV_BIN          = '/home/unitree/.local/bin/uv'
QR_REPO         = '/home/unitree/QR_scan_tool'
HTTP_PORT       = 8080
WIDTH, HEIGHT   = 640, 480
CONFIDENCE      = 0.50
YOLO_INTERVAL   = 2.0
MAX_OBJECTS     = 5
QUALITY         = 75
# ─────────────────────────────────────────────────────────────────────────────

app   = Flask(__name__)
model = YOLO(MODEL_PATH)

_lock           = threading.Lock()
_dets_ugreen    = []
_dets_realsense = []
_ann_ugreen     = None   # frame UGREEN annotée (pour HTTP stream)
_ann_realsense  = None   # frame RealSense annotée (pour HTTP stream)
_raw_rs         = None   # dernière frame RealSense brute


# ── Écriture atomique ─────────────────────────────────────────────────────────

def _write_state(dets):
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"objects": dets, "ts": time.time()}, f)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        print(f"[VISION] Erreur écriture état : {e}")


# ── Fusion des deux caméras ───────────────────────────────────────────────────

def _merge_and_write():
    """Fusionne UGREEN + RealSense, trie par confiance, écrit le fichier JSON."""
    with _lock:
        all_dets = list(_dets_ugreen) + list(_dets_realsense)
    all_dets.sort(key=lambda d: d["conf"], reverse=True)
    _write_state(all_dets[:MAX_OBJECTS])


# ── Thread YOLO UGREEN ────────────────────────────────────────────────────────

def _yolo_ugreen_loop():
    """YOLO sur la caméra UGREEN. Lit les frames depuis /tmp/latest_ugreen.jpg
    (écrit par face_id.py) — aucune ouverture directe de /dev/video0."""
    global _dets_ugreen, _ann_ugreen
    print("[YOLO-UGREEN] Démarré", flush=True)

    while True:
        time.sleep(YOLO_INTERVAL)
        if os.path.exists(PAUSE_FILE):
            continue
        if not os.path.exists(UGREEN_FRAME):
            # face_id.py pas encore démarré : vider SEULEMENT les détections UGREEN,
            # puis re-fusionner — surtout NE PAS faire _write_state([]) qui écraserait
            # les détections RealSense toutes les 2s (clignotement de la vision).
            with _lock:
                _dets_ugreen = []
            _merge_and_write()
            continue
        try:
            frame = cv2.imread(UGREEN_FRAME)
            if frame is None:
                continue

            results = model(frame, conf=CONFIDENCE, verbose=False)
            r       = results[0]
            ann     = r.plot()
            dets    = []

            if r.boxes is not None:
                for box in r.boxes:
                    cls  = int(box.cls[0])
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    dets.append({
                        "label": model.names[cls],
                        "conf":  round(conf, 2),
                        "x":     (x1 + x2) // 2,
                        "y":     (y1 + y2) // 2,
                        "cam":   "ugreen",
                    })

            with _lock:
                _dets_ugreen = dets
                _ann_ugreen  = ann

            _merge_and_write()
            print(f"[YOLO-UGREEN] {len(dets)} objet(s)", flush=True)

        except Exception as e:
            print(f"[YOLO-UGREEN] Erreur : {e}", flush=True)
            with _lock:
                _dets_ugreen = []
            _merge_and_write()


# ── Thread capture RealSense ──────────────────────────────────────────────────

def _capture_rs_loop():
    """Capture RealSense en continu → /tmp/latest_realsense.jpg (partagé avec qr_tool).
    Pas de YOLO sur la RealSense — réservée au scan QR à la demande."""
    global _raw_rs
    if not USE_REALSENSE:
        return

    # Auto-détection du premier device RealSense disponible
    pipe = None
    for attempt in range(10):
        try:
            ctx     = rs.context()
            devices = ctx.query_devices()
            if len(devices) == 0:
                raise RuntimeError("aucun device RealSense détecté")
            serial = devices[0].get_info(rs.camera_info.serial_number)
            p   = rs.pipeline()
            cfg = rs.config()
            cfg.enable_device(serial)
            cfg.enable_stream(rs.stream.color, WIDTH, HEIGHT, rs.format.bgr8, 30)
            p.start(cfg)
            pipe = p
            print(f"[RS-CAPTURE] RealSense {serial} démarrée", flush=True)
            break
        except Exception as e:
            if attempt < 9:
                print(f"[RS-CAPTURE] Tentative {attempt+1}/10 ({e}) — retry 5s", flush=True)
                time.sleep(5)
            else:
                print("[RS-CAPTURE] RealSense indisponible", flush=True)
                return

    _timeout_streak = 0

    while True:
        try:
            if os.path.exists(PAUSE_FILE):
                time.sleep(0.3)
                continue
            frames  = pipe.wait_for_frames(timeout_ms=5000)
            color_f = frames.get_color_frame()
            if not color_f:
                continue
            _timeout_streak = 0
            frame = np.asanyarray(color_f.get_data())
            with _lock:
                _raw_rs = frame
            # Écriture atomique du fichier partagé (lu par qr_tool et le stream HTTP)
            tmp = RS_FRAME.replace(".jpg", "_tmp.jpg")
            cv2.imwrite(tmp, frame, [cv2.IMWRITE_JPEG_QUALITY, QUALITY])
            os.replace(tmp, RS_FRAME)
        except Exception as e:
            print(f"[RS-CAPTURE] Erreur : {e}", flush=True)
            _timeout_streak += 1
            if _timeout_streak >= 3:
                # 3 timeouts consécutifs → hardware_reset et reprise
                print("[RS-CAPTURE] 3 timeouts — hardware_reset...", flush=True)
                try:
                    pipe.stop()
                    ctx2 = rs.context()
                    devs = ctx2.query_devices()
                    if len(devs) > 0:
                        devs[0].hardware_reset()
                    time.sleep(4)
                    pipe.start(cfg)
                    print("[RS-CAPTURE] Reprise après reset", flush=True)
                except Exception as re:
                    print(f"[RS-CAPTURE] Reset échoué ({re}) — retry 5s", flush=True)
                    time.sleep(5)
                _timeout_streak = 0
            else:
                time.sleep(1)


def _yolo_rs_loop():
    """YOLO RealSense désactivé — RealSense réservée au scan QR."""
    return


# ── Thread QR passif (RealSense) ─────────────────────────────────────────────

_DECODE_SCRIPT = (
    "import sys; sys.path.insert(0, '{repo}'); from scanner import scan_image; "
    "r = scan_image(sys.argv[1]); print(r if r else '__NONE__')"
)

def _qr_scan_loop():
    """Scan QR/PDF417/Aztec en continu sur la frame RealSense partagée.
    Utilise uv+zxingcpp pour supporter l'Aztec (billets Air France/KLM)."""
    import subprocess
    print("[QR] Thread passif démarré (QR+PDF417+Aztec via zxingcpp)", flush=True)
    _last_raw   = None
    _last_alert = 0.0
    _last_mtime = None

    while True:
        time.sleep(QR_INTERVAL)
        if not os.path.exists(RS_FRAME):
            continue
        try:
            mtime = os.path.getmtime(RS_FRAME)
        except OSError:
            continue
        if mtime == _last_mtime:
            continue
        _last_mtime = mtime
        try:
            out = subprocess.check_output(
                [UV_BIN, "run", "--project", QR_REPO, "python", "-c",
                 _DECODE_SCRIPT.format(repo=QR_REPO), RS_FRAME],
                stderr=subprocess.DEVNULL, timeout=4,
            ).decode().strip()
            raw = None if out == "__NONE__" else out
        except Exception:
            continue

        if not raw:
            continue

        now = time.time()
        if raw == _last_raw and (now - _last_alert) < QR_COOLDOWN:
            continue
        _last_raw   = raw
        _last_alert = now

        # Parse BCBP
        info = {"raw": raw, "ts": now}
        if raw.startswith("M"):
            try:
                nom_brut  = raw[2:22].strip()
                pnr       = raw[23:30].strip()
                depart    = raw[30:33].strip()
                arrivee   = raw[33:36].strip()
                compagnie = raw[36:39].strip()
                vol       = raw[39:44].strip()
                if "/" in nom_brut:
                    n, p = nom_brut.split("/", 1)
                    nom = "{} {}".format(p.strip().title(), n.strip().title())
                else:
                    nom = nom_brut.title()
                info = {"passager": nom, "pnr": pnr,
                        "vol": "{}{}".format(compagnie.strip(), vol.strip()),
                        "de": depart, "vers": arrivee, "raw": raw, "ts": now}
            except Exception:
                pass

        tmp = QR_STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(info, f, ensure_ascii=False)
        os.replace(tmp, QR_STATE_FILE)
        print("[QR] Billet détecté : {} {}".format(
            info.get("passager", "?"), info.get("vol", "")), flush=True)


# ── HTTP MJPEG ────────────────────────────────────────────────────────────────

def _gen_ugreen():
    while True:
        with _lock:
            frame = _ann_ugreen
        if frame is None:
            # Fallback : servir la dernière frame UGREEN brute
            raw = cv2.imread(UGREEN_FRAME) if os.path.exists(UGREEN_FRAME) else None
            frame = raw
        if frame is None:
            time.sleep(0.05)
            continue
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, QUALITY])
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
               + buf.tobytes() + b'\r\n')


def _gen_realsense():
    """Stream RealSense brut (depuis /tmp/latest_realsense.jpg partagé)."""
    while True:
        if os.path.exists(RS_FRAME):
            raw = cv2.imread(RS_FRAME)
            if raw is not None:
                _, buf = cv2.imencode('.jpg', raw, [cv2.IMWRITE_JPEG_QUALITY, QUALITY])
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                       + buf.tobytes() + b'\r\n')
                continue
        time.sleep(0.05)


@app.route('/')
def index():
    rs_link = '<a href="/stream/realsense" style="color:#aaa">RealSense</a>' if USE_REALSENSE else ''
    return f'''<html><head><title>G1 Vision</title>
    <style>body{{background:#111;display:flex;align-items:center;justify-content:center;
    height:100vh;margin:0;flex-direction:column;gap:12px;}}
    h1{{color:white;font-family:monospace;}}img{{border:2px solid #444;max-width:48%;}}
    .row{{display:flex;gap:12px;}}</style></head>
    <body><h1>Unitree G1 — YOLO dual-cam</h1>
    <div class="row"><img src="/stream"><img src="/stream/realsense"></div>
    </body></html>'''

@app.route('/stream')
def stream_ugreen():
    return Response(_gen_ugreen(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/stream/realsense')
def stream_realsense():
    return Response(_gen_realsense(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/detections')
def detections():
    with _lock:
        return {"objects": list(_dets_ugreen) + list(_dets_realsense)}


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    threading.Thread(target=_yolo_ugreen_loop, daemon=True).start()
    threading.Thread(target=_capture_rs_loop,  daemon=True).start()
    threading.Thread(target=_yolo_rs_loop,     daemon=True).start()
    threading.Thread(target=_qr_scan_loop,     daemon=True).start()
    print(f"[VISION] Stream UGREEN     → http://192.168.123.164:{HTTP_PORT}/stream")
    print(f"[VISION] Stream RealSense  → http://192.168.123.164:{HTTP_PORT}/stream/realsense")
    print(f"[VISION] Détections JSON   → http://192.168.123.164:{HTTP_PORT}/detections")
    app.run(host='0.0.0.0', port=HTTP_PORT, threaded=True)
