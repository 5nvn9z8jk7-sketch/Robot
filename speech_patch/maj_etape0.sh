#!/bin/bash
# maj_etape0.sh — Installe sur le robot les 2 fichiers corrigés de l'étape 0 :
#   - pick_and_place_node_v6.py : arrêt d'urgence (« stop », touche 0/ESPACE),
#                                 rotation en boucle odométrie, déclencheurs resserrés
#   - robot_watchdog.py         : pkill avec motif entre crochets (plus d'auto-arrêt)
#
# Sécurités :
#   - sauvegarde des versions actuelles dans ~/speech_patch/sauvegardes/
#   - vérifie la syntaxe AVANT de remplacer quoi que ce soit
#   - s'arrête à la première erreur (rien n'est remplacé à moitié)
#
# Depuis le PC (PowerShell) :
#   ssh robot "curl -fsSL https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-0-menage/speech_patch/maj_etape0.sh | bash"
#
# Retour arrière (affiché aussi à la fin) :
#   cp ~/speech_patch/sauvegardes/<fichier>.<date> ~/speech_patch/<fichier>

set -euo pipefail
D=/home/ubuntu/speech_patch
URL=https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-0-menage/speech_patch
TS=$(date +%Y%m%d_%H%M%S)
FICHIERS="pick_and_place_node_v6.py robot_watchdog.py"

echo "== 1/4 Téléchargement + vérification de syntaxe =="
mkdir -p /tmp/maj_etape0
for f in $FICHIERS; do
  curl -fsSL "$URL/$f" -o "/tmp/maj_etape0/$f"
  python3 -m py_compile "/tmp/maj_etape0/$f"
  echo "  OK $f"
done

echo "== 2/4 Sauvegarde puis remplacement =="
mkdir -p "$D/sauvegardes"
for f in $FICHIERS; do
  cp "$D/$f" "$D/sauvegardes/$f.$TS"
  cp "/tmp/maj_etape0/$f" "$D/$f"
  echo "  $f remplacé (ancien : sauvegardes/$f.$TS)"
done

echo "== 3/4 Relance des superviseurs (nouveau watchdog) =="
bash "$D/start_watchdogs.sh"

echo "== 4/4 Relance du pick v6 =="
pkill -f '[p]ick_and_place_node_v6.py' || true
sleep 2
setsid nohup bash -c 'source /opt/ros/humble/setup.bash; source /home/ubuntu/ros2_ws/install/setup.bash; exec python3 -u /home/ubuntu/speech_patch/pick_and_place_node_v6.py' \
  > /tmp/pick_v6.log 2>&1 < /dev/null &
sleep 8
N=$(pgrep -fc '[p]ick_and_place_node_v6.py' || true)
echo "  processus pick v6 en cours : $N (attendu : 1)"
tail -3 /tmp/pick_v6.log || true

echo
echo "Terminé. Retour arrière si besoin :"
for f in $FICHIERS; do echo "  cp $D/sauvegardes/$f.$TS $D/$f"; done
