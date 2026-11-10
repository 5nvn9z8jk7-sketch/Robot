#!/bin/bash
# maj_gardien.sh — Met à jour uniquement le gardien de sécurité (2 fichiers) et le relance.
# Sauvegarde, vérification de syntaxe, arrêt à la première erreur.
set -euo pipefail
D=/home/ubuntu/speech_patch
URL=https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-1-securite/speech_patch
TS=$(date +%Y%m%d_%H%M%S)
FICHIERS="securite_logique.py gardien_securite.py voix_rapide.py"
ROS='source /opt/ros/humble/setup.bash; source /home/ubuntu/ros2_ws/install/setup.bash'
mkdir -p /tmp/maj_gardien "$D/sauvegardes" /tmp/watchdog_logs
for f in $FICHIERS; do
  curl -fsSL "$URL/$f" -o "/tmp/maj_gardien/$f"
  python3 -m py_compile "/tmp/maj_gardien/$f"
done
grep -q VoixRapide /tmp/maj_gardien/gardien_securite.py || { echo "ERREUR: version inattendue (cache GitHub ?), rien n'est remplacé"; exit 1; }
for f in $FICHIERS; do [ -f "$D/$f" ] && cp "$D/$f" "$D/sauvegardes/$f.$TS"; cp "/tmp/maj_gardien/$f" "$D/$f"; done
echo "Fichiers remplacés (anciens : sauvegardes/*.$TS)"
pkill -f '[g]ardien_securite.py' || true
sleep 2
setsid nohup bash -c "$ROS; exec python3 -u $D/gardien_securite.py" > /tmp/watchdog_logs/gardien_securite.log 2>&1 < /dev/null &
sleep 8
echo "gardien : $(pgrep -fc '[g]ardien_securite.py' || true) processus (attendu : 1)"
tail -1 /tmp/watchdog_logs/gardien_securite.log || true
echo "Retour arrière : cd $D && for f in $FICHIERS; do cp sauvegardes/\$f.$TS \$f; done; pkill -f '[g]ardien_securite.py'"
