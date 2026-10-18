#!/bin/bash
# Redémarre proprement toute la chaîne vocale

echo "=== Arrêt de l'ancienne démo ==="
# Tuer le launch principal (tue tous les nœuds enfants)
for pid in $(ps aux | grep "ros2 launch large_models_examples" | grep -v grep | awk '{print $2}'); do
    echo "Kill launch PID $pid"
    kill -9 "$pid" 2>/dev/null
done
sleep 2

# Tuer les nœuds orphelins
for pid in $(ps aux | grep -E "agent_process|llm_control_move|tts_node|vocal_detect|asr_server|ollama_server" | grep -v grep | grep -v simple_asr | awk '{print $2}'); do
    echo "Kill orphelin PID $pid"
    kill -9 "$pid" 2>/dev/null
done
sleep 2

# Tuer simple_asr aussi
for pid in $(ps aux | grep "simple_asr_node" | grep -v grep | awk '{print $2}'); do
    echo "Kill simple_asr PID $pid"
    kill -9 "$pid" 2>/dev/null
done
sleep 1

echo ""
echo "=== Vérification: tout est arrêté ==="
ps aux | grep -E "agent_process|llm_control_move|tts_node|vocal_detect|simple_asr" | grep -v grep || echo "Tout est arrêté"

echo ""
echo "=== Démarrage de la nouvelle démo ==="
source ~/ros2_ws/.typerc
source /opt/ros/humble/setup.bash
source ~/third_party/third_party_ws/install/setup.bash
source ~/ros2_ws/install/setup.bash
export OLLAMA_URL=http://192.168.1.20:11434
export SPEECH_LANG=fr
export SPEECH_FORCE_FR=1

# Lancer la démo en arrière-plan
nohup ros2 launch large_models_examples llm_control_move.launch.py > ~/demo_launch.log 2>&1 &
echo "Launch PID: $!"

echo ""
echo "=== Démarrage de simple_asr ==="
nohup bash ~/start_simple_asr.sh > ~/simple_asr.log 2>&1 &
echo "ASR PID: $!"

echo ""
echo "=== Attente de 30s pour l'initialisation ==="
sleep 30

echo ""
echo "=== Vérification des nœuds ==="
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 node list 2>/dev/null | grep -E "simple_asr|agent_process|tts_node|llm_control|vocal_detect"

echo ""
echo "=== Logs de démarrage ==="
echo "--- demo_launch.log ---"
tail -20 ~/demo_launch.log
echo ""
echo "--- simple_asr.log ---"
tail -10 ~/simple_asr.log
