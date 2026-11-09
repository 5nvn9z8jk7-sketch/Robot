#!/bin/bash
# Lance le pont LLM -> mouvement (remplace llm_control_move_offline bloque)
# A executer sur le robot

# Tuer l'ancien llm_control_move qui bloque
for pid in $(ps aux | grep "llm_control_move_offline" | grep -v grep | awk '{print $2}'); do
    echo "Kill llm_control_move PID $pid"
    kill -9 "$pid" 2>/dev/null
done
sleep 1

# Copier le bridge s'il n'existe pas ou est different
BRIDGE_SRC="$HOME/Desktop/speech_patch/llm_move_bridge_node.py"
BRIDGE_DST="$HOME/llm_move_bridge_node.py"

if [ -f "$BRIDGE_SRC" ]; then
    cp "$BRIDGE_SRC" "$BRIDGE_DST"
fi

# Lancer le bridge
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash 2>/dev/null

nohup python3 "$BRIDGE_DST" > ~/llm_bridge.log 2>&1 &
echo "LLM Bridge PID: $!"

sleep 3
echo "--- llm_bridge.log ---"
tail -10 ~/llm_bridge.log
