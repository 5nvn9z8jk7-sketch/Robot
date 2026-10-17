# ETAT DU PROJET — ROSOrin Pro (LLM local + speech offline FRANCAIS)

Dernière mise à jour : 18/10/2026 01:15 — **EN COURS : test vocal FR sur robot**

---

## 🔄 SESSION EN COURS (18/10 01:00-01:15)

### Ce qui a été fait aujourd'hui :

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

**Prochaine session (18/10 01:15)** : robot allumé, démo en cours.
1. Patcher le scan lent (`sed` ci-dessus, section "Problème actuel")
2. Relancer `ros2 launch large_models_examples llm_control_move.launch.py`
3. Tester la voix (ASR anglais temporairement, TTS/LLM français)
4. Corriger l'ASR pour le français dans le fichier de launch
5. Vérifier le hardware (moteurs/servos)
