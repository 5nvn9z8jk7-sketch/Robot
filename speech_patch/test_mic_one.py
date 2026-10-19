"""Teste un seul device audio spécifié en argument."""
import sys
import sounddevice as sd
import numpy as np

device_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
duration = int(sys.argv[2]) if len(sys.argv) > 2 else 3

d = sd.query_devices(device_id)
print(f"Device [{device_id}]: {d['name']} ({d['max_input_channels']} canaux in)")

try:
    rec = sd.rec(int(duration * 48000), samplerate=48000, channels=1, device=device_id, dtype='int16')
    sd.wait()
    peak = int(np.abs(rec).max())
    rms = float(np.sqrt((rec.astype(float)**2).mean()))
    pct = peak / 32767 * 100
    print(f"Peak: {pct:.1f}%, RMS: {rms:.1f}")
    if pct > 10:
        print("BON - ce micro capte bien la voix")
    elif pct > 1:
        print("FAIBLE - micro capte peu")
    else:
        print("MUET - aucun son detecte")
except Exception as e:
    print(f"ERREUR: {e}")
