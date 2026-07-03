#!/bin/bash
# install.sh — Dépendances face_id pour Jetson JetPack 5.1.1 (CUDA 11.4, aarch64)
set -e

PYTHON=/home/unitree/miniconda3/bin/python3
PIP="$PYTHON -m pip"
PY_VER=$($PYTHON -c "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')")

echo "=== Python détecté : $PY_VER ==="

# ── Étape 1 : onnxruntime-gpu ──────────────────────────────────────────────────
echo ""
echo "=== [1/3] onnxruntime-gpu pour Jetson (aarch64, CUDA 11.4) ==="

# Cherche un wheel déjà téléchargé dans le dossier courant
WHEEL=$(ls onnxruntime_gpu-*-linux_aarch64.whl 2>/dev/null | head -1)

if [ -n "$WHEEL" ]; then
    echo "  Wheel trouvé localement : $WHEEL"
    $PIP install "$WHEEL"
else
    echo "  Tentative index Microsoft CUDA-11..."
    $PIP install onnxruntime-gpu \
        --index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-11/pypi/simple/ \
        2>/dev/null && echo "  [OK] onnxruntime-gpu installé" || {
        echo ""
        echo "  ╔══════════════════════════════════════════════════════════════╗"
        echo "  ║  Installation automatique impossible pour Jetson aarch64.   ║"
        echo "  ║                                                              ║"
        echo "  ║  1. Va sur : elinux.org/Jetson_Zoo  (section ONNX Runtime)  ║"
        echo "  ║  2. Télécharge le wheel pour JetPack 5.x / $PY_VER          ║"
        echo "  ║  3. Copie le .whl ici puis relance ce script                ║"
        echo "  ║                                                              ║"
        echo "  ║  En attendant : installation CPU (pas de GPU)               ║"
        echo "  ╚══════════════════════════════════════════════════════════════╝"
        echo ""
        $PIP install onnxruntime
    }
fi

# ── Étape 2 : insightface ──────────────────────────────────────────────────────
echo ""
echo "=== [2/3] insightface + scipy ==="
$PIP install insightface scipy

# ── Étape 3 : vérification ────────────────────────────────────────────────────
echo ""
echo "=== [3/3] Vérification ==="
$PYTHON - <<'EOF'
import onnxruntime as ort
providers = ort.get_available_providers()
print(f"  onnxruntime {ort.__version__}")
print(f"  Providers disponibles : {providers}")
if 'CUDAExecutionProvider' in providers:
    print("  [OK] GPU CUDA disponible")
else:
    print("  [WARN] GPU non disponible — fonctionnera en CPU (plus lent)")

from insightface.app import FaceAnalysis
fa = FaceAnalysis(name="buffalo_sc", providers=['CUDAExecutionProvider','CPUExecutionProvider'])
fa.prepare(ctx_id=0, det_size=(640,480))
print("  [OK] InsightFace prêt")
EOF

echo ""
echo "=== Installation terminée ==="
