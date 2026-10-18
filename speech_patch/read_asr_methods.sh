#!/bin/bash
echo "=== Toutes les methodes de OfflineRealTimeASR ==="
sed -n '298,600p' /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py | grep -n "def \|class " | head -30

echo ""
echo "=== Lines 400-500 (listen/asr methods) ==="
sed -n '400,550p' /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py

echo ""
echo "=== record_audio dans le package speech original ==="
find /home/ubuntu/large_models/speech_pkg -name "*.py" -exec grep -l "def record_audio" {} \; 2>/dev/null
find /home/ubuntu -path "*/speech/speech.py" 2>/dev/null | head -5
