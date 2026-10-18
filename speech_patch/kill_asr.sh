#!/bin/bash
# Tuer tous les processus simple_asr_node
for pid in $(ps aux | grep simple_asr_node | grep -v grep | awk '{print $2}'); do
    kill -9 "$pid" 2>/dev/null
done
sleep 2
if ps aux | grep simple_asr_node | grep -v grep > /dev/null; then
    echo "ENCORE ACTIF:"
    ps aux | grep simple_asr_node | grep -v grep
else
    echo "CLEAN - tous les processus simple_asr_node sont arretes"
fi
