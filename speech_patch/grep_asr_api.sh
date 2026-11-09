#!/bin/bash
echo "=== OfflineRealTimeASR class ==="
grep -n "class OfflineRealTimeASR" /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py

echo ""
echo "=== Methodes de OfflineRealTimeASR ==="
awk '/class OfflineRealTimeASR/,/^class [A-Z]/' /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py | grep -n "def \|pyaudio\|PyAudio\|sample_rate\|channels\|device_index\|record_audio\|mic_index\|SHERPA\|sherpa\|asr_model\|tokens" | head -40

echo ""
echo "=== Section __init__ de OfflineRealTimeASR ==="
awk '/class OfflineRealTimeASR/,/def asr/' /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py | head -80

echo ""
echo "=== Section asr() de OfflineRealTimeASR ==="
awk '/class OfflineRealTimeASR/,/^class [A-Z]/' /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py | awk '/def asr/,/def [a-z]/' | head -60

echo ""
echo "=== record_audio dans speech module ==="
grep -rn "def record_audio\|def play_audio" /home/ubuntu/.local/lib/python3.10/site-packages/speech/__init__.py 2>/dev/null | head -10

echo ""
echo "=== speech module init ==="
head -50 /home/ubuntu/.local/lib/python3.10/site-packages/speech/__init__.py
