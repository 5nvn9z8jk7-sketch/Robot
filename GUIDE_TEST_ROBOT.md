# 🤖 Guide de test pas à pas — Robot Hiwonder ROSOrin Pro

> Dernière mise à jour : 25 octobre 2026

---

## 1️⃣ Vérifier que le robot est prêt

### Depuis le PC, vérifier la connectivité
```bash
# Ping le robot
ping 192.168.1.30

# SSH (doit répondre sans mot de passe)
ssh robot "echo 'Robot OK' && hostname"
```

### Sur le robot, vérifier ROS2
```bash
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && ros2 node list'"
```

Tu dois voir au minimum :
```
/ros_robot_controller
/odom_publisher
/rosbridge_websocket
```

---

## 2️⃣ Lancer la chaîne vocale complète

### Sur le robot (une seule fois)
```bash
ssh robot "bash ~/start_voice_chain.sh"
```

Attendre ~30 secondes. Vérifier que les nœuds sont actifs :
```bash
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && ros2 node list | grep -E \"(simple_asr|ws_audio|llm_move_bridge|tts_node|agent_process)\"'"
```

Résultat attendu :
```
/ws_audio_asr          ← ASR via WebSocket (micro PC)
/llm_move_bridge       ← Pont commandes vocales → mouvement
/tts_node              ← Synthèse vocale (réponses du robot)
/agent_process         ← LLM (Ollama sur PC)
```

### Sur le PC, lancer l'envoi du micro
```bash
cd C:\Users\bloiz\projets\Robot
python3 speech_patch/pc_mic_sender.py --duration 120
```

Tu dois voir :
```
Connecte au robot! Parle maintenant...
```

---

## 3️⃣ Tester les commandes vocales

Parle clairement dans le micro du PC. Commandes testées et fonctionnelles :

| Dire | Action | Réponse vocale |
|------|--------|---------------|
| **"Avance"** | Robot avance 2s | "J'avance" |
| **"Recule"** | Robot recule 2s | "Je recule" |
| **"Tourne à gauche"** | Robot tourne à gauche | "Je tourne à gauche" |
| **"Tourne à droite"** | Robot tourne à droite | "Je tourne à droite" |
| **"Stop"** / **"Arrête"** | Robot s'arrête | "J'arrête" |
| **"Bonjour"** | Salutation | "Bonjour ! Je suis le robot ROSOrin..." |
| **"Qui es-tu ?"** | Présentation | "Je suis le robot ROSOrin..." |
| **"Comment ça va ?"** | Conversation | "Ça va très bien, merci !" |
| **"Merci"** | Remerciement | "De rien !" |

---

## 4️⃣ Tester les moteurs manuellement (sans voix)

### Avancer 2 secondes
```bash
python3 -c "
import websocket, json, time
ws = websocket.create_connection('ws://192.168.1.30:9090')
# Avancer 0.3 m/s pendant 2s
for i in range(20):
    ws.send(json.dumps({'op':'publish','topic':'/controller/cmd_vel','msg':{'linear':{'x':0.3,'y':0,'z':0},'angular':{'x':0,'y':0,'z':0}}}))
    time.sleep(0.1)
# Stop
ws.send(json.dumps({'op':'publish','topic':'/controller/cmd_vel','msg':{'linear':{'x':0,'y':0,'z':0},'angular':{'x':0,'y':0,'z':0}}}))
ws.close()
print('Fait: avance 2s')
"
```

### Tourner à gauche 1 seconde
```bash
python3 -c "
import websocket, json, time
ws = websocket.create_connection('ws://192.168.1.30:9090')
for i in range(10):
    ws.send(json.dumps({'op':'publish','topic':'/controller/cmd_vel','msg':{'linear':{'x':0,'y':0,'z':0},'angular':{'x':0,'y':0,'z':1.0}}}))
    time.sleep(0.1)
ws.send(json.dumps({'op':'publish','topic':'/controller/cmd_vel','msg':{'linear':{'x':0,'y':0,'z':0},'angular':{'x':0,'y':0,'z':0}}}))
ws.close()
print('Fait: tourne gauche 1s')
"
```

### Arrêt d'urgence (toujours disponible)
```bash
python3 -c "
import websocket, json
ws = websocket.create_connection('ws://192.168.1.30:9090')
ws.send(json.dumps({'op':'publish','topic':'/controller/cmd_vel','msg':{'linear':{'x':0,'y':0,'z':0},'angular':{'x':0,'y':0,'z':0}}}))
ws.close()
print('STOP!')
"
```

---

## 5️⃣ Monitoring en temps réel

### Voir toute l'activité vocale (depuis le PC)
```bash
cd C:\Users\bloiz\projets\Robot
python3 speech_patch/monitor_asr.py 60
```

Affiche en direct :
- `[ASR]` — ce que le robot entend
- `[LLM]` — réponse du LLM
- `[TTS]` — ce que le robot dit
- `[MOVE]` — mouvements (AVANCE, RECULE, GAUCHE, DROITE)
- `[BATT]` — niveau batterie

### Voir les logs sur le robot
```bash
# Logs ASR (nœud WebSocket)
ssh robot "tail -f ~/ws_asr.log"

# Logs du bridge (mouvement + LLM)
ssh robot "tail -f ~/llm_bridge.log"

# Logs TTS
ssh robot "tail -f ~/tts_node.log"

# Logs LLM (agent_process)
ssh robot "tail -f ~/agent.log"
```

---

## 6️⃣ Tester la caméra et la détection

### Vérifier que la caméra depth fonctionne
```bash
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && ros2 topic hz /depth_cam/depth0/image_raw'"
```
Tu dois voir ~30 Hz.

### Voir l'image de la caméra (depuis le PC)
Ouvrir dans un navigateur : `http://192.168.1.30:8080`
(Choisir le stream caméra)

### Tester la détection de couleur
```bash
# Configurer la détection de rouge
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && ros2 service call /color_detect_node/set_param interfaces/srv/SetColorDetectParam \"{data: [{color_name: \\\"red\\\", detect_type: \\\"rect\\\"}]}\"'"

# Lancer la détection
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && ros2 service call /color_detect_node/start std_srvs/srv/Trigger'"

# Voir les résultats
ssh robot "bash -lc 'source /opt/ros/humble/setup.bash && ros2 topic echo /color_detect_node/roi --once'"
```

---

## 7️⃣ Tester le Pick-and-Place (attraper un objet)

> Nécessite : caméra depth + bras robotique + objet coloré (cube rouge)

### Lancer la démo complète
```bash
ssh robot "bash ~/start_pick_place_demo.sh"
```

### Dire la commande
Parle dans le micro PC :
> **"Attrape le cube rouge"**

Le robot doit :
1. Détecter le cube rouge avec la caméra
2. Se tourner vers le cube
3. Avancer jusqu'au cube
4. Baisser le bras et attraper
5. Se relever

### Logs pick-and-place
```bash
ssh robot "tail -f ~/pick_and_place.log"
```

---

## 8️⃣ Commandes de diagnostic rapide

### Tout vérifier en une commande
```bash
ssh robot "bash -lc '
source /opt/ros/humble/setup.bash
echo \"=== Noeuds vocaux ===\"
ros2 node list | grep -E \"(ws_audio|simple_asr|llm_move_bridge|tts_node|agent_process|pick_and_place)\"
echo \"\"
echo \"=== Topics ASR ===\"
ros2 topic info /vocal_detect/asr_result | grep \"Publisher count\"
echo \"\"
echo \"=== Batterie ===\"
ros2 topic echo /ros_robot_controller/battery --once
echo \"\"
echo \"=== Moteurs (test 1s) ===\"
timeout 2 ros2 topic pub /controller/cmd_vel geometry_msgs/Twist \"{linear: {x: 0.1}}\" -r 10 &
sleep 1
ros2 topic echo /odom --once | grep -A2 position
kill %1 2>/dev/null
ros2 topic pub /controller/cmd_vel geometry_msgs/Twist \"{linear: {x: 0}} -r 1 --once
'"
```

### Redémarrer proprement
```bash
# Tuer tous les nœuds vocaux
ssh robot "pkill -f 'ws_audio_asr|simple_asr|llm_move_bridge|tts_node|agent_process'; sleep 2"

# Relancer
ssh robot "bash ~/start_voice_chain.sh"
```

---

## 9️⃣ Tableau récapitulatif des ports

| Port | Service | Accès |
|------|---------|-------|
| 22 | SSH | `ssh robot` |
| 9090 | rosbridge WebSocket | `ws://192.168.1.30:9090` |
| 9092 | WebSocket ASR (micro PC) | `ws://192.168.1.30:9092` |
| 8080 | Web video server | `http://192.168.1.30:8080` |
| 4000 | Autre service | — |
| 11434 | Ollama (sur PC) | `http://192.168.1.20:11434` |

---

## 🔟 En cas de problème

| Symptôme | Cause probable | Solution |
|----------|---------------|----------|
| Robot ne répond pas au ping | Éteint ou WiFi coupé | Allumer le robot, vérifier le WiFi |
| `ssh robot` demande un mot de passe | Clé SSH perdue | `ssh-copy-id robot` ou utiliser l'IP directe |
| Pas de nœuds vocaux | Chaîne non lancée | `ssh robot "bash ~/start_voice_chain.sh"` |
| ASR ne transcrit rien | Micro PC pas branché | Vérifier le micro, relancer `pc_mic_sender.py` |
| Robot ne bouge pas | `voice_control_move` bloque | Le script `start_voice_chain.sh` le tue automatiquement |
| TTS ne parle pas | `tts_node` non lancé | Vérifier dans les nœuds ROS2 |
| LLM ne répond pas | Ollama PC éteint | `curl http://192.168.1.20:11434/api/tags` |

---

**Bon test !** 🎉
