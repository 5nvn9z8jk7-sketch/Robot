#!/bin/bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "=== Topic info verbose: /vocal_detect/asr_result ==="
ros2 topic info -v /vocal_detect/asr_result 2>/dev/null

echo ""
echo "=== Test: publier et ecouter en meme temps ==="
echo "Lancement echo en arriere-plan..."
timeout 10 ros2 topic echo /vocal_detect/asr_result 2>/dev/null &
ECHO_PID=$!
sleep 1

echo "Publication test..."
ros2 topic pub --once /vocal_detect/asr_result std_msgs/msg/String "{data: 'avance'}" 2>&1

sleep 3
kill $ECHO_PID 2>/dev/null

echo ""
echo "=== Test: appeler le service get_chat de agent_process ==="
ros2 service call /agent_process/get_chat std_srvs/srv/Trigger 2>&1

echo ""
echo "=== Test: appeler init_finish ==="
ros2 service call /agent_process/init_finish std_srvs/srv/Empty 2>&1

echo ""
echo "=== agent_process est-il bloque? Check CPU ==="
ps aux | grep agent_process | grep -v grep

echo ""
echo "=== Threads de agent_process ==="
PID=$(ps aux | grep "agent_process" | grep -v grep | awk '{print $2}' | head -1)
if [ -n "$PID" ]; then
    echo "PID: $PID"
    cat /proc/$PID/status 2>/dev/null | grep -E "Threads|State"
    ls /proc/$PID/task/ 2>/dev/null | wc -l
    echo "Stack:"
    cat /proc/$PID/wchan 2>/dev/null
    echo ""
    # Check if process is in uninterruptible sleep (D state = blocked on IO)
    ps -o pid,stat,wchan:30,cmd -p $PID 2>/dev/null
fi
