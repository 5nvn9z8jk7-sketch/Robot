#!/bin/bash
echo "=== Methode listen() ==="
awk '/class OfflineRealTimeASR/,/^class [A-Z]/' /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py | awk '/def listen/,/def [a-z_]+\(/' | head -50

echo ""
echo "=== Methode start() ==="
awk '/class OfflineRealTimeASR/,/^class [A-Z]/' /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py | awk '/def start/,/def [a-z_]+\(/' | head -30

echo ""
echo "=== Methode asr() (ancienne API compat) ==="
awk '/class OfflineRealTimeASR/,/^class [A-Z]/' /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py | awk '/def asr\(/,/def [a-z_]+\(/' | head -30

echo ""
echo "=== record_audio dans speech.py ==="
find /home/ubuntu/.local/lib/python3.10/site-packages/speech -name "*.py" -exec grep -l "def record_audio" {} \;
grep -n "def record_audio" /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech.py 2>/dev/null | head -5
find /home/ubuntu/ros2_ws/src/large_models -name "speech.py" -exec grep -n "def record_audio\|def play_audio" {} \; 2>/dev/null | head -10

echo ""
echo "=== Chercher record_audio partout ==="
grep -rn "def record_audio" /home/ubuntu/.local/lib/python3.10/site-packages/speech/ 2>/dev/null | head -5
grep -rn "def record_audio" /home/ubuntu/ros2_ws/src/ 2>/dev/null | head -5

echo ""
echo "=== speech module - fonction record_audio ==="
python3 -c "from speech import speech; import inspect; print(inspect.getsource(speech.record_audio))" 2>&1 | head -40
