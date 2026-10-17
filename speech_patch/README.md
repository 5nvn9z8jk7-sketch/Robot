# Patch offline pour le ROSOrin Pro — bibliothèque speech v2.0 -> classes v3.0

## Contexte

Le ROSOrin Pro (Jetson Orin NX, Ubuntu 22.04, IP 192.168.1.30) tourne avec le
firmware de juin 2026 (|V1.0.0|App_ROS2_1.0|2026-06-01|). Celui-ci exige la
bibliothèque Python "speech" en version >= 3.0 avec trois classes offline :
OfflineRealTimeASR, OfflineRealTimeTTS et OllamaAPI. Or le robot a la v2.0
installée — au lancement de la démo LLM offline, les nœuds plantent :

    AttributeError: module 'speech.speech' has no attribute 'OfflineRealTimeASR'
    AttributeError: module 'speech.speech' has no attribute 'OfflineRealTimeTTS'
    AttributeError: module 'speech.speech' has no attribute 'OllamaAPI'

Un mail a été envoyé au support Hiwonder (support@hiwonder.com) le 15/10/2026 à
22h16 pour demander le package speech >= 3.0. Pas de réponse à ce jour (16/10).
En attendant, ce dossier contient un wrapper qui émule les trois classes :

- OfflineRealTimeASR : reconnaissance vocale offline via sherpa-onnx (zipformer,
  déjà présent sur le robot dans ~/third_party/sherpa-onnx)
- OfflineRealTimeTTS : synthèse vocale offline via sherpa-onnx (VITS, idem)
- OllamaAPI : client HTTP vers le serveur Ollama du PC (LLM local)

## Architecture

    PC (192.168.1.20)            Robot (192.168.1.30)
    -------------------          ----------------------------------
    Ollama :11434                sherpa-onnx (ASR + TTS, déjà là)
    qwen3.5:9b, mistral...       ce patch (speech_offline_patch.py)
                                 micro + haut-parleur

    Flux : micro -> ASR (anglais) -> Ollama (LLM, réponse en français)
           -> TTS -> haut-parleur + mouvements du robot

## Fichiers

- speech_offline_patch.py — le wrapper (à transférer sur le robot, il s'installe tout seul)
- install_on_robot.sh — script de confort (appelle le --install du wrapper)
- test_wrapper.py — tests (à lancer sur le PC et/ou sur le robot)
- test_depuis_robot.sh — test de connectivité robot → PC (à lancer SUR le robot)
- autoriser_ollama_firewall.bat — règle pare-feu Windows (à lancer EN ADMIN sur le PC)
- README.md — ce fichier

## Déploiement sur le robot

Pas de mot de passe SSH connu -> déploiement manuel via NoMachine.

1. Sur le PC, ouvrir le client NoMachine (nxplayer.exe) et se connecter à
   192.168.1.30:4000 (utilisateur ubuntu).
2. Transférer le dossier "speech_patch" sur le robot (glisser-déposer dans la
   fenêtre NoMachine, par exemple sur le Bureau -> ~/Bureau/speech_patch).
3. Ouvrir un terminal sur le robot et taper :

    cd ~/Bureau/speech_patch
    bash install_on_robot.sh

   Le script fait tout :
   - copie le wrapper dans ~/.local/lib/python3.10/site-packages/speech/
   - sauvegarde speech.py et __init__.py (fichiers .bak)
   - branche l'import du wrapper à la fin de speech.py
   - vérifie dans un sous-processus que les 3 classes sont bien présentes

   Alternative en une seule commande :

    python3 ~/Bureau/speech_patch/speech_offline_patch.py --install

4. Vérifier le diagnostic :

    python3 ~/Bureau/speech_patch/speech_offline_patch.py --selftest

   Résultat attendu : les 3 classes OK, Ollama joignable avec la liste des
   modèles, modèles sherpa-onnx ASR et TTS trouvés.

5. Relancer la démo :

    ros2 launch large_models_examples llm_control_move.launch.py

   (avec ASR_MODE=offline comme avant)

6. Optionnel — valider ASR/TTS sur le robot :

    python3 ~/Bureau/speech_patch/test_wrapper.py

## Côté PC : rendre Ollama joignable depuis le robot

Ollama écoute déjà sur 0.0.0.0:11434 (vérifié le 17/10). Trois points de vigilance :

1. **Pare-feu Windows** : le profil privé bloque les entrées par défaut.
   Exécuter **en tant qu'administrateur** :

       speech_patch\autoriser_ollama_firewall.bat

   (clic droit → Exécuter en tant qu'administrateur)

2. **IP du PC** : le routeur attribue l'IP en DHCP. Aujourd'hui le PC est en
   192.168.1.20 (vérifié le 17/10, inchangé). Si l'IP change, le robot ne
   trouvera plus Ollama : relancer l'installation avec la nouvelle IP :

       python3 speech_offline_patch.py --install --ollama-url http://<NOUVELLE_IP>:11434

   ou définir la variable d'environnement OLLAMA_URL avant de lancer ROS.
   Pour éviter les surprises : réserver l'IP du PC dans le routeur (DHCP
   statique) ou lui mettre une IP fixe.

3. **Vérification depuis le robot** (avant d'installer le patch) :

       bash ~/Bureau/speech_patch/test_depuis_robot.sh

   Ce script teste : ping du PC, port 11434 ouvert, API Ollama, completion LLM.

## Piège : les modèles "thinking" (qwen3.x)

qwen3.5:9b est un modèle "thinking" : avec le budget de tokens par défaut
(~128), il dépense tout en réflexion interne et renvoie une réponse VIDE.
Le wrapper envoie toujours num_predict = 4096 par défaut — ne pas baisser
sous 2048 avec qwen3.x (validé par test : qwen3.5:9b répond "oui" avec 2048).
Si le robot est trop lent, utiliser mistral:latest :

    python3 speech_offline_patch.py --install --ollama-model mistral:latest

## Faire parler le robot en français

- L'ASR (zipformer-en) comprend l'ANGLAIS : donner les commandes en anglais.
- Le LLM répond dans la langue de son prompt système (fixé par le nœud du
  firmware). Pour un usage "chat", le wrapper accepte un prompt en français :

    from speech import speech
    llm = speech.OllamaAPI()
    llm.set_system_prompt("Tu es le ROSOrin Pro. Réponds toujours en français, brièvement.")
    reponse = llm.chat([{"role": "user", "content": "Bonjour, qui es-tu ?"}])

- La voix TTS (vits-ljs) est ANGLAISE : elle lira le français avec un accent.
  Pour une voix 100 % française, il faudra un modèle VITS français dans
  ~/third_party/sherpa-onnx (le wrapper détecte automatiquement les modèles
  présents dans ce dossier).

## Désinstallation

Sur le robot :

    python3 speech_offline_patch.py --uninstall

Cela restaure speech.py et __init__.py depuis les sauvegardes .bak et supprime
le wrapper du package. Les sauvegardes restent en place (fichiers .bak).

## Quand Hiwonder répondra

Installer proprement la v3.0 :

    pip3 install --user --upgrade "speech>=3.0"

Puis retirer ce patch (--uninstall) et supprimer speech_offline_patch.py du
dossier du package. Le wrapper est conçu pour ne pas entrer en conflit : il
n'écrase une classe que si elle est absente.

## Tests

Sur le PC (Ollama local requis) :

    cd C:/Users/bloiz/projets/Robot/speech_patch
    python3 test_wrapper.py

Dernier résultat (17/10) : 35 PASS, 0 FAIL, 2 SKIP (les 2 SKIP concernent
sherpa-onnx, absent du PC — à valider sur le robot).

