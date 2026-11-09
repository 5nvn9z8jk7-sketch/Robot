#!/bin/bash
# setup_ssh_access.sh — Configure l'accès SSH du PC vers le robot
# À exécuter UNE SEULE FOIS sur le robot (via NoMachine terminal)
#
# Usage: bash setup_ssh_access.sh

echo "=== Configuration accès SSH PC -> Robot ==="
echo ""

# Créer le dossier .ssh si inexistant
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# Ajouter la clé publique du PC (générée le 18/10/2026)
PUB_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPhYn5b7uOzJyPZUFyL2tZS70cr9ElwbWiT7UeAVLqbb vibe-robot-20261018"

if grep -q "vibe-robot-20261018" ~/.ssh/authorized_keys 2>/dev/null; then
    echo "[OK] Clé déjà présente dans authorized_keys"
else
    echo "$PUB_KEY" >> ~/.ssh/authorized_keys
    echo "[OK] Clé ajoutée à ~/.ssh/authorized_keys"
fi

chmod 600 ~/.ssh/authorized_keys

echo ""
echo "=== Configuration terminée ==="
echo "Le PC peut maintenant se connecter avec:"
echo "  ssh -i ~/.ssh/id_robot ubuntu@$(hostname -I | awk '{print $1}')"
echo ""
echo "Depuis le PC, tester avec:"
echo "  ssh -i /c/Users/bloiz/.ssh/id_robot ubuntu@192.168.1.30 'echo OK'"
