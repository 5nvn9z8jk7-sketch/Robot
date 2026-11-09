#!/bin/bash
echo "=== OllamaAPI dans le speech patch ==="
grep -n "class OllamaAPI\|num_predict\|api/generate\|v1/chat\|chat/completions\|def chat\|def stream_chat\|thinking\|OPENAI_API_KEY\|openai\|base_url\|OLLAMA_URL" /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py | head -40

echo ""
echo "=== Test Ollama avec num_predict eleve ==="
curl -s --connect-timeout 5 --max-time 30 http://192.168.1.20:11434/api/generate -d '{"model":"qwen3.5:9b","prompt":"Dis bonjour en francais","stream":false,"options":{"num_predict":4096}}' 2>&1 | python3 -c "import sys,json; d=json.load(sys.stdin); print('Response:', repr(d.get('response','')[:200]))" 2>&1

echo ""
echo "=== Test avec /v1/chat/completions (API OpenAI) ==="
curl -s --connect-timeout 5 --max-time 30 http://192.168.1.20:11434/v1/chat/completions -d '{"model":"qwen3.5:9b","messages":[{"role":"user","content":"Dis bonjour en francais"}],"max_tokens":4096,"stream":false}' 2>&1 | python3 -c "import sys,json; d=json.load(sys.stdin); msg=d.get('choices',[{}])[0].get('message',{}); print('Response:', repr(msg.get('content','')[:200]))" 2>&1
