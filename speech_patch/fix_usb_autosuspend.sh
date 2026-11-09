#!/bin/bash
# Desactive la mise en veille USB automatique (cause classique de camera qui "decroche" sur Jetson).
# A lancer SEULEMENT si diag_camera.sh montre power/control=auto. Reversible : sudo rm la regle + reboot.
set -e
for d in /sys/bus/usb/devices/*/power/control; do echo on | sudo tee "$d" >/dev/null; done
echo 'ACTION=="add", SUBSYSTEM=="usb", TEST=="power/control", ATTR{power/control}="on"' | \
  sudo tee /etc/udev/rules.d/90-usb-no-autosuspend.rules >/dev/null
sudo udevadm control --reload-rules
echo "OK : veille USB desactivee maintenant et a chaque demarrage (/etc/udev/rules.d/90-usb-no-autosuspend.rules)"
