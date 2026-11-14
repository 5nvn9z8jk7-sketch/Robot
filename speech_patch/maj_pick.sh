#!/bin/bash
# maj_pick.sh — Met à jour uniquement la saisie du cube (pick v6) ; le watchdog la relance.
# (Script à part : une commande ssh qui contient le nom du programme et un pkill
#  s'arrêtait elle-même — vu le 15/11.)
set -euo pipefail
D=/home/ubuntu/speech_patch
F=pick_and_place_node_v6.py
URL=https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-2-routeur/speech_patch
TS=$(date +%Y%m%d_%H%M%S)
curl -fsSL "$URL/$F?t=$TS" -o /tmp/pick_new.py
python3 -m py_compile /tmp/pick_new.py
# Outils de réglage partagés (survol, 16/11)
for G in pick_calib.py teach_pick_v6.py; do
  curl -fsSL "$URL/$G?t=$TS" -o "/tmp/new_$G"
  python3 -m py_compile "/tmp/new_$G"
done
grep -q VITESSE_FINE /tmp/pick_new.py || { echo "ERREUR: version inattendue, rien n'est remplacé"; exit 1; }
mkdir -p "$D/sauvegardes"
cp "$D/$F" "$D/sauvegardes/$F.$TS"
cp /tmp/pick_new.py "$D/$F"
for G in pick_calib.py teach_pick_v6.py; do
  [ -f "$D/$G" ] && cp "$D/$G" "$D/sauvegardes/$G.$TS"
  cp "/tmp/new_$G" "$D/$G"
done
cp "$D/pick_calib.json" "$D/sauvegardes/pick_calib.json.$TS" 2>/dev/null || true
echo "Installé (ancienne version : sauvegardes/$F.$TS)"
pkill -f '[p]ick_and_place_node_v6' || true
echo "Attente de la relance par le watchdog (jusqu'à 90 s)..."
for i in $(seq 1 18); do
  sleep 5
  if [ "$(pgrep -fc '[p]ick_and_place_node_v6' || true)" -ge 1 ]; then echo "Saisie relancée (après $((i*5)) s)"; exit 0; fi
done
echo "ATTENTION : pas relancée après 90 s"
