#!/bin/bash
# Diagnostic camera aurora930 — LECTURE SEULE, ne modifie rien.
# Usage : bash ~/speech_patch/diag_camera.sh   -> resultat dans ~/diag_camera_<date>.txt
OUT=~/diag_camera_$(date +%Y%m%d_%H%M).txt
{
echo "=== Date / uptime ==="; date; uptime
echo; echo "=== Watchdogs camera actifs (il ne doit y en avoir QU'UN) ==="
ps -eo pid,etime,cmd | grep -E '[c]amera_watchdog|[c]amera_supervisor|[r]obot_watchdog|[a]urora930_node'
echo; echo "=== Mode puissance Jetson ==="; nvpmodel -q 2>/dev/null || sudo -n nvpmodel -q 2>/dev/null
echo; echo "=== Arbre USB (la camera doit etre sur un port 3.0 si possible : 5000M) ==="; lsusb -t; echo; lsusb
echo; echo "=== Port camera 1-2.2.1 : vitesse / gestion d'energie ==="
for f in product manufacturer speed bMaxPower power/control power/autosuspend_delay_ms; do
  printf '%-28s %s\n' "$f" "$(cat /sys/bus/usb/devices/1-2.2.1/$f 2>/dev/null)"; done
echo "autosuspend global : $(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null)"
echo; echo "=== Erreurs USB dans dmesg (deconnexions, resets, sous-alimentation) ==="
(dmesg 2>/dev/null || sudo -n dmesg) | grep -iE 'usb .*(disconnect|reset|over-current|error|unable|not accepting)|uvc|-71|-110|over-current|undervolt' | tail -40
echo "Nb deconnexions USB : $((dmesg 2>/dev/null || sudo -n dmesg) | grep -ic 'usb.*disconnect')"
echo; echo "=== Relances par l'ancien watchdog (watchdog.log) ==="
echo "pannes signalees : $(grep -c 'NE STREAM PAS' ~/watchdog.log 2>/dev/null)"; grep 'NE STREAM PAS' ~/watchdog.log 2>/dev/null | tail -10
echo; echo "=== Relances forcees par robot_watchdog ==="; ls -la ~/*/aurora_force_restart.log /tmp/*aurora_force* 2>/dev/null
echo; echo "=== Fin de aurora.log ==="; tail -40 ~/aurora.log 2>/dev/null
echo; echo "=== Evenements du nouveau superviseur ==="; tail -40 ~/camera_events.log 2>/dev/null
echo; echo "=== Temperature / alimentation (1 echantillon) ==="; timeout 3 tegrastats --interval 1000 2>/dev/null | head -1
} > "$OUT" 2>&1
echo "Diagnostic ecrit dans $OUT"; cat "$OUT"
