#!/bin/bash

echo "=== llm_control_move.launch.py (source) ==="
cat /home/ubuntu/ros2_ws/src/large_models_examples/large_models_examples/llm_control_move.launch.py

echo ""
echo "=== llm_control_move.launch.py (install) ==="
cat /home/ubuntu/ros2_ws/install/large_models_examples/share/large_models_examples/large_models_examples/llm_control_move.launch.py 2>/dev/null

echo ""
echo "=== config.py - variables sherpa ==="
grep -n "sherpa_onnx_path\|offline_asr\|offline_punct\|ASR_LANGUAGE\|asr_model\|zipformer\|fr-\|en-" /home/ubuntu/ros2_ws/src/large_models/large_models/config.py 2>/dev/null | head -30

echo ""
echo "=== vocal_detect.py - section WonderEchoPro ==="
sed -n '50,70p' /home/ubuntu/ros2_ws/src/large_models/large_models/large_models/vocal_detect.py

echo ""
echo "=== vocal_detect.py - section wakeup/mode (120-210) ==="
sed -n '120,210p' /home/ubuntu/ros2_ws/src/large_models/large_models/large_models/vocal_detect.py
