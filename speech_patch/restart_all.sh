#!/bin/bash
source /opt/ros/humble/setup.bash 2>/dev/null
source ~/ros2_ws/install/setup.bash 2>/dev/null
source ~/third_party/third_party_ws/install/setup.bash 2>/dev/null
source ~/third_party/aurora_ws/install/setup.bash 2>/dev/null
source ~/ros2_ws/.typerc 2>/dev/null
export SPEECH_LANG=fr
export SPEECH_FORCE_FR=1

# Kill old instances
pkill -f llm_move_bridge_node 2>/dev/null
pkill -f voice_pick_node 2>/dev/null
pkill -f pick_and_place_node 2>/dev/null
sleep 2

# Restart
setsid python3 ~/llm_move_bridge_node.py > ~/llm_bridge.log 2>&1 < /dev/null &
setsid python3 ~/voice_pick_node.py > ~/voice_pick.log 2>&1 < /dev/null &
setsid python3 ~/pick_and_place_node.py > ~/pick_and_place.log 2>&1 < /dev/null &
sleep 3

echo "=== Nodes ==="
ros2 node list 2>/dev/null | grep -E "(llm_move_bridge|voice_pick|pick_and_place|simple_asr|agent_process|tts_node|color_detect)"

echo ""
echo "=== Camera ==="
ros2 topic info /depth_cam/depth0/image_raw 2>/dev/null | grep "Publisher count"

echo ""
echo "=== ASR publishers ==="
ros2 topic info /vocal_detect/asr_result 2>/dev/null | grep "Publisher count"

echo ""
echo "=== Logs ==="
tail -2 ~/llm_bridge.log
tail -2 ~/voice_pick.log
tail -2 ~/pick_and_place.log
