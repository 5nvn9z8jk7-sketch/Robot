#!/bin/bash
echo "=== Test microphone avec sounddevice ==="
python3 << 'PYEOF'
import sounddevice as sd
import numpy as np

print("=== Audio devices ===")
devices = sd.query_devices()
for i, d in enumerate(devices):
    if d['max_input_channels'] > 0:
        print(f"  [{i}] {d['name']} — in:{d['max_input_channels']}ch, out:{d['max_output_channels']}ch, rate:{d['default_samplerate']}")

print(f"\nDefault input device: {sd.default.device[0]}")
print(f"Default sample rate: {sd.default.samplerate}")

print("\n=== Enregistrement test 5 secondes ===")
try:
    # Record 5 seconds at 16kHz mono (comme l'ASR)
    recording = sd.rec(int(16000 * 5), samplerate=16000, channels=1, dtype='int16')
    sd.wait()
    
    # Analyse
    max_val = np.abs(recording.flatten()).max()
    mean_val = np.abs(recording.flatten()).mean()
    rms = np.sqrt(np.mean(recording.flatten().astype(np.float32) ** 2))
    
    print(f"Max amplitude: {max_val} / 32767")
    print(f"Mean amplitude: {mean_val:.1f}")
    print(f"RMS: {rms:.1f}")
    print(f"Duree: {len(recording)/16000:.1f}s")
    
    # Check if there's actual audio (not just silence)
    if max_val > 100:
        print(">>> AUDIO DETECTE! Le micro fonctionne.")
    else:
        print(">>> SILENCE — le micro ne capte rien ou volume trop bas.")
        
    # Save a snippet for analysis
    import wave
    with wave.open('/tmp/test_mic.wav', 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(recording.tobytes())
    print("Enregistrement sauvegarde dans /tmp/test_mic.wav")
    
except Exception as e:
    print(f"ERREUR: {e}")
    import traceback
    traceback.print_exc()
PYEOF
