#!/bin/bash
# maj_etape2.sh — Installe le routeur d'ordres (étape 2) sur le robot.
#   routeur_ordres.py + routeur_logique.py : seul programme qui comprend les phrases
#   llm_move_bridge_node.py (v4)           : exécute avance / recule / crabe / tourne
#   pick_and_place_node_v6.py, autonomous_mission_node.py : déclenchés par le routeur
#   robot_watchdog.py                      : surveille et relance aussi le routeur
# Sauvegarde, vérification de syntaxe de TOUS les fichiers avant de remplacer,
# arrêt à la première erreur.
set -euo pipefail
D=/home/ubuntu/speech_patch
URL=https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-2-routeur/speech_patch
TS=$(date +%Y%m%d_%H%M%S)
FICHIERS="voix_rapide.py routeur_logique.py routeur_ordres.py llm_move_bridge_node.py pick_and_place_node_v6.py autonomous_mission_node.py robot_watchdog.py"
NOEUDS="'[r]outeur_ordres.py' '[l]lm_move_bridge_node.py' '[p]ick_and_place_node_v6.py' '[a]utonomous_mission_node.py'"
ROS='source /opt/ros/humble/setup.bash; source /home/ubuntu/ros2_ws/install/setup.bash'

echo "== 1/5 Téléchargement + vérification =="
mkdir -p /tmp/maj_etape2
for f in $FICHIERS; do
  curl -fsSL "$URL/$f?t=$TS" -o "/tmp/maj_etape2/$f"
  python3 -m py_compile "/tmp/maj_etape2/$f"
done
grep -q "robot/ordre" /tmp/maj_etape2/pick_and_place_node_v6.py || { echo "ERREUR: version inattendue (cache GitHub ?), rien n'est remplacé"; exit 1; }
[ -f "$D/securite_logique.py" ] && [ -f "$D/voix_rapide.py" ] || { echo "ERREUR: étape 1 absente (securite_logique.py / voix_rapide.py)"; exit 1; }
echo "  OK ($FICHIERS)"

echo "== 2/5 IA locale du PC (Ollama) joignable depuis le robot ? =="
if curl -s -m 5 http://192.168.1.20:11434/api/tags | grep -q 'qwen3.5:9b'; then
  echo "  OK : Ollama répond, modèle qwen3.5:9b présent"
else
  echo "  ATTENTION : Ollama ne répond pas depuis le robot (PC éteint, pare-feu, ou Ollama n'écoute que localhost)."
  echo "  Le routeur fonctionne quand même pour toutes les phrases connues ; seules les phrases inconnues échoueront."
fi

echo "== 3/5 Sauvegarde + remplacement =="
mkdir -p "$D/sauvegardes"
for f in $FICHIERS; do
  [ -f "$D/$f" ] && cp "$D/$f" "$D/sauvegardes/$f.$TS"
  cp "/tmp/maj_etape2/$f" "$D/$f"
done
echo "  sauvegardes : $D/sauvegardes/*.$TS"

echo "== 4/5 Relance des superviseurs =="
bash "$D/start_watchdogs.sh"

echo "== 5/5 Relance du routeur, des déplacements, du pick et de la mission =="
export XDG_RUNTIME_DIR=/run/user/1000
for p in '[r]outeur_ordres.py' '[l]lm_move_bridge_node.py' '[p]ick_and_place_node_v6.py' '[a]utonomous_mission_node.py'; do
  pkill -f "$p" || true
done
sleep 2
mkdir -p /tmp/watchdog_logs
setsid nohup bash -c "$ROS; exec python3 -u $D/routeur_ordres.py" > /tmp/watchdog_logs/routeur_ordres.log 2>&1 < /dev/null &
setsid nohup bash -c "$ROS; exec python3 -u $D/llm_move_bridge_node.py" > /tmp/watchdog_logs/llm_move_bridge.log 2>&1 < /dev/null &
setsid nohup bash -c "$ROS; exec python3 -u $D/pick_and_place_node_v6.py" > /tmp/pick_v6.log 2>&1 < /dev/null &
setsid nohup bash -c "$ROS; exec python3 -u $D/autonomous_mission_node.py" > /tmp/mission.log 2>&1 < /dev/null &
sleep 12
for p in '[r]outeur_ordres.py' '[l]lm_move_bridge_node.py' '[p]ick_and_place_node_v6.py' '[a]utonomous_mission_node.py'; do
  echo "  $p : $(pgrep -fc "$p" || true) processus (attendu : 1)"
done
echo
echo "Qui écoute maintenant les phrases (/vocal_detect/asr_result) — attendu : routeur, gardien, pick (pour « stop » seulement) :"
bash -c "$ROS; timeout 15 ros2 topic info -v /vocal_detect/asr_result | grep 'Node name'" || true
echo "Qui reçoit les ordres (/robot/ordre) — attendu : llm_move_bridge, pick, mission :"
bash -c "$ROS; timeout 15 ros2 topic info -v /robot/ordre | grep 'Node name'" || true
echo
tail -3 /tmp/watchdog_logs/routeur_ordres.log || true
echo
echo "Retour arrière complet :"
echo "  cd $D && for f in $FICHIERS; do [ -f sauvegardes/\$f.$TS ] && cp sauvegardes/\$f.$TS \$f; done; for p in $NOEUDS; do pkill -f \"\$p\"; done; bash start_watchdogs.sh"
echo "  (le watchdog relance ensuite les anciennes versions en moins d'une minute ; le routeur, absent de l'ancien watchdog, reste arrêté)"
