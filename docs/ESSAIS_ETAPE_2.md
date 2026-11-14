# Étape 2 — Essais du routeur d'ordres

**Au premier résultat anormal : ESPACE, on s'arrête, on note, on ne continue pas.**

Commandes dans l'Invite de commandes (`cmd`), depuis `C:\Users\bloiz\projets\Robot`. Copier seulement les lignes qui commencent par `ssh`, `scp`, `git`, `cd`.

Robot au sol, 2 m libres devant, une main sur ESPACE, un mètre ruban.

## Ce qui change

- Un seul programme comprend les phrases : `routeur_ordres.py`. Le pick, la mission et le pont de déplacement ne cherchent plus leurs propres mots-clés : ils reçoivent un ordre déjà compris sur `/robot/ordre` et répondent sur `/robot/ordre/fin`.
- Grammaire fixe : avance / recule / décale-toi à gauche-droite (crabe) de X m ou cm, tourne à gauche-droite de X degrés, demi-tour, attrape le cube rouge, attrape tous les cubes, patrouille, état. Nombres en chiffres ou en lettres (« quatre-vingt-dix degrés », « un mètre cinquante »). Enchaînement avec « puis » (5 ordres au maximum).
- Limites : avance 3 m, recul 0,4 m (l'arrière n'est pas vu), crabe 1 m, rotation 1 tour. Au-delà : refus expliqué, rien ne bouge.
- Pas encore disponible (refus clair) : dépose dans le bac (étape 3), retour à la base et lieux (étape 4), pince seule, cubes d'une autre couleur.
- Phrase inconnue : l'IA locale du PC (Ollama) propose un plan, contrôlé par le routeur. Si le robot doit bouger, il dit « Je vais … Je lance ? » et attend « oui » (20 s).
- Distances mesurées par l'odométrie ; rotation encore chronométrée (précision à améliorer à l'étape 3).
- Si le gardien bloque le robot devant un obstacle plus de 1,5 s : « Je n'ai pas pu terminer : obstacle devant moi », la suite du plan est annulée.
- Page : zone de texte « Écris un ordre », bouton « Micro PC », ligne « Entendu / Compris / État ».

## G1 — Installation

```bat
git fetch
git checkout etape-2-routeur
git pull
scp speech_patch\maj_etape2.sh robot:/tmp/
ssh robot "sed -i 's/\r$//' /tmp/maj_etape2.sh && bash /tmp/maj_etape2.sh"
```

Attendu : `1 processus` pour les 4 programmes ; Ollama « OK » (sinon seules les phrases inconnues échouent) ; `/robot/ordre` reçu par `llm_move_bridge`, `pick_and_place_node_v6`, `autonomous_mission_node`.

Puis relancer `speech_patch\start_interface.bat` et recharger la page avec **Ctrl+F5**.

## G2 — Zone de texte

Écrire `avance de 30 cm`, Entrée. Attendu : « J'avance », ~30 cm au mètre ruban, « C'est fait ». La page affiche « Compris : avancer de 30 centimètres (grammaire) ».

## G3 — Rotation et crabe

`tourne à droite de 90 degrés`, puis `décale-toi à gauche de 20 cm`. Noter l'angle réellement fait (chronométré).

## G4 — Enchaînement

`avance de 30 cm puis tourne à gauche puis recule de 20 cm`.

## G5 — Refus

`recule d'un mètre`, `va à la cuisine`, `attrape le cube bleu` : le robot explique, ne bouge pas.

## G6 — Obstacle

Carton à ~1 m devant. `avance de 2 mètres` : arrêt ~0,30 m du lidar, « Obstacle », puis « Je n'ai pas pu terminer : obstacle devant moi ».

## G7 — Arrêt pendant un ordre

`avance de 2 mètres` (sans obstacle), puis ESPACE après ~50 cm (la zone de texte est quittée automatiquement après l'envoi). Attendu : arrêt, « Arrêt général », pas de reprise toute seule. Entrée pour lever.

## G8 — Touche P et état

P : saisie du cube comme avant (passe maintenant par le routeur). `état` : batterie et sécurité annoncées.

## G9 — Micro du PC

Bouton « 🎤 Micro PC » (autoriser le micro la première fois), dire « avance de trente centimètres ». Attendu : même résultat que G2.

## G10 — IA locale

`approche-toi un peu de moi` (phrase hors grammaire). Attendu : « Je réfléchis », puis « Je vais … Je lance ? » ; écrire `oui`. Puis `raconte une blague` : réponse parlée, aucun mouvement.

## G11 — Redémarrage

Redémarrer, attendre 3 min, relevé `verif_etat_robot.sh` : `routeur_ordres` présent (lancé par le watchdog).

## Plus tard (étape 2b)

Micro du robot : aucun programme de reconnaissance vocale du robot ne tourne aujourd'hui (relevé E0). À brancher sur `/vocal_detect/asr_result` une fois G1–G11 validés ; le routeur n'aura pas à changer.
