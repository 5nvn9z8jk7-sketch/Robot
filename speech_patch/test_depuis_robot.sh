#!/bin/bash
# test_depuis_robot.sh - A EXECUTER SUR LE ROBOT (terminal NoMachine, user ubuntu)
# Verifie que le robot peut atteindre Ollama sur le PC avant d'installer le patch.
#
# Usage : bash test_depuis_robot.sh [OLLAMA_URL]
# Defaut : http://192.168.1.20:11434

OLLAMA_URL="${1:-http://192.168.1.20:11434}"

echo "=== Test connectivite robot -> PC (Ollama) ==="
echo "URL testee : $OLLAMA_URL"
echo ""

echo "--- 1. Ping du PC ---"
ping -c 2 -W 2 192.168.1.20 || echo "PING ECHOUE"
echo ""

echo "--- 2. Port 11434 ouvert ? ---"
if command -v nc &>/dev/null; then
    nc -zv -w 3 192.168.1.20 11434 && echo "PORT 11434 OUVERT" || echo "PORT 11434 FERME/BLOQUE"
elif command -v telnet &>/dev/null; then
    timeout 3 telnet 192.168.1.20 11434 </dev/null && echo "PORT OUVERT" || echo "PORT FERME"
else
    echo "(nc/telnet absent, test HTTP direct)"
fi
echo ""

echo "--- 3. API Ollama repond ? ---"
REPONSE=$(curl -s --max-time 5 "$OLLAMA_URL/api/tags" 2>/dev/null)
if [ -n "$REPONSE" ]; then
    echo "Ollama repond :"
    echo "$REPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print('  Modeles:', ', '.join(m['name'] for m in d.get('models',[])))" 2>/dev/null || echo "  $REPONSE" | head -c 200
else
    echo "ECHEC : pas de reponse de Ollama"
    echo "Verifiez :"
    echo "  - Le PC est allume et sur le meme reseau (192.168.1.20)"
    echo "  - Ollama tourne sur le PC (ollama serve)"
    echo "  - Le pare-feu Windows autorise le port 11434 en entree"
    echo "    (executer autoriser_ollama_firewall.bat en admin sur le PC)"
fi
echo ""

echo "--- 4. Test completion LLM (3 tokens) ---"
curl -s --max-time 15 "$OLLAMA_URL/api/generate" \
    -d '{"model":"qwen3.5:9b","prompt":"Dis bonjour en un mot.","stream":false,"options":{"num_predict":10}}' \
    2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('  Reponse:', d.get('response','(vide)')[:100])" 2>/dev/null || echo "  (test LLM ignore)"

echo ""
echo "=== Fin du test ==="
