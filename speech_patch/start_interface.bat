@echo off
chcp 65001 >nul
title Robot Hiwonder - Interface Web
color 0A

echo ============================================
echo   🤖 Robot Hiwonder - Interface de contrôle
echo ============================================
echo.

:: Vérifier que le robot est accessible
echo [1/4] Vérification du robot (192.168.1.30)...
ping -n 1 -w 2000 192.168.1.30 >nul 2>&1
if errorlevel 1 (
    echo   ❌ Robot non accessible ! Vérifie qu'il est allumé.
    echo.
    pause
    exit /b 1
)
echo   ✅ Robot en ligne

:: Vérifier le nœud moteurs (SANS le relancer : c'est le rôle du watchdog du robot,
:: qui le relance avec les bons paramètres. L'ancienne relance ici était "nue"
:: et faisait mourir imu_raw et odom.)
echo [2/4] Vérification du nœud moteurs...
ssh robot "bash -c 'source /opt/ros/humble/setup.bash; source /home/ubuntu/ros2_ws/install/setup.bash; ros2 node list 2>/dev/null | grep -q ros_robot_controller && echo ACTIF || echo INACTIF'" 2>nul > temp_motors.txt
:: On cherche d'abord INACTIF, puis ACTIF (findstr /X ne marche pas sur les
:: lignes Linux renvoyées par ssh, sans retour chariot).
findstr /C:"INACTIF" temp_motors.txt >nul 2>&1
if not errorlevel 1 (
    echo   ⚠️  Nœud moteurs INACTIF. Attendre 1 minute que le watchdog le relance,
    echo      ou regarder : ssh robot "tail -20 /tmp/watchdog.log"
    goto :moteurs_fin
)
findstr /C:"ACTIF" temp_motors.txt >nul 2>&1
if not errorlevel 1 (
    echo   ✅ Nœud moteurs actif
) else (
    echo   ⚠️  Pas de réponse du robot sur l'état des moteurs ^(ssh ou ROS^)
)
:moteurs_fin
del temp_motors.txt 2>nul

:: Vérifier Ollama
echo [3/4] Vérification du LLM (Ollama)...
curl -s http://192.168.1.20:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo   ⚠️  Ollama non accessible sur 192.168.1.20:11434
) else (
    echo   ✅ Ollama en ligne
)

:: Lancer le serveur web
echo [4/4] Lancement du serveur web...
echo.
echo ============================================
echo   🌐 Ouvre ton navigateur sur :
echo   👉 http://localhost:8888/robot_keypad.html
echo ============================================
echo.
echo   Appuie sur une touche pour arrêter le serveur

cd /d "%~dp0"
python -m http.server 8888 --bind 0.0.0.0

pause
