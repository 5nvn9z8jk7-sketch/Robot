#!/bin/bash

echo "=== Recherche modele FR sherpa ==="
find /home/ubuntu -name "*fr*" -path "*sherpa*" 2>/dev/null
find /home/ubuntu -name "*zipformer*fr*" 2>/dev/null
find /home/ubuntu -name "*french*" -path "*sherpa*" 2>/dev/null

echo ""
echo "=== Tous les modeles sherpa ==="
ls -la /home/ubuntu/third_party/sherpa-onnx/ 2>/dev/null

echo ""
echo "=== Contenu du repertoire models de large_models ==="
find /home/ubuntu/ros2_ws/src/large_models -name "*.onnx" 2>/dev/null | head -20
find /home/ubuntu/ros2_ws/src/large_models -type d -name "*model*" 2>/dev/null | head -10

echo ""
echo "=== Chercher model.bin / tokens.txt ==="
find /home/ubuntu -name "model.bin" -o -name "tokens.txt" 2>/dev/null | head -20

echo ""
echo "=== Paramètres du launch file ==="
find /home/ubuntu/ros2_ws/src/large_models_examples -name "llm_control_move*" 2>/dev/null
cat /home/ubuntu/ros2_ws/src/large_models_examples/launch/llm_control_move.launch.py 2>/dev/null | head -80
