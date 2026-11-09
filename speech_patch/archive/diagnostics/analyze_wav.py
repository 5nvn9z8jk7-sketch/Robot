import wave, struct, sys

path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/test_mic.wav'
w = wave.open(path, 'rb')
frames = w.readframes(w.getnframes())
samples = struct.unpack(f'<{len(frames)//2}h', frames)
peak = max(abs(s) for s in samples)
rms = (sum(s**2 for s in samples) / len(samples)) ** 0.5
print(f'Peak: {peak}/32767 ({peak/32767*100:.1f}%), RMS: {rms:.1f}')
print(f'Durée: {w.getnframes()/w.getframerate():.1f}s, {w.getnchannels()} canaux, {w.getframerate()} Hz')
