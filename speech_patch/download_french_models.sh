#!/bin/bash
# download_french_models.sh - Telecharge les modeles sherpa-onnx francais sur le robot
#
# Usage (sur le robot, user ubuntu) :
#   chmod +x download_french_models.sh
#   ./download_french_models.sh
#
# Ou via le wrapper Python :
#   python3 speech_patch/speech_offline_patch.py --download-fr
#
# Modeles telecharges dans ~/third_party/sherpa-onnx/ :
#   - ASR streaming zipformer francais  (~80 Mo)
#     sherpa-onnx-streaming-zipformer-fr-2023-02-20/
#   - TTS VITS piper fr_FR siwis        (~60 Mo)
#     vits-piper-fr_FR-siwis-medium/

set -e

SHERPA_DIR="${SHERPA_DIR:-$HOME/third_party/sherpa-onnx}"
echo "=== Telechargement modeles sherpa-onnx francais ==="
echo "Dossier cible : $SHERPA_DIR"
mkdir -p "$SHERPA_DIR"
cd "$SHERPA_DIR"

# ---------------------------------------------------------------
# 1. ASR streaming zipformer francais
# ---------------------------------------------------------------
ASR_DIR="sherpa-onnx-streaming-zipformer-fr-2023-02-20"
ASR_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-fr-2023-02-20.tar.bz2"

if [ -f "$ASR_DIR/.complete" ]; then
    echo "[ASR-fr] Deja telecharge ($ASR_DIR)"
else
    echo "[ASR-fr] Telechargement (~80 Mo)..."
    echo "  $ASR_URL"
    wget -q --show-progress -O asr-fr.tar.bz2 "$ASR_URL" || {
        echo "ERREUR : telechargement ASR echoue"
        exit 1
    }
    echo "[ASR-fr] Extraction..."
    tar xjf asr-fr.tar.bz2
    rm -f asr-fr.tar.bz2
    touch "$ASR_DIR/.complete"
    echo "[ASR-fr] OK : $ASR_DIR"
fi

# ---------------------------------------------------------------
# 2. TTS VITS piper fr_FR siwis (voix feminine, bonne qualite)
# ---------------------------------------------------------------
TTS_DIR="vits-piper-fr_FR-siwis-medium"
TTS_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-fr_FR-siwis-medium.tar.bz2"

if [ -f "$TTS_DIR/.complete" ]; then
    echo "[TTS-fr] Deja telecharge ($TTS_DIR)"
else
    echo "[TTS-fr] Telechargement (~60 Mo)..."
    echo "  $TTS_URL"
    wget -q --show-progress -O tts-fr.tar.bz2 "$TTS_URL" || {
        echo "ERREUR : telechargement TTS echoue"
        exit 1
    }
    echo "[TTS-fr] Extraction..."
    tar xjf tts-fr.tar.bz2
    rm -f tts-fr.tar.bz2
    touch "$TTS_DIR/.complete"
    echo "[TTS-fr] OK : $TTS_DIR"
fi

# ---------------------------------------------------------------
# 3. Verifier l'installation de sherpa-onnx Python
# ---------------------------------------------------------------
echo ""
echo "=== Verification sherpa-onnx Python ==="
python3 -c "import sherpa_onnx; print('sherpa_onnx OK:', sherpa_onnx.__version__)" 2>/dev/null || {
    echo "ATTENTION : sherpa_onnx Python non installe."
    echo "  Installer avec : pip install sherpa-onnx"
}

echo ""
echo "=== Termine ==="
echo "Modeles disponibles dans $SHERPA_DIR :"
ls -la "$SHERPA_DIR" | grep -E "zipformer|vits" || true
echo ""
echo "Prochaine etape : relancer le robot et tester :"
echo "  ros2 launch large_models_examples llm_control_move.launch.py"
echo "Parler en francais : 'Avance d'un metre', 'Tourne a gauche', 'Stop'"
