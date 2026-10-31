#!/bin/bash

echo "=== Module awake ==="
find /home/ubuntu/ros2_ws -path "*/awake*" -name "*.py" 2>/dev/null | head -10
find /home/ubuntu/ros2_ws -name "awake.py" 2>/dev/null

echo ""
echo "=== Contenu awake.py (WonderEchoPro) ==="
find /home/ubuntu/ros2_ws -name "awake.py" -exec grep -n "class WonderEchoPro\|def __init__\|def start\|def wakeup\|port\|pyaudio\|PyAudio\|usb\|USB\|hw:" {} \; 2>/dev/null | head -40

echo ""
echo "=== Chercher WonderEchoPro dans tout le workspace ==="
grep -rn "class WonderEchoPro" /home/ubuntu/ros2_ws/src/ 2>/dev/null

echo ""
echo "=== Chercher le fichier awake complet ==="
find /home/ubuntu/ros2_ws -name "awake*" -type f 2>/dev/null | head -10
