#!/bin/bash
# maj_etape1.sh — Installe le gardien de sécurité (étape 1) sur le robot.
#   gardien_securite.py + securite_logique.py : seul passage vers les roues
#   pick v6, mission, pont vocal : publient sur /robot/cmd_vel/auto
#   robot_watchdog.py : surveille et relance aussi le gardien
# Sauvegarde, vérification de syntaxe de TOUS les fichiers avant de remplacer,
# arrêt à la première erreur.
set -euo pipefail
D=/home/ubuntu/speech_patch
URL=https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-1-securite/speech_patch
TS=$(date +%Y%m%d_%H%M%S)
FICHIERS="securite_logique.py gardien_securite.py pick_and_place_node_v6.py autonomous_mission_node.py llm_move_bridge_node.py robot_watchdog.py"
ROS='source /opt/ros/humble/setup.bash; source /home/ubuntu/ros2_ws/install/setup.bash'

echo "== 1/4 Téléchargement + vérification =="
mkdir -p /tmp/maj_etape1
for f in $FICHIERS; do
  curl -fsSL "$URL/$f" -o "/tmp/maj_etape1/$f"
  python3 -m py_compile "/tmp/maj_etape1/$f"
done
grep -q "robot/cmd_vel/auto" /tmp/maj_etape1/pick_and_place_node_v6.py || { echo "ERREUR: version inattendue (cache GitHub ?), rien n'est remplacé"; exit 1; }
echo "  OK ($FICHIERS)"

echo "== 2/4 Sauvegarde + remplacement =="
mkdir -p "$D/sauvegardes"
for f in $FICHIERS; do
  [ -f "$D/$f" ] && cp "$D/$f" "$D/sauvegardes/$f.$TS"
  cp "/tmp/maj_etape1/$f" "$D/$f"
done
echo "  sauvegardes : $D/sauvegardes/*.$TS"

echo "== 3/4 Relance des superviseurs =="
bash "$D/start_watchdogs.sh"

echo "== 4/4 Relance du gardien, du pick, de la mission et du pont vocal =="
export XDG_RUNTIME_DIR=/run/user/1000
for p in '[g]ardien_securite.py' '[p]ick_and_place_node_v6.py' '[a]utonomous_mission_node.py' '[l]lm_move_bridge_node.py'; do
  pkill -f "$p" || true
done
sleep 2
mkdir -p /tmp/watchdog_logs
setsid nohup bash -c "$ROS; exec python3 -u $D/gardien_securite.py" > /tmp/watchdog_logs/gardien_securite.log 2>&1 < /dev/null &
setsid nohup bash -c "$ROS; exec python3 -u $D/pick_and_place_node_v6.py" > /tmp/pick_v6.log 2>&1 < /dev/null &
setsid nohup bash -c "$ROS; exec python3 -u $D/autonomous_mission_node.py" > /tmp/mission.log 2>&1 < /dev/null &
setsid nohup bash -c "$ROS; exec python3 -u $D/llm_move_bridge_node.py" > /tmp/watchdog_logs/llm_move_bridge.log 2>&1 < /dev/null &
sleep 12
for p in '[g]ardien_securite.py' '[p]ick_and_place_node_v6.py' '[a]utonomous_mission_node.py' '[l]lm_move_bridge_node.py'; do
  echo "  $p : $(pgrep -fc "$p" || true) processus (attendu : 1)"
done
tail -1 /tmp/watchdog_logs/gardien_securite.log || true
echo
echo "Qui publie maintenant sur /controller/cmd_vel (le gardien doit y être, plus nos 3 nœuds) :"
bash -c "$ROS; timeout 15 ros2 topic info -v /controller/cmd_vel | grep 'Node name'" || true
echo
echo "Retour arrière complet :"
echo "  cd $D && for f in $FICHIERS; do [ -f sauvegardes/\$f.$TS ] && cp sauvegardes/\$f.$TS \$f; done; pkill -f '[g]ardien_securite.py'; for p in '[p]ick_and_place_node_v6.py' '[a]utonomous_mission_node.py' '[l]lm_move_bridge_node.py'; do pkill -f \$p; done; bash start_watchdogs.sh"
echo "  (le watchdog relance ensuite les anciennes versions en moins d'une minute)"
