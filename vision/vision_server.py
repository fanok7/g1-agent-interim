#!/usr/bin/env python3
"""
vision/vision_server.py - A lancer sur le robot G1 (miniconda python3)
Stream caméra RealSense D435i avec détection YOLO26 + distance.

- HTTP MJPEG  : http://192.168.123.164:8080
- Socket 9997 : envoie les détections à l'agent (g1_chat via vision_tool)

Format socket → JSON : {"objects": [{"label":"person","conf":0.95,"dist":1.2,"x":320,"y":240}]}

Lancement :
    /home/unitree/miniconda3/bin/python3 /home/unitree/g1_agent_interim/vision/vision_server.py
"""

import json
import socket
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response
from ultralytics import YOLO

try:
    import pyrealsense2 as rs
    USE_REALSENSE = True
    print("[VISION] Mode RealSense D435i (RGB + depth)")
except ImportError:
    USE_REALSENSE = False
    print("[VISION] pyrealsense2 absent → fallback webcam (pas de distance)")

# ── Config ────────────────────────────────────────────────────────────────────
DEVICE_ID       = 4          # fallback webcam si pas de RealSense
HTTP_PORT       = 8080
SOCKET_PORT     = 9997       # port écouté par vision_tool.py dans l'agent
WIDTH, HEIGHT   = 640, 480
QUALITY         = 75
CONFIDENCE      = 0.45
YOLO_SKIP       = 3          # YOLO 1 frame sur N (charge CPU/GPU)
PUBLISH_EVERY   = 1.0        # secondes entre deux publications socket
MAX_OBJECTS     = 5          # max objets remontés à l'agent
# ──────────────────────────────────────────────────────────────────────────────

app   = Flask(__name__)
model = YOLO('/home/unitree/yolo26n.pt')

# État partagé thread-safe
_lock          = threading.Lock()
_last_frame    = None
_last_dets     = []   # [{"label":…,"conf":…,"dist":…,"x":…,"y":…}]
_subscribers   = []   # sockets connectés (vision_tool)

# ── Initialisation caméra ─────────────────────────────────────────────────────

def _init_realsense():
    pipe   = rs.pipeline()
    cfg    = rs.config()
    cfg.enable_stream(rs.stream.color, WIDTH, HEIGHT, rs.format.bgr8, 30)
    cfg.enable_stream(rs.stream.depth, WIDTH, HEIGHT, rs.format.z16,  30)
    pipe.start(cfg)
    align  = rs.align(rs.stream.color)
    return pipe, align

def _init_webcam():
    for idx in [DEVICE_ID, 0, 1, 2, 3, 5, 6]:
        cap = cv2.VideoCapture(idx)
        ret, frm = cap.read()
        if cap.isOpened() and ret and len(frm.shape) == 3:
            b, g, _ = cv2.split(frm)
            if cv2.countNonZero(cv2.absdiff(b, g)) > 1000:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
                print(f"[VISION] Webcam /dev/video{idx}")
                return cap
        cap.release()
    raise RuntimeError("Aucune caméra RGB disponible")

# ── Thread capture + détection ────────────────────────────────────────────────

def _capture_loop():
    global _last_frame, _last_dets

    if USE_REALSENSE:
        pipe, align = _init_realsense()
    else:
        cap = _init_webcam()

    frame_count = 0

    while True:
        try:
            if USE_REALSENSE:
                frames   = pipe.wait_for_frames(timeout_ms=5000)
                aligned  = align.process(frames)
                color_f  = aligned.get_color_frame()
                depth_f  = aligned.get_depth_frame()
                if not color_f or not depth_f:
                    continue
                frame = np.asanyarray(color_f.get_data())
                depth = depth_f   # on garde le frame RS pour get_distance
            else:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.5)
                    cap = _init_webcam()
                    continue
                depth = None

            dets = []
            annotated = frame.copy()

            if frame_count % YOLO_SKIP == 0:
                results = model(frame, conf=CONFIDENCE, verbose=False)
                r       = results[0]
                annotated = r.plot()

                if r.boxes is not None:
                    for box in r.boxes:
                        cls  = int(box.cls[0])
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

                        if USE_REALSENSE and depth:
                            dist = round(depth.get_distance(
                                min(cx, WIDTH - 1), min(cy, HEIGHT - 1)
                            ), 2)
                        else:
                            dist = -1.0   # inconnue

                        dets.append({
                            "label": model.names[cls],
                            "conf":  round(conf, 2),
                            "dist":  dist,
                            "x":     cx,
                            "y":     cy,
                        })

                # Trier par confiance décroissante, limiter
                dets.sort(key=lambda d: d["conf"], reverse=True)
                dets = dets[:MAX_OBJECTS]

            with _lock:
                _last_frame = annotated
                if frame_count % YOLO_SKIP == 0:
                    _last_dets = dets

            frame_count += 1

        except Exception as e:
            print(f"[VISION] Erreur capture : {e}")
            time.sleep(1)


# ── Thread publication socket ─────────────────────────────────────────────────

def _publish_loop():
    """Serveur socket : accepte des clients (vision_tool) et leur envoie les dets."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', SOCKET_PORT))
    srv.listen(5)
    print(f"[VISION] Socket pub sur 127.0.0.1:{SOCKET_PORT}")

    def _handle(conn):
        try:
            while True:
                with _lock:
                    dets = list(_last_dets)
                payload = json.dumps({"objects": dets}) + '\n'
                conn.sendall(payload.encode())
                time.sleep(PUBLISH_EVERY)
        except Exception:
            pass
        finally:
            conn.close()

    while True:
        try:
            conn, _ = srv.accept()
            threading.Thread(target=_handle, args=(conn,), daemon=True).start()
        except Exception as e:
            print(f"[VISION] Erreur serveur socket : {e}")


# ── HTTP MJPEG ────────────────────────────────────────────────────────────────

def _generate_mjpeg():
    while True:
        with _lock:
            frame = _last_frame

        if frame is None:
            time.sleep(0.05)
            continue

        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, QUALITY])
        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n'
            + buf.tobytes()
            + b'\r\n'
        )


@app.route('/')
def index():
    return '''<html><head><title>G1 Vision</title>
    <style>body{background:#111;display:flex;flex-direction:column;align-items:center;
    justify-content:center;height:100vh;margin:0;gap:12px;}
    h1{color:white;font-family:monospace;}img{border:2px solid #444;max-width:100%;}</style>
    </head><body><h1>Unitree G1 — Vision YOLO26 + RealSense</h1>
    <img src="/stream"></body></html>'''


@app.route('/stream')
def stream():
    return Response(_generate_mjpeg(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/detections')
def detections():
    """Endpoint JSON : état courant des détections."""
    with _lock:
        dets = list(_last_dets)
    return {"objects": dets}


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    threading.Thread(target=_capture_loop, daemon=True).start()
    threading.Thread(target=_publish_loop, daemon=True).start()

    print(f"[VISION] Stream HTTP  → http://192.168.123.164:{HTTP_PORT}")
    print(f"[VISION] Socket agent → 127.0.0.1:{SOCKET_PORT}")
    app.run(host='0.0.0.0', port=HTTP_PORT, threaded=True)
