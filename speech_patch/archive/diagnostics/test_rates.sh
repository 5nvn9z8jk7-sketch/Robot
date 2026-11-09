#!/bin/bash
echo "=== Test des combinaisons sample_rate/channels pour device 0 ==="
python3 << 'PYEOF'
import sounddevice as sd
import numpy as np

tests = [
    (48000, 1),   # 48kHz mono
    (48000, 2),   # 48kHz stereo
    (44100, 1),   # 44.1kHz mono
    (44100, 2),   # 44.1kHz stereo
    (16000, 2),   # 16kHz stereo
]

for rate, ch in tests:
    try:
        rec = sd.rec(int(rate * 2), samplerate=rate, channels=ch, dtype='int16', device=0)
        sd.wait()
        max_val = np.abs(rec.flatten()).max()
        status = "OK" if max_val > 50 else "SILENCE"
        print(f"  {rate}Hz {ch}ch: max={max_val}, {status}")
    except Exception as e:
        print(f"  {rate}Hz {ch}ch: ERREUR - {e}")

print("\n=== Test device 0 avec arecord (ALSA hw:0,0) ===")
import subprocess
# Test 48kHz stereo
r = subprocess.run(['arecord', '-D', 'hw:0,0', '-f', 'S16_LE', '-r', '48000', '-c', '2', '-d', '2', '/tmp/test_48k_stereo.wav'],
                   capture_output=True, text=True, timeout=10)
print(f"48kHz stereo: rc={r.returncode}, stderr={r.stderr.strip()[:100]}")

# Test 48kHz mono
r = subprocess.run(['arecord', '-D', 'hw:0,0', '-f', 'S16_LE', '-r', '48000', '-c', '1', '-d', '2', '/tmp/test_48k_mono.wav'],
                   capture_output=True, text=True, timeout=10)
print(f"48kHz mono: rc={r.returncode}, stderr={r.stderr.strip()[:100]}")

# Analyser les fichiers
for f in ['/tmp/test_48k_stereo.wav', '/tmp/test_48k_mono.wav']:
    try:
        import wave
        with wave.open(f, 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            data = np.frombuffer(frames, dtype=np.int16)
            print(f"  {f}: max={np.abs(data).max()}, mean={np.abs(data).mean():.1f}")
    except Exception as e:
        print(f"  {f}: {e}")
PYEOF
