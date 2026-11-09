#!/bin/bash
# maj_pick_rotation.sh — Remet la rotation chronométrée (validée le 30/10) dans
# pick_and_place_node_v6.py, en gardant l'arrêt d'urgence de la PR #3.
# Sauvegarde, vérification de syntaxe, arrêt à la première erreur.
set -euo pipefail
D=/home/ubuntu/speech_patch
URL=https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-0-menage/speech_patch
F=pick_and_place_node_v6.py
TS=$(date +%Y%m%d_%H%M%S)
curl -fsSL "$URL/$F" -o /tmp/$F.new
python3 -m py_compile /tmp/$F.new
grep -q 'chrono {duration' /tmp/$F.new || { echo "ERREUR: version téléchargée inattendue (cache GitHub ?), rien n'est remplacé"; exit 1; }
mkdir -p $D/sauvegardes
cp $D/$F $D/sauvegardes/$F.$TS
cp /tmp/$F.new $D/$F
echo "Remplacé (ancien : sauvegardes/$F.$TS)"
pkill -f '[p]ick_and_place_node_v6.py' || true
sleep 2
setsid nohup bash -c "source /opt/ros/humble/setup.bash; source /home/ubuntu/ros2_ws/install/setup.bash; exec python3 -u $D/$F" > /tmp/pick_v6.log 2>&1 < /dev/null &
sleep 8
echo "pick v6 : $(pgrep -fc '[p]ick_and_place_node_v6.py' || true) processus (attendu : 1)"
tail -2 /tmp/pick_v6.log || true
echo "Retour arrière : cp $D/sauvegardes/$F.$TS $D/$F"
