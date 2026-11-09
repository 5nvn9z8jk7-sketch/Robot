#!/bin/bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "=== Test 1: Verifier que agent_process recoit le message ==="
echo "Lancement de rosout en arriere-plan..."
timeout 20 ros2 topic echo /rosout --field msg 2>/dev/null | grep -i "agent_process\|thinking\|llm result" &
ROSOUT_PID=$!

sleep 2
echo "Publication de 'avance'..."
ros2 topic pub --once /vocal_detect/asr_result std_msgs/msg/String "{data: 'avance'}" 2>&1

echo "Attente de 15s pour la reponse LLM..."
sleep 15

kill $ROSOUT_PID 2>/dev/null

echo ""
echo "=== Test 2: Appel direct du LLM comme agent_process ==="
echo "Simulation de l'appel llm() avec prompt vide..."
python3 << 'PYEOF'
import os, sys
os.environ['OLLAMA_URL'] = 'http://192.168.1.20:11434'
os.environ['SPEECH_LANG'] = 'fr'
os.environ['SPEECH_FORCE_FR'] = '1'

from speech import speech
client = speech.OllamaAPI('http://192.168.1.20:11434', timeout=60)
print(f"Model: {client}")
# Simuler l'appel avec prompt vide (comme agent_process au debut)
res = client.llm('avance', '', model='qwen3.5:9b')
print(f"Resultat (prompt vide): '{res}'")
PYEOF

echo ""
echo "=== Test 3: Appel avec le prompt de llm_control_move ==="
python3 << 'PYEOF'
import os, sys
os.environ['OLLAMA_URL'] = 'http://192.168.1.20:11434'
os.environ['SPEECH_LANG'] = 'fr'
os.environ['SPEECH_FORCE_FR'] = '1'

from speech import speech
client = speech.OllamaAPI('http://192.168.1.20:11434', timeout=60)

# Chercher le prompt dans llm_control_move_offline
prompt = "Tu es un robot mobile. Quand on te demande de bouger, reponds en JSON: {\"action\": \"move('forward', 1, 0)\", \"response\": \"J'avance\"}"
res = client.llm('avance', prompt, model='qwen3.5:9b')
print(f"Resultat (avec prompt): '{res}'")
PYEOF
