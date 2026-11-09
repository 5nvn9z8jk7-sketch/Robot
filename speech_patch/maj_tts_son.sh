#!/bin/bash
# maj_tts_son.sh — Donne XDG_RUNTIME_DIR aux programmes lancés par le watchdog
# (sinon la synthèse vocale lancée au boot ne sort aucun son), puis relance
# uniquement la synthèse vocale et lui fait dire une phrase de test.
# Sauvegarde, vérification de syntaxe, arrêt à la première erreur.
set -euo pipefail
D=/home/ubuntu/speech_patch
URL=https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-0-menage/speech_patch
F=robot_watchdog.py
TS=$(date +%Y%m%d_%H%M%S)
ROS='source /opt/ros/humble/setup.bash; source /home/ubuntu/ros2_ws/install/setup.bash'

echo "== 1/4 Téléchargement + vérification =="
curl -fsSL "$URL/$F" -o /tmp/$F.new
python3 -m py_compile /tmp/$F.new
grep -q 'XDG_RUNTIME_DIR=/run/user/1000' /tmp/$F.new || { echo "ERREUR: version téléchargée inattendue (cache GitHub ?), rien n'est remplacé"; exit 1; }
echo "  OK"

echo "== 2/4 Sauvegarde + remplacement du watchdog =="
mkdir -p $D/sauvegardes
cp $D/$F $D/sauvegardes/$F.$TS
cp /tmp/$F.new $D/$F
bash $D/start_watchdogs.sh

echo "== 3/4 Relance de la synthèse vocale avec le réglage audio =="
pkill -f '[t]ts_node' || true
sleep 2
mkdir -p /tmp/watchdog_logs
setsid nohup bash -c "export XDG_RUNTIME_DIR=/run/user/1000 ASR_MODE=offline ASR_LANGUAGE=fr MIC_TYPE=xf; $ROS; exec ros2 run large_models tts_node" \
  > /tmp/watchdog_logs/tts_node.log 2>&1 < /dev/null &
sleep 12
for p in $(pgrep -f '[t]ts_node'); do
  echo "  PID $p : $(tr '\0' '\n' < /proc/$p/environ | grep XDG_RUNTIME_DIR || echo 'XDG_RUNTIME_DIR ABSENT')"
done

echo "== 4/4 Phrase de test =="
bash -c "$ROS; ros2 topic pub --once -w 1 /tts_node/tts_text std_msgs/msg/String 'data: La voix du robot fonctionne.'" >/dev/null
echo "  Phrase envoyée : le robot doit dire « La voix du robot fonctionne »."
echo "Retour arrière : cp $D/sauvegardes/$F.$TS $D/$F && bash $D/start_watchdogs.sh"
