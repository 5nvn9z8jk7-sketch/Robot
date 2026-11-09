# 🤖 Robot Hiwonder — Système Autonome Complet

## Vue d'ensemble

Le robot est maintenant **entièrement autonome**. Tu lui donnes un ordre vocal, il exécute la mission complète sans intervention.

```
┌─────────────────────────────────────────────────────────┐
│                    INTERFACE WEB                         │
│         http://localhost:8888/robot_keypad.html          │
│  (Clavier numérique + Joystick + Boutons mission)       │
├─────────────────────────────────────────────────────────┤
│  🐕 WATCHDOG          Surveille et répare auto (10s)     │
│  🤖 MISSION NODE      Exécute les missions autonome      │
│  📷 PICK v4           Caméra depth + scan 360°          │
│  🎤 ASR + 🗣️ TTS      Reconnaissance + synthèse vocale  │
│  🧠 LLM (Ollama)      Compréhension des ordres          │
│  🚗 MOTEURS           ros_robot_controller              │
├─────────────────────────────────────────────────────────┤
│                    ROBOT (192.168.1.30)                  │
└─────────────────────────────────────────────────────────┘
```

---

## 🎮 Commandes disponibles

### Mode manuel (interface web)

| Touche | Action |
|--------|--------|
| `Z Q S D` / `↑←↓→` | Déplacer (avancer/gauche/reculer/droite) |
| `0-9` | Commandes numérotées prédéfinies |
| `P` | Attraper 1 cube (direct, devant) |
| `C` | Scan 360° + attraper |
| `ESPACE` | Stop urgence |

### Mode autonome (missions)

| Touche | Commande vocale | Description |
|--------|-----------------|-------------|
| `M` | **"Mission attrape tous les cubes"** | Scan 360°, attrape chaque cube un par un (max 10) |
| `R` | **"Patrouille"** | Avance, tourne, scanne pendant 2 minutes |
| `B` | **"Retourne à la base"** | Revient au point de départ (odométrie) |
| `S` | **"Status"** | Annonce batterie, position, mission en cours |
| `ESPACE` | **"Stop"** | Annule la mission en cours |

### Commandes vocales naturelles

Tu peux aussi parler directement au robot (micro PC) :

| Dire | Action |
|------|--------|
| "Attrape le cube rouge" | Pick-and-place direct |
| "Cherche le cube" | Scan 360° + attrape |
| "Mission attrape tous les cubes" | Mission complète multi-cubes |
| "Patrouille" | Patrouille 2 min |
| "Retourne à la base" / "Va charger" | Retour base |
| "Status" / "Où en es-tu ?" | Rapport vocal |
| "Stop" / "Arrête" | Arrêt immédiat |
| "Bonjour" / "Qui es-tu ?" | Salutations |

---

## 🐕 Watchdog (auto-réparation)

Vérifie **toutes les 10 secondes** :

| Priorité | Composant | Action si tombé |
|----------|-----------|-----------------|
| 🔴 Critique | Moteurs (`ros_robot_controller`) | Redémarre |
| 🔴 Critique | WebSocket (`rosbridge`) | Redémarre |
| 🔴 Critique | Bras (`servo_controller`) | Redémarre |
| 🟡 Important | Caméra depth (`aurora`) | Redémarre |
| 🟡 Important | Pick-and-place v4 | Redémarre |
| 🟡 Important | ASR / TTS / LLM | Redémarre |
| 🟢 Normal | Odométrie | Redémarre |

- **Max 5 redémarrages** par composant (évite boucle infinie)
- **Logs** : `ssh robot "tail -f /tmp/watchdog.log"`
- **Autostart** : démarre automatiquement au boot du robot

---

## 🤖 Missions autonome

### Mission "Attrape tous les cubes"

```
1. 🔍 Scan 360° → trouve un cube rouge
2. 🎯 Se tourne vers le cube
3. 📏 Mesure distance (caméra depth, précision ±2cm)
4. 🚶 Avance/recule jusqu'à 18cm du cube
5. 🤏 Bras attrape le cube
6. 🚶 Recule avec le cube
7. 🔍 Cherche le cube suivant...
8. 🏁 Répète jusqu'à 10 cubes ou plus de cube
```

**Feedback vocal à chaque étape** :
- "Je cherche un cube..."
- "J'ai trouvé le cube !"
- "Je me tourne vers le cube."
- "J'attrape le cube !"
- "Cube 1 attrapé ! 9 restant."
- "Mission terminée ! 5 cubes attrapés."

### Gestion batterie intelligente

| Niveau | Action |
|--------|--------|
| > 20% | Mission normale |
| 10-20% | "Batterie faible, je retourne à la base" → annule mission → retour base |
| < 10% | "Batterie critique ! Arrêt d'urgence" → stop immédiat |

### Retry automatique

Si un cube n'est pas attrapé : **3 tentatives** avant de passer au suivant.

---

## 🕹️ Joystick virtuel

Dans l'interface web, un **joystick tactile** permet de conduire le robot :

```
    🐢    ⬆️    🐇     ← ralentir / avancer / accélérer

    ⬅️    ⏹️    ➡️     ← tourner / stop / tourner
```

- **Maintenir** un bouton = mouvement continu
- **Relâcher** = arrêt
- Boutons 🐢/🐇 = ajuster la vitesse

---

## 🚀 Démarrage rapide

### Après chaque recharge du robot :

1. **Double-clique** : `Bureau → Robot Hiwonder.bat`

   Cela fait automatiquement :
   - ✅ Vérifie le robot
   - ✅ Lance les moteurs si besoin
   - ✅ Déploie Pick-and-place v4 (depth)
   - ✅ Lance le nœud Mission autonome
   - ✅ Lance le Watchdog
   - ✅ Ouvre l'interface web

2. **Ouvre** : `http://localhost:8888/robot_keypad.html`

3. **Appuie sur M** (ou dis *"Mission attrape tous les cubes"*)

4. **Le robot fait tout tout seul !** 🤖

---

## 📁 Architecture des fichiers

```
speech_patch/
├── robot_keypad.html          Interface web complète
├── autonomous_mission_node.py Nœud mission autonome
├── pick_and_place_node_v4.py  Pick-and-place avec depth
├── robot_watchdog.py          Watchdog auto-réparation
├── deploy_mission.sh          Déploiement mission
├── deploy_pick_v4.sh          Déploiement pick v4
├── deploy_watchdog.sh         Déploiement watchdog
├── install_watchdog_autostart.sh  Autostart au boot
├── voice_bridge.py            Pont vocal LLM (CLI)
├── calibrate_pick.py          Calibration interactive
└── start_interface.bat        Lancement serveur web

Bureau/
├── Robot Hiwonder.bat         Lance TOUT (1 clic)
└── Calibrer Pick.bat          Calibration
```

---

## 🔧 Dépannage

| Problème | Solution |
|----------|----------|
| Robot ne bouge pas | Watchdog relance les moteurs. Vérifie: `ssh robot "ros2 node list \| grep ros_robot"` |
| Caméra ne marche pas | Watchdog relance aurora. Vérifie: `ssh robot "tail -f /tmp/watchdog.log"` |
| Mission bloquée | Dis "Stop" ou appuie ESPACE. Relance avec M. |
| Batterie faible | Le robot retourne auto à la base. Recharge-le. |
| Interface web inaccessible | Relance `Bureau → Robot Hiwonder.bat` |
| Voir tous les logs | `ssh robot "tail -f /tmp/{watchdog,mission,pick_v4,rrc}.log"` |

---

## 🎯 Résumé des capacités

| Capacité | Statut |
|----------|--------|
| Contrôle manuel (clavier/joystick) | ✅ |
| Commandes vocales FR | ✅ |
| Scan 360° + détection cube | ✅ |
| Pick-and-place avec caméra depth (±2cm) | ✅ |
| Mission multi-cubes autonome | ✅ |
| Patrouille autonome | ✅ |
| Retour base automatique | ✅ |
| Gestion batterie intelligente | ✅ |
| Watchdog auto-réparation | ✅ |
| Feedback vocal à chaque étape | ✅ |
| Interface web complète | ✅ |
| Raccourci 1-clic sur le bureau | ✅ |

**Le robot est prêt pour l'autonomie complète !** 🎉
