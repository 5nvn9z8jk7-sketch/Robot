#!/bin/bash
echo "=== API OnlineRecognizer sherpa-onnx 1.12.14 ==="
python3 << 'PYEOF'
import sherpa_onnx
import os
import wave
import numpy as np

sherpa_dir = os.path.expanduser('~/third_party/sherpa-onnx')
model_dir = os.path.join(sherpa_dir, 'sherpa-onnx-streaming-zipformer-fr-2023-04-14')

encoder = os.path.join(model_dir, 'encoder-epoch-29-avg-9-with-averaged-model.onnx')
decoder = os.path.join(model_dir, 'decoder-epoch-29-avg-9-with-averaged-model.onnx')
joiner = os.path.join(model_dir, 'joiner-epoch-29-avg-9-with-averaged-model.onnx')
tokens = os.path.join(model_dir, 'tokens.txt')

recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
    encoder=encoder, decoder=decoder, joiner=joiner, tokens=tokens
)

print(f"Recognizer dir: {[x for x in dir(recognizer) if not x.startswith('_')]}")

# Test avec un fichier WAV
test_wav = os.path.join(model_dir, 'test_wavs', 'common_voice_fr_19364697.wav')
with wave.open(test_wav, 'rb') as wf:
    frames = wf.readframes(wf.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

print(f"\n=== Test differentes manieres d'obtenir le resultat ===")

# Methode 1: decode_stream puis recognizer.get_result(stream)
stream = recognizer.create_stream()
stream.accept_waveform(16000, audio)
stream.input_finished()
recognizer.decode_stream(stream)

# Essayer toutes les manieres possibles
methods_to_try = [
    ("recognizer.get_result(stream)", lambda: recognizer.get_result(stream)),
    ("recognizer.get_result()", lambda: recognizer.get_result()),
    ("stream.result", lambda: stream.result),
]

for name, fn in methods_to_try:
    try:
        result = fn()
        print(f"  {name}: type={type(result)}, dir={[x for x in dir(result) if not x.startswith('_')] if hasattr(result, '__dir__') else 'N/A'}")
        if hasattr(result, 'text'):
            print(f"    -> text: '{result.text}'")
    except Exception as e:
        print(f"  {name}: ERROR - {e}")

# Methode 2: utiliser is_endpoint + get_result
print(f"\n=== Test avec detection de fin de phrase ===")
stream2 = recognizer.create_stream()
# Envoyer l'audio par petits morceaux
chunk_size = 1600  # 0.1s a 16kHz
for i in range(0, len(audio), chunk_size):
    chunk = audio[i:i+chunk_size]
    stream2.accept_waveform(16000, chunk)
    if recognizer.is_ready(stream2):
        recognizer.decode_stream(stream2)
stream2.input_finished()
recognizer.decode_stream(stream2)

# Essayer de recuperer le resultat
try:
    result = recognizer.get_result(stream2)
    print(f"  recognizer.get_result(stream2): '{result.text}'")
except Exception as e:
    print(f"  recognizer.get_result(stream2) ERROR: {e}")

# Verifier les attributs du resultat
try:
    result = recognizer.get_result(stream2)
    print(f"  result type: {type(result)}")
    print(f"  result attrs: {[x for x in dir(result) if not x.startswith('_')]}")
    for attr in ['text', 'tokens', 'timestamps', 'json']:
        if hasattr(result, attr):
            val = getattr(result, attr)
            if callable(val):
                try:
                    val = val()
                except:
                    pass
            print(f"  result.{attr}: {str(val)[:200]}")
except Exception as e:
    print(f"  ERROR: {e}")

# Methode 3: OfflineRecognizer (non-streaming) pour comparaison
print(f"\n=== Test avec OfflineRecognizer (non-streaming) ===")
try:
    offline_rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=encoder, decoder=decoder, joiner=joiner, tokens=tokens
    )
    stream3 = offline_rec.create_stream()
    stream3.accept_waveform(16000, audio)
    offline_rec.decode_stream(stream3)
    result3 = stream3.result
    print(f"  OfflineRecognizer stream.result.text: '{result3.text}'")
    print(f"  stream3 dir: {[x for x in dir(stream3) if not x.startswith('_')]}")
except Exception as e:
    print(f"  OfflineRecognizer ERROR: {e}")
PYEOF
