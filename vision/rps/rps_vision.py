"""
rps_vision.py — Détection geste adversaire Pierre Feuille Ciseaux
=================================================================
Utilise yolo11-rps-detection.pt sur la D435i (Jetson) ou
la Logitech C270 (/dev/video9) pour les tests PC.

Utilisation standalone :
    python3.8 rps_vision.py --source 0

Utilisation comme module :
    from rps_vision import RPSVision
    vision = RPSVision(model_path='yolo11-rps-detection.pt', source=0)
    vision.start()
    geste = vision.get_gesture()  # 'rock' / 'paper' / 'scissors' / None
    vision.stop()
"""

import cv2
import threading
import time
import argparse
from collections import Counter
from ultralytics import YOLO

# ── Config ───────────────────────────────────────────────────────────────────
CONF_MIN    = 0.50
SKIP        = 3
BUF_LEN     = 8    # frames pour stabiliser le geste

# Mapping anglais → français
FR = {"rock": "pierre", "paper": "feuille", "scissors": "ciseaux"}

class RPSVision:
    def __init__(self, model_path="yolo11-rps-detection.pt", source=0,
                 conf=CONF_MIN):
        self.model_path = model_path
        self.source     = source
        self.conf       = conf
        self._gesture   = None    # geste stable (français)
        self._raw       = None    # geste brut dernière frame
        self._running   = False
        self._lock      = threading.Lock()
        self._thread    = None
        self._frame     = None    # dernière frame annotée

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[INFO] Vision démarrée — source={self.source}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def get_gesture(self):
        """Retourne le geste stable courant (français) ou None."""
        with self._lock:
            return self._gesture

    def get_frame(self):
        """Retourne la dernière frame annotée."""
        with self._lock:
            return self._frame

    def capture_gesture(self, timeout=2.0):
        """
        Attend un geste stable pendant timeout secondes.
        Retourne le geste ou None si timeout.
        """
        t0 = time.time()
        while time.time() - t0 < timeout:
            g = self.get_gesture()
            if g: return g
            time.sleep(0.1)
        return None

    def _loop(self):
        model = YOLO(self.model_path)
        print(f"[INFO] Classes modèle : {model.names}")

        cap = cv2.VideoCapture(
            int(self.source) if str(self.source).isdigit() else self.source)
        if not cap.isOpened():
            print(f"[ERR] Impossible d'ouvrir : {self.source}")
            return

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        frame_idx   = 0
        last_res    = []
        gesture_buf = []

        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05); continue

            frame_idx += 1

            if frame_idx % SKIP == 0:
                h0, w0 = frame.shape[:2]
                small  = cv2.resize(frame, (320, int(h0*320/w0)))
                sx, sy = w0/320, h0/int(h0*320/w0)

                results  = model(small, imgsz=320, verbose=False,
                                 conf=self.conf)
                last_res = []
                for r in results:
                    if r.boxes is None or len(r.boxes) == 0: continue
                    for box, cls, c in zip(r.boxes.xyxy.cpu().numpy(),
                                           r.boxes.cls.cpu().numpy(),
                                           r.boxes.conf.cpu().numpy()):
                        box[[0,2]] *= sx; box[[1,3]] *= sy
                        last_res.append((box.copy(),
                                         model.names[int(cls)], float(c)))

                g = FR.get(last_res[0][1]) if last_res else None
                gesture_buf.append(g)
                if len(gesture_buf) > BUF_LEN: gesture_buf.pop(0)
                valid = [x for x in gesture_buf if x]
                stable = (Counter(valid).most_common(1)[0][0]
                          if len(valid) >= BUF_LEN//2 else None)
                with self._lock:
                    self._gesture = stable
                    self._raw     = g

            # Dessin
            out = cv2.resize(frame, (1280, 720))
            sx2, sy2 = 1280/640, 720/480
            for box, label, conf_det in last_res:
                x1,y1 = int(box[0]*sx2), int(box[1]*sy2)
                x2,y2 = int(box[2]*sx2), int(box[3]*sy2)
                cv2.rectangle(out,(x1,y1),(x2,y2),(100,255,100),2)
                cv2.putText(out,
                            f"{FR.get(label,label).upper()} {conf_det:.0%}",
                            (x1,y1-10), cv2.FONT_HERSHEY_DUPLEX, 0.9,
                            (100,255,100), 2)

            with self._lock:
                g_disp = self._gesture or "?"
            cv2.putText(out, f"Geste : {g_disp.upper()}",
                        (20, out.shape[0]-20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200,200,200), 2)

            with self._lock:
                self._frame = out.copy()

        cap.release()

# ── Test standalone ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model",  default="yolo11-rps-detection.pt")
    ap.add_argument("--source", default="/dev/video4")
    ap.add_argument("--conf",   type=float, default=0.50)
    args = ap.parse_args()

    vision = RPSVision(args.model, args.source, args.conf)
    vision.start()

    print("Appuyez sur Q pour quitter")
    while True:
        frame = vision.get_frame()
        if frame is not None:
            cv2.imshow("RPS Vision", frame)
        if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
            break

    vision.stop()
    cv2.destroyAllWindows()
