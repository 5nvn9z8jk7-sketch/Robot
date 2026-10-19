#!/bin/bash
# start_pick_place_demo.sh — Démarre la chaîne complète pick and place
# Usage: ssh robot "bash ~/start_pick_place_demo.sh"
#
# Lance dans l'ordre:
#   1. Tuer les nodes firmware qui interfèrent
#   2. Caméra depth Aurora 930
#   3. Configuration détection couleur rouge
#   4. pick_and_place_node + voice_pick_node
#   5. Vérification

set -e

source /opt/ros/humble/setup.bash 2>/dev/null
source ~/ros2_ws/install/setup.bash 2>/dev/null
source ~/third_party/third_party_ws/install/setup.bash 2>/dev/null
source ~/third_party/aurora_ws/install/setup.bash 2>/dev/null

export SPEECH_LANG=fr
export SPEECH_FORCE_FR=1
export DEPTH_CAMERA_TYPE=aurora
export need_compile=True

echo "=== 1. Kill firmware nodes ==="
pkill -f vocal_detect 2>/dev/null || true
pkill -f voice_control_move 2>/dev/null || true
pkill -f llm_control_move 2>/dev/null || true
pkill -f llm_control_move_offline 2>/dev/null || true
sleep 1

echo "=== 2. Caméra depth Aurora 930 ==="
if ros2 topic list 2>/dev/null | grep -q '/depth_cam/depth0/image_raw'; then
    echo "  Caméra déjà active"
else
    pkill -f aurora930_node 2>/dev/null || true
    pkill -f orbbec_camera 2>/dev/null || true
    sleep 1
    setsid ros2 launch peripherals depth_camera.launch.py depth_camera_name:=depth_cam > ~/aurora_cam.log 2>&1 < /dev/null &
    echo "  Lancement caméra..."
    for i in $(seq 1 15); do
        sleep 1
        if ros2 topic list 2>/dev/null | grep -q '/depth_cam/depth0/image_raw'; then
            echo "  Caméra prête (${i}s)"
            break
        fi
    done
fi

echo "=== 3. Configuration détection rouge ==="
ros2 service call /color_detect_node/set_param interfaces/srv/SetColorDetectParam "{data: [{color_name: \"red\", detect_type: \"rect\"}]}" 2>/dev/null | grep success || true
ros2 service call /color_detect_node/start std_srvs/srv/Trigger 2>/dev/null | grep success || true

echo "=== 4. Lancement pick_and_place + voice_pick ==="
pkill -f pick_and_place_node 2>/dev/null || true
pkill -f voice_pick_node 2>/dev/null || true
sleep 1
setsid python3 ~/pick_and_place_node.py > ~/pick_and_place.log 2>&1 < /dev/null &
setsid python3 ~/voice_pick_node.py > ~/voice_pick.log 2>&1 < /dev/null &
sleep 3

echo "=== 5. Vérification ==="
echo "Nodes actifs:"
ros2 node list 2>/dev/null | grep -E "(simple_asr|pick_and_place|voice_pick|llm_move_bridge|agent_process|tts_node|color_detect)" | sort

echo ""
echo "Topics caméra:"
ros2 topic list 2>/dev/null | grep depth_cam | sort

echo ""
echo "ASR publishers:"
ros2 topic info /vocal_detect/asr_result 2>/dev/null | grep "Publisher count"

echo ""
echo "=== Prêt ! ==="
echo "Dis 'attrape le cube rouge' au robot avec un cube rouge devant lui."
echo "Logs: ~/pick_and_place.log ~/voice_pick.log ~/simple_asr.log"
