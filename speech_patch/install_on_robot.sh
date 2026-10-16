#!/bin/bash
# install_on_robot.sh - A EXECUTER SUR LE ROBOT (terminal NoMachine, user ubuntu)
# Installe le wrapper offline dans la bibliotheque speech v2.0 du ROSOrin Pro.
#
# Usage :
#   bash install_on_robot.sh [chemin/speech_offline_patch.py] [OLLAMA_URL] [OLLAMA_MODEL]
#
# Le vrai travail est fait par : python3 speech_offline_patch.py --install

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH_SRC="$1"
[ -z "$PATCH_SRC" ] && PATCH_SRC="$SCRIPT_DIR/speech_offline_patch.py"
OLLAMA_URL="$2"
[ -z "$OLLAMA_URL" ] && OLLAMA_URL="http://192.168.1.20:11434"
OLLAMA_MODEL="$3"
[ -z "$OLLAMA_MODEL" ] && OLLAMA_MODEL="qwen3.5:9b"

if [ ! -f "$PATCH_SRC" ]; then
    echo "ERREUR : patch introuvable : $PATCH_SRC"
    echo "Transferez speech_offline_patch.py sur le robot (glisser-deposer NoMachine)"
    echo "ou passez son chemin en 1er argument."
    exit 1
fi

echo "=== Installation du patch offline speech ==="
echo "Patch  : $PATCH_SRC"
echo "Ollama : $OLLAMA_URL ($OLLAMA_MODEL)"
echo ""

python3 "$PATCH_SRC" --install --ollama-url "$OLLAMA_URL" --ollama-model "$OLLAMA_MODEL"

echo ""
echo "=== Selftest ==="
python3 "$PATCH_SRC" --selftest --ollama-url "$OLLAMA_URL" || true

echo ""
echo "Termine. Relancez ensuite le noeud LLM :"
echo "  ros2 launch large_models_examples llm_control_move.launch.py"

