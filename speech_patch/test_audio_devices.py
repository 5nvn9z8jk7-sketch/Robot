import sounddevice as sd

print("Devices disponibles:")
for i, d in enumerate(sd.query_devices()):
    name = d['name']
    inch = d['max_input_channels']
    outch = d['max_output_channels']
    print(f"  [{i}] {name} (in={inch}, out={outch})")

print()
print("Device par defaut:", sd.default.device)

# Test d'enregistrement de 3 secondes sur le device 0
print("\nTest enregistrement 3s sur device 0...")
try:
    import numpy as np
    rec = sd.rec(int(3 * 48000), samplerate=48000, channels=2, device=0, dtype='int16')
    sd.wait()
    peak = int(np.abs(rec).max())
    rms = float(np.sqrt((rec.astype(float)**2).mean()))
    print(f"  Peak: {peak}/32767 ({peak/32767*100:.1f}%), RMS: {rms:.1f}")
except Exception as e:
    print(f"  ERREUR: {e}")
