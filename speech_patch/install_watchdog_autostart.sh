#!/bin/bash
# install_watchdog_autostart.sh — Lance le watchdog automatiquement au boot du robot
# À exécuter UNE SEULE FOIS sur le robot

echo "=== Installation du watchdog en autostart ==="

# Créer un script de lancement
cat > /home/ubuntu/start_watchdog.sh << 'EOF'
#!/bin/bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
source /home/ubuntu/third_party/aurora_ws/install/setup.bash 2>/dev/null

# Attendre que ROS2 soit prêt
sleep 10

# Lancer le watchdog
nohup python3 /home/ubuntu/speech_patch/robot_watchdog.py --interval 10 --max-restarts 5 > /tmp/watchdog.log 2>&1 &
echo "Watchdog autostart lancé PID $!"
EOF

chmod +x /home/ubuntu/start_watchdog.sh

# Ajouter au crontab (lance au boot)
(crontab -l 2>/dev/null; echo "@reboot /home/ubuntu/start_watchdog.sh") | crontab -

echo "✅ Watchdog installé en autostart (crontab @reboot)"
echo ""
echo "Vérification:"
echo "  crontab -l | grep watchdog"
echo "  tail -f /tmp/watchdog.log"
echo ""
echo "Le watchdog démarrera automatiquement à chaque boot du robot."
