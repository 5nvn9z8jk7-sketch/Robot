@echo off
REM autoriser_ollama_firewall.bat - A EXECUTER EN TANT QU'ADMINISTRATEUR
REM Ouvre le port 11434 (Ollama) en entree pour le robot (192.168.1.30)
REM Clic droit > Executer en tant qu'administrateur

echo === Autorisation du port Ollama 11434 pour le robot ===
echo.

netsh advfirewall firewall add rule name="Ollama 11434 (Robot ROSOrin)" dir=in action=allow protocol=TCP localport=11434 remoteip=192.168.1.30 profile=private,domain
echo.

echo Verification :
netsh advfirewall firewall show rule name="Ollama 11434 (Robot ROSOrin)"
echo.

netsh advfirewall firewall add rule name="Ollama 11434 (local)" dir=in action=allow protocol=TCP localport=11434 profile=private,domain
echo.
echo Fait. Le robot peut maintenant atteindre Ollama sur 192.168.1.20:11434
echo.
pause
