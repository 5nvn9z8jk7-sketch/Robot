#!/bin/bash
# verif_etat_robot.sh — Relevé de l'état du robot, en LECTURE SEULE.
# Ne lance, n'arrête et ne modifie rien. À exécuter sur le robot.
#
# Depuis le PC (PowerShell), une seule ligne :
#   ssh robot "curl -fsSL https://raw.githubusercontent.com/5nvn9z8jk7-sketch/Robot/etape-0-menage/speech_patch/verif_etat_robot.sh | bash" > $env:TEMP\verif_robot.txt
# Le résultat est dans le fichier verif_robot.txt du dossier temporaire du PC.

source /opt/ros/humble/setup.bash 2>/dev/null
source /home/ubuntu/ros2_ws/install/setup.bash 2>/dev/null
source /home/ubuntu/third_party/aurora_ws/install/setup.bash 2>/dev/null
D=/home/ubuntu/speech_patch

titre() { echo; echo "===== $1 ====="; }

titre "DATE / UPTIME"
date; uptime

titre "DEMARRAGE AUTOMATIQUE (crontab)"
crontab -l 2>/dev/null | grep -v '^#' || echo "(crontab vide)"

titre "SUPERVISEURS"
echo "robot_watchdog    : $(pgrep -fc '[r]obot_watchdog.py') processus"
echo "camera_supervisor : $(pgrep -fc '[c]amera_supervisor.py') processus"

titre "PROCESSUS QUI ECOUTENT LA VOIX OU PILOTENT LES ROUES (nombre)"
for p in '[p]ick_and_place_node_v6' '[p]ick_and_place_node.py' '[p]ick_and_place_node_v[2-5]' \
         '[v]oice_pick_node' '[l]lm_move_bridge' '[a]utonomous_mission' '[l]lm_control_move' \
         '[a]gent_process' '[v]ocal_detect' '[s]imple_asr_node' '[w]s_audio_asr' \
         '[p]c_audio_asr_server' '[s]imple_color_detect' '[t]ts_node' '[r]osbridge' \
         '[g]ardien_securite' '[r]outeur_ordres'; do
  printf '  %-32s %s\n' "$p" "$(pgrep -fc "$p")"
done

titre "NOEUDS ROS"
timeout 15 ros2 node list 2>/dev/null | sort

titre "QUI PUBLIE SUR /controller/cmd_vel"
timeout 15 ros2 topic info -v /controller/cmd_vel 2>/dev/null | grep -E 'Node name|Publisher count|Subscription count'

titre "QUI ECOUTE /vocal_detect/asr_result"
timeout 15 ros2 topic info -v /vocal_detect/asr_result 2>/dev/null | grep -E 'Node name|Publisher count|Subscription count'

titre "QUI RECOIT LES ORDRES DU ROUTEUR (/robot/ordre)"
timeout 15 ros2 topic info -v /robot/ordre 2>/dev/null | grep -E 'Node name|Publisher count|Subscription count'

titre "FREQUENCE DES CAPTEURS (6 s chacun)"
for t in /odom /scan /imu /ros_robot_controller/imu_raw /depth_cam/rgb0/image_raw /depth_cam/depth0/image_raw /color_detect_node/color_info; do
  r=$(timeout 6 ros2 topic hz "$t" 2>/dev/null | grep -m1 'average rate')
  printf '  %-34s %s\n' "$t" "${r:-AUCUN MESSAGE}"
done

titre "BATTERIE"
timeout 6 ros2 topic echo --once /ros_robot_controller/battery 2>/dev/null || echo "AUCUN MESSAGE sur /ros_robot_controller/battery"

titre "NAVIGATION / CARTOGRAPHIE DISPONIBLES"
ls /home/ubuntu/ros2_ws/src 2>/dev/null | tr '\n' ' '; echo
timeout 15 ros2 pkg list 2>/dev/null | grep -E 'nav2_bt_navigator|nav2_collision_monitor|slam_toolbox|cartographer_ros|twist_mux' || echo "(aucun paquet nav2/slam/twist_mux trouvé)"
echo "Cartes trouvées :"
find /home/ubuntu -maxdepth 6 -name '*.pgm' 2>/dev/null | head -10

titre "CAMERA (USB + superviseur)"
lsusb -t 2>/dev/null | grep -B1 -A1 -i 'video\|3251' | head -12
tail -3 /home/ubuntu/camera_events.log 2>/dev/null
echo "Erreurs USB -71 dans le noyau : $(dmesg 2>/dev/null | grep -c 'error -71') (vide = dmesg non lisible)"

titre "DERNIER BILAN WATCHDOG"
tail -20 /tmp/watchdog.log 2>/dev/null

titre "EMPREINTES DES FICHIERS ACTIFS (comparaison avec GitHub)"
cd "$D" 2>/dev/null && md5sum pick_and_place_node_v6.py pick_calib.py pick_calib.json simple_color_detect_v3.py \
  autonomous_mission_node.py llm_move_bridge_node.py robot_watchdog.py camera_supervisor.py \
  gardien_securite.py securite_logique.py voix_rapide.py routeur_ordres.py routeur_logique.py \
  start_watchdogs.sh ws_audio_asr_node.py speech_offline_patch.py 2>&1
echo "Fichiers .py présents dans $D :"
ls "$D"/*.py 2>/dev/null | xargs -n1 basename | tr '\n' ' '; echo

titre "FIN DU RELEVE"
