#!/bin/bash

echo "=== Contenu modele FR ==="
ls -la /home/ubuntu/third_party/sherpa-onnx/sherpa-onnx-streaming-zipformer-fr-2023-04-14/

echo ""
echo "=== Contenu modele EN ==="
ls -la /home/ubuntu/third_party/sherpa-onnx/sherpa-onnx-streaming-zipformer-en-2023-06-21/

echo ""
echo "=== Launch file llm_control_move ==="
cat /home/ubuntu/ros2_ws/src/large_models_examples/launch/llm_control_move.launch.py 2>/dev/null

echo ""
echo "=== Launch params du vocal_detect (tmp) ==="
cat /tmp/launch_params_qrum6ooc 2>/dev/null

echo ""
echo "=== Config speech dans le package ==="
find /home/ubuntu/ros2_ws/src/large_models -name "*.py" -exec grep -l "sherpa\|asr_model\|model_dir\|zipformer" {} \; 2>/dev/null | head -10

echo ""
echo "=== speech_offline_patch.py - chercher le chemin du modele ==="
grep -n "sherpa\|model_dir\|zipformer\|model_path\|asr_model\|\.onnx" /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py 2>/dev/null | head -30
