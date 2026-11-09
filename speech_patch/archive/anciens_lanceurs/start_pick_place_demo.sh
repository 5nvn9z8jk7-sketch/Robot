#!/bin/bash
# start_pick_place_demo.sh — Démarre la chaîne complète pick and place
# Usage: ssh robot "bash ~/start_pick_place_demo.sh"
#
# Lance dans l'ordre:
#   1. Tuer les nodes firmware qui interfèrent
#   2. Caméra depth Aurora 930
#   3. TTS node (avec les bonnes variables d'environnement)
#   4. Configuration détection couleur rouge
#   5. pick_and_place_node + voice_pick_node + llm_move_bridge
#   6. Vérification

set -e

source /opt/ros/humble/setup.bash 2>/dev/null
source ~/ros2_ws/install/setup.bash 2>/dev/null
source ~/third_party/third_party_ws/install/setup.bash 2>/dev/null
source ~/third_party/aurora_ws/install/setup.bash 2>/dev/null
source ~/ros2_ws/.typerc 2>/dev/null

export SPEECH_LANG=fr
export SPEECH_FORCE_FR=1
export OLLAMA_URL=http://192.168.1.20:11434

echo "=== 1. Kill firmware nodes ==="
pkill -f vocal_detect 2>/dev/null || true
pkill -f voice_control_move 2>/dev/null || true
pkill -f llm_control_move 2>/dev/null || true
pkill -f llm_control_move_offline 2>/dev/null || true
sleep 1

echo "=== 2. Caméra depth Aurora 930 ==="
if ros2 topic info /depth_cam/depth0/image_raw 2>/dev/null | grep -q "Publisher count: 1"; then
    echo "  Caméra déjà active"
else
    pkill -9 -f aurora930_node 2>/dev/null || true
    pkill -9 -f camera_container 2>/dev/null || true
    pkill -9 -f depth_camera 2>/dev/null || true
    sleep 2
    setsid ros2 launch peripherals depth_camera.launch.py depth_camera_name:=depth_cam > ~/aurora_cam.log 2>&1 < /dev/null &
    echo "  Lancement caméra..."
    for i in $(seq 1 20); do
        sleep 1
        if ros2 topic info /depth_cam/depth0/image_raw 2>/dev/null | grep -q "Publisher count: 1"; then
            echo "  Caméra prête (${i}s)"
            break
        fi
    done
fi

echo "=== 3. TTS node ==="
pkill -9 -f tts_node 2>/dev/null || true
sleep 2
setsid python3 /home/ubuntu/ros2_ws/install/large_models/lib/large_models/tts_node --ros-args > ~/tts_node.log 2>&1 < /dev/null &
echo "  TTS lancé, attente chargement modèles..."
sleep 15

echo "=== 4. Configuration détection rouge ==="
ros2 service call /color_detect_node/set_param interfaces/srv/SetColorDetectParam "{data: [{color_name: \"red\", detect_type: \"rect\"}]}" 2>/dev/null | grep success || true
ros2 service call /color_detect_node/start std_srvs/srv/Trigger 2>/dev/null | grep success || true

echo "=== 5. Lancement nodes ==="
pkill -f pick_and_place_node 2>/dev/null || true
pkill -f voice_pick_node 2>/dev/null || true
pkill -f llm_move_bridge_node 2>/dev/null || true
sleep 1
setsid python3 -u /home/ubuntu/speech_patch/pick_and_place_node_v6.py > ~/pick_and_place.log 2>&1 < /dev/null &
setsid python3 ~/voice_pick_node.py > ~/voice_pick.log 2>&1 < /dev/null &
setsid python3 ~/llm_move_bridge_node.py > ~/llm_bridge.log 2>&1 < /dev/null &
sleep 3

echo "=== 6. Vérification ==="
echo "Nodes actifs:"
ros2 node list 2>/dev/null | grep -E "(simple_asr|pick_and_place|voice_pick|llm_move_bridge|agent_process|tts_node|color_detect)" | sort

echo ""
echo "Topics caméra:"
ros2 topic info /depth_cam/depth0/image_raw 2>/dev/null | grep "Publisher count"

echo ""
echo "ASR publishers:"
ros2 topic info /vocal_detect/asr_result 2>/dev/null | grep "Publisher count"

echo ""
echo "TTS node:"
ros2 node list 2>/dev/null | grep tts || echo "  (pas encore enregistré, attendre 10s de plus)"

echo ""
echo "=== Prêt ! ==="
echo "Dis 'attrape le cube rouge' au robot avec un cube rouge devant lui."
echo "Logs: ~/pick_and_place.log ~/voice_pick.log ~/tts_node.log"
