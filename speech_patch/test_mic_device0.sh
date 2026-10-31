#!/bin/bash
echo "=== Test micro USB (device 0) ==="
python3 << 'PYEOF'
import sounddevice as sd
import numpy as np

print("=== Test device 0 (USB PnP Audio Device) ===")
try:
    # Record 5 seconds from device 0 at 16kHz mono
    recording = sd.rec(int(16000 * 5), samplerate=16000, channels=1, dtype='int16', device=0)
    sd.wait()
    
    max_val = np.abs(recording.flatten()).max()
    mean_val = np.abs(recording.flatten()).mean()
    rms = np.sqrt(np.mean(recording.flatten().astype(np.float32) ** 2))
    
    print(f"Device 0 — Max: {max_val}, Mean: {mean_val:.1f}, RMS: {rms:.1f}")
    if max_val > 100:
        print(">>> AUDIO DETECTE sur device 0!")
    else:
        print(">>> Silence sur device 0 aussi")
    
except Exception as e:
    print(f"ERREUR device 0: {e}")

print("\n=== Test device 0 a 48kHz stereo (natif) ===")
try:
    recording = sd.rec(int(48000 * 3), samplerate=48000, channels=2, dtype='int16', device=0)
    sd.wait()
    
    max_val = np.abs(recording.flatten()).max()
    mean_val = np.abs(recording.flatten()).mean()
    print(f"Device 0 (48kHz stereo) — Max: {max_val}, Mean: {mean_val:.1f}")
    if max_val > 100:
        print(">>> AUDIO DETECTE!")
    else:
        print(">>> Silence")
    
except Exception as e:
    print(f"ERREUR: {e}")

print("\n=== Test avec arecord (ALSA direct) ===")
import subprocess
result = subprocess.run(['arecord', '-D', 'hw:0,0', '-f', 'S16_LE', '-r', '16000', '-c', '1', '-d', '3', '/tmp/arecord_test.wav'], 
                       capture_output=True, text=True, timeout=10)
print(f"arecord stdout: {result.stdout}")
print(f"arecord stderr: {result.stderr}")

# Analyser le fichier
try:
    import wave
    with wave.open('/tmp/arecord_test.wav', 'rb') as wf:
        frames = wf.readframes(wf.getnframes())
        data = np.frombuffer(frames, dtype=np.int16)
        max_val = np.abs(data).max()
        mean_val = np.abs(data).mean()
        print(f"arecord file — Max: {max_val}, Mean: {mean_val:.1f}, Frames: {len(data)}")
        if max_val > 100:
            print(">>> AUDIO DETECTE avec arecord!")
        else:
            print(">>> Silence avec arecord")
except Exception as e:
    print(f"Erreur lecture wav: {e}")
PYEOF
