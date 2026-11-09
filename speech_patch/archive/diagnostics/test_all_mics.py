"""Teste tous les devices audio avec canaux d'entree pour trouver le bon micro."""
import sounddevice as sd
import numpy as np

devices = sd.query_devices()
candidates = []
for i, d in enumerate(devices):
    if d['max_input_channels'] > 0 and ('APE' in d['name'] or i == 0):
        candidates.append((i, d['name'], d['max_input_channels']))

print(f"{len(candidates)} devices a tester (USB + APE):")
for i, name, ch in candidates:
    print(f"  [{i}] {name} ({ch} canaux)")

print("\nTest de 3 secondes sur chaque device (parle pendant le test !)...")
for i, name, ch in candidates:
    try:
        rec = sd.rec(int(3 * 48000), samplerate=48000, channels=1, device=i, dtype='int16')
        sd.wait()
        peak = int(np.abs(rec).max())
        rms = float(np.sqrt((rec.astype(float)**2).mean()))
        pct = peak / 32767 * 100
        status = "BON" if pct > 10 else "faible" if pct > 1 else "muet"
        print(f"  [{i}] {name[:40]:40s} Peak={pct:5.1f}% RMS={rms:7.1f} -> {status}")
    except Exception as e:
        print(f"  [{i}] {name[:40]:40s} ERREUR: {str(e)[:50]}")
