#!/bin/bash
echo "=== Test pattern streaming correct ==="
python3 << 'PYEOF'
import os
import wave
import numpy as np
import sherpa_onnx

sherpa_dir = os.path.expanduser('~/third_party/sherpa-onnx')
model_dir = os.path.join(sherpa_dir, 'sherpa-onnx-streaming-zipformer-fr-2023-04-14')

encoder = os.path.join(model_dir, 'encoder-epoch-29-avg-9-with-averaged-model.onnx')
decoder = os.path.join(model_dir, 'decoder-epoch-29-avg-9-with-averaged-model.onnx')
joiner = os.path.join(model_dir, 'joiner-epoch-29-avg-9-with-averaged-model.onnx')
tokens = os.path.join(model_dir, 'tokens.txt')

recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
    encoder=encoder, decoder=decoder, joiner=joiner, tokens=tokens
)
print("Recognizer OK")

# Charger le fichier test
test_wav = os.path.join(model_dir, 'test_wavs', 'common_voice_fr_19364697.wav')
with wave.open(test_wav, 'rb') as wf:
    frames = wf.readframes(wf.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

print(f"Audio: {len(audio)} samples, {len(audio)/16000:.2f}s")

# Pattern 1: feed all at once, decode once (ce qu'on fait actuellement)
print("\n=== Pattern 1: feed all + decode once ===")
s1 = recognizer.create_stream()
s1.accept_waveform(16000, audio)
s1.input_finished()
recognizer.decode_stream(s1)
print(f"  Result: '{recognizer.get_result(s1)}'")

# Pattern 2: feed chunk by chunk, decode when ready
print("\n=== Pattern 2: feed chunk-by-chunk + decode when ready ===")
s2 = recognizer.create_stream()
chunk_size = 1600  # 0.1s
decoded_count = 0
for i in range(0, len(audio), chunk_size):
    chunk = audio[i:i+chunk_size]
    s2.accept_waveform(16000, chunk)
    while recognizer.is_ready(s2):
        recognizer.decode_stream(s2)
        decoded_count += 1
s2.input_finished()
while recognizer.is_ready(s2):
    recognizer.decode_stream(s2)
    decoded_count += 1
print(f"  Decoded {decoded_count} times")
print(f"  Result: '{recognizer.get_result(s2)}'")

# Pattern 3: feed all, decode multiple times
print("\n=== Pattern 3: feed all + decode loop ===")
s3 = recognizer.create_stream()
s3.accept_waveform(16000, audio)
decoded_count3 = 0
while recognizer.is_ready(s3):
    recognizer.decode_stream(s3)
    decoded_count3 += 1
s3.input_finished()
while recognizer.is_ready(s3):
    recognizer.decode_stream(s3)
    decoded_count3 += 1
print(f"  Decoded {decoded_count3} times")
print(f"  Result: '{recognizer.get_result(s3)}'")

# Pattern 4: feed + input_finished + decode loop
print("\n=== Pattern 4: feed + input_finished + decode loop ===")
s4 = recognizer.create_stream()
s4.accept_waveform(16000, audio)
s4.input_finished()
decoded_count4 = 0
while recognizer.is_ready(s4):
    recognizer.decode_stream(s4)
    decoded_count4 += 1
print(f"  Decoded {decoded_count4} times")
print(f"  Result: '{recognizer.get_result(s4)}'")

# Pattern 5: utiliser get_result_all
print("\n=== Pattern 5: get_result_all ===")
s5 = recognizer.create_stream()
s5.accept_waveform(16000, audio)
s5.input_finished()
recognizer.decode_stream(s5)
try:
    all_results = recognizer.get_result_all()
    print(f"  get_result_all: '{all_results}'")
except Exception as e:
    print(f"  ERROR: {e}")

# Test avec un fichier test different
print("\n=== Test avec common_voice_fr_19738183.wav ===")
test_wav2 = os.path.join(model_dir, 'test_wavs', 'common_voice_fr_19738183.wav')
with wave.open(test_wav2, 'rb') as wf:
    frames2 = wf.readframes(wf.getnframes())
    audio2 = np.frombuffer(frames2, dtype=np.int16).astype(np.float32) / 32768.0

s6 = recognizer.create_stream()
for i in range(0, len(audio2), 1600):
    chunk = audio2[i:i+1600]
    s6.accept_waveform(16000, chunk)
    while recognizer.is_ready(s6):
        recognizer.decode_stream(s6)
s6.input_finished()
while recognizer.is_ready(s6):
    recognizer.decode_stream(s6)
print(f"  Result: '{recognizer.get_result(s6)}'")
PYEOF
