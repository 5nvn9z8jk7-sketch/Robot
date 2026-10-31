#!/bin/bash
# install_on_robot.sh - A EXECUTER SUR LE ROBOT (terminal NoMachine, user ubuntu)
# Installe le wrapper offline dans la bibliotheque speech v2.0 du ROSOrin Pro,
# configure le francais (ASR/TTS/LLM) et telecharge les modeles si absents.
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

echo "=== Installation du patch offline speech (francais) ==="
echo "Patch  : $PATCH_SRC"
echo "Ollama : $OLLAMA_URL ($OLLAMA_MODEL)"
echo "Langue : fr (ASR + TTS + LLM)"
echo ""

# 1. Installer le patch dans le package speech
python3 "$PATCH_SRC" --install --ollama-url "$OLLAMA_URL" --ollama-model "$OLLAMA_MODEL"

# 2. Configurer les variables d'environnement dans ~/.bashrc (idempotent)
echo ""
echo "=== Configuration environnement (francais) ==="
BASHRC="$HOME/.bashrc"

# OLLAMA_URL (si pas deja present ou different)
if ! grep -q "^export OLLAMA_URL=" "$BASHRC" 2>/dev/null; then
    echo "export OLLAMA_URL=$OLLAMA_URL" >> "$BASHRC"
    echo "Ajout OLLAMA_URL=$OLLAMA_URL dans ~/.bashrc"
else
    # Mettre a jour si l'URL a change
    sed -i "s|^export OLLAMA_URL=.*|export OLLAMA_URL=$OLLAMA_URL|" "$BASHRC"
    echo "Mise a jour OLLAMA_URL=$OLLAMA_URL dans ~/.bashrc"
fi

# SPEECH_LANG=fr (francais par defaut)
if ! grep -q "^export SPEECH_LANG=" "$BASHRC" 2>/dev/null; then
    echo "export SPEECH_LANG=fr" >> "$BASHRC"
    echo "Ajout SPEECH_LANG=fr dans ~/.bashrc"
fi

# SPEECH_FORCE_FR=1 (forcer le prompt systeme francais)
if ! grep -q "^export SPEECH_FORCE_FR=" "$BASHRC" 2>/dev/null; then
    echo "export SPEECH_FORCE_FR=1" >> "$BASHRC"
    echo "Ajout SPEECH_FORCE_FR=1 dans ~/.bashrc"
fi

# Charger les variables pour la session courante
export OLLAMA_URL="$OLLAMA_URL"
export SPEECH_LANG="fr"
export SPEECH_FORCE_FR="1"

# 3. Telecharger les modeles francais si absents
echo ""
echo "=== Modeles sherpa-onnx francais ==="
python3 "$PATCH_SRC" --download-fr || {
    echo "ATTENTION : le telechargement des modeles francais a echoue."
    echo "Vous pouvez le relancer plus tard avec :"
    echo "  python3 $PATCH_SRC --download-fr"
}

# 4. Selftest
echo ""
echo "=== Selftest ==="
python3 "$PATCH_SRC" --selftest --ollama-url "$OLLAMA_URL" || true

echo ""
echo "=== Termine ==="
echo "Redemarrez le terminal (ou 'source ~/.bashrc') pour charger les variables."
echo "Puis relancez le noeud LLM :"
echo "  ros2 launch large_models_examples llm_control_move.launch.py"
echo ""
echo "Parlez en francais au robot :"
echo "  'Avance d'un metre'"
echo "  'Tourne a gauche'"
echo "  'Stop'"
