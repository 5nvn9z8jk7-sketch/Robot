#!/bin/bash
# maj_lidar.sh — Relance le programme du lidar (port /dev/lidar apparu après lui au boot)
# et installe le watchdog qui le surveille désormais (/scan_raw).
set -euo pipefail
D=/home/ubuntu/speech_patch
URL=https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-2-routeur/speech_patch
TS=$(date +%Y%m%d_%H%M%S)
ROS='source /opt/ros/humble/setup.bash; source /home/ubuntu/ros2_ws/install/setup.bash'
mkdir -p /tmp/maj_lidar "$D/sauvegardes" /tmp/watchdog_logs
for f in robot_watchdog.py lidar_sclidar.yaml; do curl -fsSL "$URL/$f?t=$TS" -o "/tmp/maj_lidar/$f"; done
python3 -m py_compile /tmp/maj_lidar/robot_watchdog.py
grep -q sclidar_scan_publisher /tmp/maj_lidar/robot_watchdog.py || { echo "ERREUR: version inattendue, rien n'est remplacé"; exit 1; }
for f in robot_watchdog.py lidar_sclidar.yaml; do [ -f "$D/$f" ] && cp "$D/$f" "$D/sauvegardes/$f.$TS"; cp "/tmp/maj_lidar/$f" "$D/$f"; done
echo "== Port du lidar =="; ls -l /dev/lidar
echo "== Relance du programme du lidar =="
pkill -f '[s]clidar_scan_publisher' || true
sleep 2
setsid nohup bash -c "$ROS; source /home/ubuntu/third_party/third_party_ws/install/setup.bash; exec /home/ubuntu/third_party/third_party_ws/install/sclidar_ros2/lib/sclidar_ros2/sclidar --ros-args -r __node:=sclidar_scan_publisher --params-file $D/lidar_sclidar.yaml -r /scan:=scan_raw" > /tmp/watchdog_logs/sclidar_scan_publisher.log 2>&1 < /dev/null &
sleep 6
echo "== Relance des superviseurs (nouveau watchdog) =="
bash "$D/start_watchdogs.sh"
echo "== Mesures =="
for t in /scan_raw /scan; do
  r=$(bash -c "$ROS; timeout 8 ros2 topic hz $t 2>/dev/null | grep -m1 average" || true)
  echo "  $t : ${r:-AUCUN}  (attendu ~10)"
done
tail -3 /tmp/watchdog_logs/sclidar_scan_publisher.log || true
echo "Retour arrière : cd $D && cp sauvegardes/robot_watchdog.py.$TS robot_watchdog.py && bash start_watchdogs.sh"
