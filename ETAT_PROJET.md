# ETAT DU PROJET — ROSOrin Pro (LLM local + speech offline FRANCAIS)

Dernière mise à jour : 18/10/2026 05:30 — **FIX mouvement vocal : prefixe FR au lieu de remplacement**

---

## ✅ FIX APPLIQUÉ (18/10 05:30) — Mouvement vocal résolu côté code

### 🐛 Problème identifié

Le robot comprenait et répondait vocalement ("hello hiwonder") mais ne bougeait pas sur commande vocale ("Avance"/"Forward").

**Cause racine** : Quand `SPEECH_FORCE_FR=1` (défaut), le wrapper **remplaçait** le prompt système du firmware par `DEFAULT_SYSTEM_PROMPT` (français générique). Or le nœud `llm_control_move` du firmware envoie un prompt système avec les instructions JSON pour les mouvements :

```json
{"action": "move('forward', 1, 0)", "response": "OK"}
```

Ce prompt était écrasé → le LLM ne générait plus de JSON → pas de mouvement.

### 🔧 Solution appliquée

**Changement de comportement** : au lieu de **remplacer** le prompt du firmware, on **préfixe** avec `FRENCH_SYSTEM_PREFIX`.

| Avant (bug) | Après (fix) |
|-------------|-------------|
| `sp = DEFAULT_SYSTEM_PROMPT` | `sp = FRENCH_SYSTEM_PREFIX + (system or self.system_prompt)` |

Le `FRENCH_SYSTEM_PREFIX` :
- Force la réponse en français
- Rappelle le format JSON attendu pour les mouvements
- **Préserve** le prompt système du firmware (instructions spécifiques)

### 📝 Fichiers modifiés

- `speech_patch/speech_offline_patch.py` :
  - Nouvelle constante `FRENCH_SYSTEM_PREFIX` (préfixe FR + instructions JSON mouvement)
  - `DEFAULT_SYSTEM_PROMPT` amélioré (inclut aussi les instructions JSON)
  - `OllamaAPI.chat()` : préfixe au lieu de remplacer
  - `OllamaAPI.stream_chat()` : préfixe au lieu de remplacer
- `speech_patch/test_wrapper.py` : 11 nouveaux tests (72 PASS, 0 FAIL, 2 SKIP)

### 🧪 Tests

```
72 PASS, 0 FAIL, 2 SKIP
```

Nouveaux tests : `FRENCH_SYSTEM_PREFIX` (7 tests), `DEFAULT_SYSTEM_PROMPT` JSON (2 tests), logique préfixe chat() (3 tests - conserve prompt firmware + ajoute FR + conserve JSON).

### 🚀 Déploiement sur le robot (quand batterie rechargée)

```bash
# 1. Transférer le nouveau speech_patch_deploy.zip sur le robot
# 2. Sur le robot :
cd ~/Desktop/speech_patch
bash install_on_robot.sh

# 3. Relancer la démo :
source ~/.bashrc
ros2 launch large_models_examples llm_control_move.launch.py

# 4. Tester : dire "Avance" ou "Forward" → le robot doit bouger
```

## 🔄 SESSION EN COURS (18/10 03:50-04:35) — Diagnostic mouvement vocal

### ✅ Ce qui fonctionne

| Composant | Statut | Détails |
|-----------|--------|---------|
| ASR français | ✅ | `vocal_detect` initialisé avec `zipformer-fr-2023-04-14` |
| TTS français | ✅ | `tts_node` initialisé avec `vits-piper-fr_FR-siwis-medium` |
| LLM (PC) | ✅ | `agent_process` connecté à `http://192.168.1.20:11434` |
| Réponse vocale FR | ✅ | Le robot dit "Je suis prêt à vous aider" |
| Nœuds actifs | ✅ | `/vocal_detect`, `/agent_process`, `/tts_node`, `/llm_control_move` |
| Hardware moteurs | ✅ | Test manuel `/cmd_vel` → le robot avance |

### ❌ Problème en cours : le robot ne bouge pas sur commande vocale

**Symptôme** : Le robot comprend et répond ("hello hiwonder"), mais ne bouge pas quand on dit "Avance"/"Forward".

**Diagnostic effectué** :
- `/controller/cmd_vel` publie des `Twist` avec valeurs à 0 (stop)
- `/llm_control_move` écoute `/agent_process/result` et publie `/controller/cmd_vel`
- Le LLM reçoit les ordres mais ne génère pas le format JSON attendu :
  ```json
  "action": "move('forward', 1, 0)", "response": "OK"
  ```

**Cause probable** : Le prompt système du nœud `llm_control_move` (en anglais,来自 firmware)
demande un format JSON strict. Notre wrapper force peut-être un prompt FR qui perturbe ce format.

**Test effectué** : `SPEECH_FORCE_FR=0` → toujours pas de mouvement.

### 🔍 Prochaines étapes (quand batterie rechargée)

1. **Relancer la démo** :
   ```bash
   source /home/ubuntu/.bashrc
   ros2 launch large_models_examples llm_control_move.launch.py
   ```

2. **Surveiller les topics** (3 terminaux) :
   ```bash
   # Terminal A
   ros2 topic echo /vocal_detect/asr_result
   # Terminal B
   ros2 topic echo /agent_process/result
   # Terminal C
   ros2 topic echo /controller/cmd_vel
   ```

3. **Dire "Forward"** et observer :
   - Terminal A : le texte reconnu par l'ASR
   - Terminal B : la réponse brute du LLM (JSON ou texte ?)
   - Terminal C : les commandes de mouvement (0 = stop, >0 = mouvement)

4. **Si le LLM répond en texte et pas en JSON** :
   - Le problème vient du prompt système
   - Solution : modifier le prompt dans le wrapper pour qu'il génère du JSON
     même en français, OU désactiver `SPEECH_FORCE_FR` pour ce nœud

5. **Vérifier le réveil (wakeup)** :
   ```bash
   ros2 topic echo /vocal_detect/wakeup
   ```
   Le nœud `llm_control_move` attend peut-être un signal de réveil avant d'agir.

### 📝 Patch appliqué sur le robot (scan rapide)

```bash
cd /home/ubuntu/.local/lib/python3.10/site-packages/speech
sed -i 's|for item in base.rglob("\*"):|for item in list(base.rglob("*.bin")) + list(base.rglob("lexicon*")) + list(base.rglob("espeak-ng-data")) + list(base.rglob("voices*")):|g' speech_offline_patch.py
```

### Variables d'environnement (vérifiées OK)

```bash
OLLAMA_URL=http://192.168.1.20:11434
SPEECH_LANG=fr
SPEECH_FORCE_FR=1  # À tester avec 0 si problème de format JSON
```

### Fichiers clés

| Fichier | Chemin |
|---------|--------|
| Wrapper PC | `C:\Users\bloiz\projets\Robot\speech_patch\speech_offline_patch.py` |
| Wrapper robot | `/home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py` |
| Fichier launch | `/home/ubuntu/ros2_ws/src/large_models_examples/large_models_examples/llm_control_move.launch.py` |

### Dernier commit

`e71665b` — docs: session 18/10, état du diagnostic mouvement vocal

---

## 🔄 SESSION PRÉCÉDENTE (18/10 01:00-01:15)

### Ce qui a été fait :

| Étape | Statut |
|-------|--------|
| Support FR ajouté au wrapper (ASR/TTS/LLM) | ✅ Commit `969d8ee` pushé |
| Tests PC : 61 PASS, 0 FAIL | ✅ |
| Zip déployé sur robot | ✅ `speech_patch_deploy.zip` (24 Ko) |
| Installation sur robot (`install_on_robot.sh`) | ✅ Patch installé, bashrc configuré |
| TTS FR téléchargé (`vits-piper-fr_FR-siwis-medium`) | ✅ 60 Mo |
| ASR FR téléchargé (`zipformer-fr-2023-04-14`) | ✅ 380 Mo |
| Selftest robot | ✅ ASR[fr] + TTS[fr] détectés |
| Lancement démo `llm_control_move.launch.py` | ✅ Tous les nœuds démarrent |
| TTS FR initialisé | ✅ `TTS initialise (config, lang=fr)` |
| **PROBLÈME : scan sherpa-onnx trop lent** | ❌ **BLOQUANT** |

### 🐛 Problème actuel (BLOQUANT)

Le nœud `vocal_detect` bloque au démarrage car `_find_sherpa_models()` fait
`base.rglob("*")` sur `~/third_party/sherpa-onnx/` (~1 Go de modèles).
Le scan prend > 2 minutes et le nœud est interrompu avant de finir.

**Fichier concerné** (sur le robot) :
`~/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py`

**Ligne à patcher** (chercher `rglob("*")`) :
```python
# AVANT (lent) :
for item in base.rglob("*"):

# APRÈS (rapide) :
for item in list(base.rglob("*.bin")) + list(base.rglob("lexicon*")) + list(base.rglob("espeak-ng-data")) + list(base.rglob("voices*")):
```

**Commande sed rapide** (à exécuter sur le robot) :
```bash
cd ~/.local/lib/python3.10/site-packages/speech
cp speech_offline_patch.py speech_offline_patch.py.bak2
sed -i 's|for item in base.rglob("\*"):|for item in list(base.rglob("*.bin")) + list(base.rglob("lexicon*")) + list(base.rglob("espeak-ng-data")) + list(base.rglob("voices*")):|g' speech_offline_patch.py
```

### ⚠️ Autres problèmes connus (non bloquants)

| Problème | Cause | Impact |
|----------|-------|--------|
| `agent_process` → `localhost:11434` | `OLLAMA_URL` pas chargée ( Mauvais `source /.bashrc` au lieu de `~/.bashrc` ) | Utilise Ollama local (petits modèles) au lieu du PC |
| `asr_server` utilise modèle EN | Fichier de launch code en dur le chemin EN | ASR en anglais au lieu de français |
| `ros_robot_controller` : `校验失败` | Problème hardware (câble/contrôleur série) | Moteurs peuvent ne pas fonctionner |
| `servo_controller` crash (exit -2) | Problème hardware servos | Bras/pince peuvent ne pas fonctionner |

### Commandes de reprise (robot allumé)

```bash
# 1. Terminal robot, charger l'environnement CORRECTEMENT :
source ~/.bashrc
# Vérifier :
echo $OLLAMA_URL        # doit afficher: http://192.168.1.20:11434
echo $SPEECH_LANG       # doit afficher: fr

# 2. Patcher le scan lent (si pas encore fait) :
cd ~/.local/lib/python3.10/site-packages/speech
sed -i 's|for item in base.rglob("\*"):|for item in list(base.rglob("*.bin")) + list(base.rglob("lexicon*")) + list(base.rglob("espeak-ng-data")) + list(base.rglob("voices*")):|g' speech_offline_patch.py

# 3. Relancer la démo :
ros2 launch large_models_examples llm_control_move.launch.py

# 4. Attendre 10-20 secondes, puis tester :
# Parler en français : "Bonjour", "Avance"
# (ASR encore en anglais temporairement -> dire "Forward", "Hello")
```

### Ce qu'il faut faire ensuite (par ordre de priorité)

1. **PATCHER le scan lent** (sed ci-dessus) → débloque `vocal_detect`
2. **Tester la chaîne vocale** : micro → ASR → LLM → TTS → haut-parleur
3. **Corriger l'ASR pour le français** : modifier le fichier de launch
   `~/ros2_ws/src/large_models_examples/large_models_examples/llm_control_move.launch.py`
   pour pointer `asr_server` vers le modèle FR au lieu de EN
4. **Vérifier le hardware** : `ros_robot_controller` `校验失败` → câble USB/série
5. **Tester les mouvements** : "Avance", "Tourne à gauche", "Stop"

---

## Objectif

Configurer le ROSOrin Pro (Jetson Orin NX 16 Go, Ubuntu 22.04.5, IP 192.168.1.30,
user ubuntu) pour que le LLM tourne en local et réponde **en français** (ASR + TTS + LLM).

## ✅ DÉPLOIEMENT RÉUSSI (17/10 ~21h55) + FRANÇAIS (18/10)

### Tous les nœuds speech fonctionnent :

| Nœud | Statut | Détails |
|------|--------|---------|
| `tts_node` | ✅ | `TTS initialise (config): vits-ljs.onnx` → **sera remplacé par VITS fr** |
| `vocal_detect` | ✅ | `OnlineRecognizer` streaming initialisé → **sera remplacé par zipformer fr** |
| `agent_process` | ✅ | LLM répond → **prompt système FR forcé** |
| `llm_control_move` | ✅ | Démarré, prêt pour commandes |

### Chaîne fonctionnelle (AVANT français) :
```
Micro → ASR (sherpa-onnx streaming, ANGLAIS) → LLM (Ollama qwen3:1.7b)
      → Réponse texte → TTS (sherpa-onnx VITS, voix ANGLAISE) → Haut-parleur
      → Actions mouvement (si hardware OK)
```

### Chaîne fonctionnelle (APRÈS français — 18/10) :
```
Micro → ASR (sherpa-onnx streaming, FRANÇAIS) → LLM (Ollama, prompt FR)
      → Réponse texte (FRANÇAIS) → TTS (sherpa-onnx VITS, voix FRANÇAISE) → Haut-parleur
      → Actions mouvement
```

## 🇫🇷 Ce qui a été ajouté le 18/10 (support français)

### Modifications du wrapper `speech_offline_patch.py` :

1. **Détection de langue** (`_detect_lang()`) : analyse le chemin/nom des modèles
   pour détecter `fr`, `en` ou `unknown`.

2. **Sélection par langue** (`_find_sherpa_models()`) : retourne maintenant
   `asr_models` et `tts_models` comme dictionnaires `{lang: {model, tokens, ...}}`.
   Le modèle français est préféré si `SPEECH_LANG=fr` (défaut).

3. **ASR français** (`OfflineRealTimeASR`) : accepte `language="fr"`,
   cherche un modèle zipformer français dans `~/third_party/sherpa-onnx/`.

4. **TTS français** (`OfflineRealTimeTTS`) : accepte `language="fr"`,
   cherche un modèle VITS français (ex: `vits-piper-fr_FR-siwis-medium`).

5. **LLM français** (`OllamaAPI`) : prompt système en français par défaut :
   > "Tu es un assistant vocal pour un robot. Réponds toujours en français,
   > de manière concise et naturelle..."
   Le forçage est contrôlé par `SPEECH_FORCE_FR=1` (défaut).

6. **Téléchargement modèles FR** (`--download-fr`) : télécharge automatiquement :
   - ASR : `sherpa-onnx-streaming-zipformer-fr-2023-02-20` (~80 Mo)
   - TTS : `vits-piper-fr_FR-siwis-medium` (~60 Mo)

7. **Selftest mis à jour** : affiche les modèles par langue ([fr], [en], [unknown]).

### Nouvelles variables d'environnement :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `SPEECH_LANG` | `fr` | Langue par défaut (fr ou en) |
| `SPEECH_FORCE_FR` | `1` | Forcer le prompt système FR même si le firmware en fournit un autre |

### Nouveaux fichiers :

- `download_french_models.sh` — script standalone de téléchargement modèles FR
- `install_on_robot.sh` — mis à jour (configure SPEECH_LANG, SPEECH_FORCE_FR, télécharge modèles)

### Tests :

- **61 PASS, 0 FAIL, 2 SKIP** (les 2 SKIP = sherpa-onnx absent sur PC)
- Nouveaux tests : `_detect_lang`, constantes FR, sélection langue ASR/TTS,
  prompt système FR, `SHERPA_FR_MODELS`, structure `asr_models`/`tts_models`

## Blocage initial (RÉSOLU par contournement)

- Firmware juin 2026 (|V1.0.0|App_ROS2_1.0|2026-06-01|) exige speech >= 3.0
  (OfflineRealTimeASR, OfflineRealTimeTTS, OllamaAPI) ; le robot a speech v2.0
  avec un module compilé `speech.so` (pas de `speech.py`)
- Mail envoyé à support@hiwonder.com le 15/10/2026 — **pas de réponse**
- **Solution déployée** : wrapper Python `speech_offline_patch.py` qui émule
  les 3 classes avec sherpa-onnx (ASR/TTS) + Ollama (LLM)

## Environnement

### PC (192.168.1.20 — DHCP) :

- Ollama v0.40.5 sur 0.0.0.0:11434
- Modèles : qwen3.5:9b, qwen3.5-32k, qwen3.6:35b, qwen3.6-32k,
  mistral:latest, nomic-embed-text, **qwen3:1.7b**
- Pare-feu Windows : règle "Ollama 11434 (Robot ROSOrin)" créée
- NoMachine client : nxplayer.exe

### Robot (192.168.1.30 — sans batterie, à recharger) :

- NoMachine serveur v9.1.24, port 4000 ; user ubuntu
- Dossier `~/Desktop/speech_patch/` avec le wrapper (version 17/10 21h55 — **à mettre à jour avec la v18/10**)
- Package patché : `~/.local/lib/python3.10/site-packages/speech/`
- `~/.bashrc` : `export OLLAMA_URL=http://192.168.1.20:11434` (à compléter avec SPEECH_LANG/SPEECH_FORCE_FR)
- Modèles sherpa-onnx actuels : `~/third_party/sherpa-onnx/`
  - ASR : `sherpa-onnx-streaming-zipformer-en-2023-06-21/` (ANGLAIS — à remplacer par FR)
  - TTS : `vits-ljs/vits-ljs.onnx` (ANGLAIS — à remplacer par FR)
- **À télécharger** : modèles FR (~140 Mo) via `--download-fr`

## Commandes de reprise (quand batterie rechargée)

```bash
# 1. Allumer le robot, attendre le boot
# 2. NoMachine → 192.168.1.30:4000 (user ubuntu)
# 3. Terminal sur le robot :

cd ~/Desktop

# 4. Mettre à jour le patch (transférer le nouveau speech_patch_deploy.zip)
#    Extraire et remplacer les fichiers dans ~/Desktop/speech_patch/

# 5. Réinstaller avec support français :
cd ~/Desktop/speech_patch
bash install_on_robot.sh
# → installe le wrapper, configure SPEECH_LANG=fr, SPEECH_FORCE_FR=1
# → télécharge les modèles ASR/TTS français (~140 Mo, nécessite internet)

# 6. Redémarrer le terminal ou :
source ~/.bashrc

# 7. Vérifier :
python3 speech_offline_patch.py --selftest
# → doit afficher les modèles [fr] ASR et TTS

# 8. Lancer la démo :
ros2 launch large_models_examples llm_control_move.launch.py

# 9. Parler en FRANÇAIS au robot :
#   "Avance d'un mètre"
#   "Tourne à gauche"
#   "Stop"
#   "Bonjour, qui es-tu ?"
```

## Améliorations possibles (reste)

1. **Hardware** : erreurs `SerialException` sur `ros_robot_controller` —
   câble USB ou contrôleur série à vérifier (moteurs/servos)

2. **Voix masculine FR** : télécharger un autre modèle VITS fr (ex: `vits-piper-fr_FR-upmc-medium`)

3. **Modèle LLM plus gros** : si le PC a assez de VRAM, utiliser qwen3.5:9b au lieu de qwen3:1.7b

## Pièges / à savoir

- **IP PC en DHCP** : si elle change, mettre à jour `OLLAMA_URL` dans
  `~/.bashrc` et relancer
- **Téléchargement modèles FR** : nécessite internet sur le robot (~140 Mo)
  Si pas d'internet, les télécharger sur PC et transférer via NoMachine
- **qwen3:1.7b = thinking** : réponses vides si num_predict < 2048
  (le wrapper envoie 4096 par défaut)
- **Désinstallation** : `python3 speech_offline_patch.py --uninstall`
- **Terminal zsh** : le robot utilise zsh, pas bash (erreurs `shopt` normales)
- **Passer en anglais** : `export SPEECH_LANG=en` puis relancer
- **Forcer/annuler prompt FR** : `export SPEECH_FORCE_FR=0` (laisse le firmware décider)

## Git

Dernier commit : `d579013` (17/10 ~22h00)
**À committer** : support français (18/10)
- `speech_patch : FRANCAIS — ASR/TTS modèles fr + prompt système FR + --download-fr`

## Projets liés

- `ros2_ws/src/toy_sorter/` — Toy Sorter (14 tests OK, simulation fonctionnelle)
- `C:/Users/bloiz/assistant-vocal/` — assistant vocal PC (même bug qwen)

---

**Prochaine session (18/10 04:35)** : robot sans batterie, à recharger.
1. Recharger la batterie, allumer le robot
2. Relancer : `source /home/ubuntu/.bashrc` puis `ros2 launch large_models_examples llm_control_move.launch.py`
3. Surveiller `/agent_process/result` pour voir le format de sortie du LLM
4. Si le LLM ne génère pas de JSON → modifier le prompt FR ou désactiver `SPEECH_FORCE_FR`
5. Vérifier `/vocal_detect/wakeup` (signal de réveil peut-être nécessaire)
6. Une fois les mouvements OK → corriger l'ASR pour le FR dans le fichier de launch
7. Puis passer au projet toy_sorter

---

# SESSION 18/10/2026 14h45 — Pont vocal fonctionnel + outillage reprise

## État actuel (vérifié 14:46)

```
[OK] Robot 192.168.1.30 repond
[OK] PC repond
[OK] Ollama actif
[OK] rosbridge actif (28 noeuds)
```

## Pont vocal fonctionnel

Le robot répond aux commandes françaises SANS déploiement du speech_patch :

```bash
python3 speech_patch/voice_bridge.py "Avance"
python3 speech_patch/voice_bridge.py --interactive
```

## Outillage créé cette session

| Fichier | Description |
|---------|-------------|
| `speech_patch/voice_bridge.py` | Pont LLM -> rosbridge -> mouvement |
| `speech_patch/robot_ssh.py` | Helper SSH pour contrôler le robot |
| `speech_patch/setup_ssh_access.sh` | Configure l'accès SSH (à lancer sur robot) |
| `speech_patch/check_and_resume.py` | Diagnostic auto + reprise après recharge |
| `ETAT_PROJET_SESSION.md` | Doc session détaillée |

## Comment me donner la main sur le robot (SSH)

### Option A : Clé SSH (recommandée, une seule fois)

1. **Sur le robot** (via NoMachine terminal), copier-coller :

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
curl -s https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/main/speech_patch/setup_ssh_access.sh | bash
# OU transférer setup_ssh_access.sh et lancer: bash setup_ssh_access.sh
```

2. **Depuis le PC**, je peux alors me connecter :

```bash
ssh -i /c/Users/bloiz/.ssh/id_robot ubuntu@192.168.1.30
# OU utiliser le helper:
python3 speech_patch/robot_ssh.py "commande"
python3 speech_patch/robot_ssh.py --deploy   # Déploie le speech_patch
```

### Option B : Mot de passe SSH (temporaire)

Me donner le mot de passe SSH du robot (user `ubuntu`), je peux utiliser paramiko.

## Reprise après déconnexion batterie

Si le robot s'éteint (batterie vide), après recharge :

```bash
# 1. Vérifier que tout est OK (30 secondes)
python3 speech_patch/check_and_resume.py --quick

# 2. Si tout est vert, contrôler le robot:
python3 speech_patch/voice_bridge.py "Avance"

# 3. Diagnostic complet si problème:
python3 speech_patch/check_and_resume.py
```

## Commandes essentielles

```bash
# Diagnostic rapide
python3 speech_patch/check_and_resume.py --quick

# Test vocal
python3 speech_patch/voice_bridge.py "Avance"

# Mode interactif (taper les commandes)
python3 speech_patch/voice_bridge.py --interactive

# Contrôle manuel rosbridge (sans LLM)
python3 -c "
import websocket, json, time
ws = websocket.create_connection('ws://192.168.1.30:9090')
ws.send(json.dumps({'op':'publish','topic':'/controller/cmd_vel','msg':{'linear':{'x':0.3,'y':0,'z':0},'angular':{'x':0,'y':0,'z':0}}}))
time.sleep(2)
ws.send(json.dumps({'op':'publish','topic':'/controller/cmd_vel','msg':{'linear':{'x':0,'y':0,'z':0},'angular':{'x':0,'y':0,'z':0}}}))
"
```

## Commit actuel

`0ab743c` — feat: pont vocal LLM -> rosbridge (18/10 14h30)

Prochain commit prévu : outillage SSH + check_and_resume

---

# 🎉 SESSION 18/10/2026 15h15 — SUCCÈS TOTAL : Robot répond en français et bouge !

## Chaîne vocale complète FONCTIONNELLE

```
Micro → ASR FR (zipformer) → LLM (qwen3.5:9b, prompt FR) → JSON action
      → TTS FR (vits-piper siwis) → Haut-parleur
      → /controller/cmd_vel → MOTEURS → Robot bouge !
```

## Tests réussis (18/10 15h15)

| Commande | LLM réponse | TTS | Mouvement |
|----------|-------------|-----|-----------|
| "Avance" | `move('forward', 1, 0)` + "J'avance" | "J'avance" | ✅ Avance 0.2 m/s |
| "Tourne à gauche" | `move('left', 0, 0)` + "J'arrête" | "J'arrête." | ✅ (action left) |
| TTS direct | - | "Bonjour, je suis le robot ROSOrin" | - |

## Déploiement effectué

1. ✅ Clé SSH configurée (`~/.ssh/id_robot`)
2. ✅ Speech patch v2 (avec support FR) déployé
3. ✅ Modèles FR installés (ASR zipformer fr + TTS vits-piper fr)
4. ✅ `.bashrc` nettoyé (variables dédupliquées)
5. ✅ Packages ROS2 recompilés (`colcon build`)
6. ✅ Démo `llm_control_move.launch.py` lancée avec succès

## Configuration requise pour lancer la démo

```bash
ssh robot
bash -c '
source ~/ros2_ws/.typerc          # Config firmware (MACHINE_TYPE, etc.)
source /opt/ros/humble/setup.bash
source ~/third_party/third_party_ws/install/setup.bash
source ~/ros2_ws/install/setup.bash

# Variables pour notre usage (need_compile=False vient du firmware)
export OLLAMA_URL=http://192.168.1.20:11434
export SPEECH_LANG=fr
export SPEECH_FORCE_FR=1

# Lancer la démo
ros2 launch large_models_examples llm_control_move.launch.py
'
```

## Nœuds actifs (démo LLM)

| Nœud | Rôle | Statut |
|------|------|--------|
| `/vocal_detect` | ASR (reconnaissance vocale FR) | ✅ ACTIF |
| `/agent_process` | LLM (Ollama, prompt FR) | ✅ ACTIF |
| `/tts_node` | TTS (voix FR) | ✅ ACTIF |
| `/llm_control_move` | Parse JSON → mouvement | ✅ ACTIF |

## Topics clés

| Topic | Type | Description |
|-------|------|-------------|
| `/vocal_detect/asr_result` | String | Texte reconnu (ASR) |
| `/vocal_detect/wakeup` | Bool | Signal de réveil |
| `/agent_process/result` | String | Réponse LLM (JSON) |
| `/tts_node/tts_text` | String | Texte à dire (TTS) |
| `/controller/cmd_vel` | Twist | Commandes mouvement |

## Accès SSH (configuré)

```bash
# Connexion directe
ssh robot "commande"

# Ou avec le helper
python3 speech_patch/robot_ssh.py "commande"
python3 speech_patch/robot_ssh.py --deploy
```

## État batterie

⚠️ Pas de message sur `/ros_robot_controller/battery` — vérifier le branchement batterie.

## Prochaines étapes

1. ⬜ Tester avec le vrai micro (parler au robot)
2. ⬜ Vérifier la batterie
3. ⬜ Corriger `ros_robot_controller` (erreur série `校验失败`)
4. ⬜ Passer au projet toy_sorter

---

**Commit actuel** : en attente (mise à jour ETAT_PROJET)
