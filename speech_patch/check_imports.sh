#!/bin/bash

echo "=== Imports dans vocal_detect.py ==="
head -30 /home/ubuntu/ros2_ws/src/large_models/large_models/large_models/vocal_detect.py

echo ""
echo "=== Chercher le module awake ==="
find /home/ubuntu -name "awake" -type d 2>/dev/null | head -5
find /home/ubuntu -name "awake.py" 2>/dev/null | head -5
find /home/ubuntu/ros2_ws/install -path "*awake*" 2>/dev/null | head -10

echo ""
echo "=== Python path - chercher awake ==="
python3 -c "import awake; print(awake.__file__)" 2>&1 || echo "awake module not found in python path"

echo ""
echo "=== Chercher dans site-packages ==="
find /home/ubuntu/.local/lib -name "awake*" 2>/dev/null | head -10
find /usr/lib/python3 -name "awake*" 2>/dev/null | head -5

echo ""
echo "=== xf_mic_asr_offline awake ==="
grep -rn "WonderEchoPro\|class.*awake\|class.*Wakeup\|class.*KWS" /home/ubuntu/ros2_ws/src/xf_mic_asr_offline/ 2>/dev/null | head -20

echo ""
echo "=== Chercher dans le package speech ==="
find /home/ubuntu/.local/lib/python3.10/site-packages/speech -name "*.py" 2>/dev/null | head -20
grep -rn "WonderEchoPro\|class.*awake" /home/ubuntu/.local/lib/python3.10/site-packages/speech/ 2>/dev/null | head -20
