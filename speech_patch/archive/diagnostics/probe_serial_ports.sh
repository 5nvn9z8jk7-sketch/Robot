#!/bin/bash
# Ecoute les ports serie 2s chacun pour trouver la board (elle streame l'IMU)
python3 - <<'PYEOF'
import serial, time
for dev in ("/dev/ttyACM0", "/dev/ttyCH341USB0", "/dev/ttyCH341USB1"):
    try:
        s = serial.Serial(dev, 1000000, timeout=0.2)
        s.reset_input_buffer()
        n = 0
        end = time.time() + 2.0
        while time.time() < end:
            data = s.read(4096)
            n += len(data)
        s.close()
        print(f"{dev}: {n} octets recus en 2s")
    except Exception as e:
        print(f"{dev}: ERREUR {e}")
PYEOF
