#!/bin/bash
echo "=== API OnlineStream sherpa-onnx ==="
python3 << 'PYEOF'
import sherpa_onnx
import os

# Charger le modele FR
sherpa_dir = os.path.expanduser('~/third_party/sherpa-onnx')
model_dir = os.path.join(sherpa_dir, 'sherpa-onnx-streaming-zipformer-fr-2023-04-14')

# Lister les fichiers
print("Fichiers du modele:")
for f in sorted(os.listdir(model_dir)):
    if f.endswith('.onnx') or f == 'tokens.txt':
        print(f"  {f}")

# Creer le recognizer
encoder = os.path.join(model_dir, 'encoder-epoch-29-avg-9-with-averaged-model.onnx')
decoder = os.path.join(model_dir, 'decoder-epoch-29-avg-9-with-averaged-model.onnx')
joiner = os.path.join(model_dir, 'joiner-epoch-29-avg-9-with-averaged-model.onnx')
tokens = os.path.join(model_dir, 'tokens.txt')

print(f"\nCreation OnlineRecognizer...")
recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
    encoder=encoder, decoder=decoder, joiner=joiner, tokens=tokens
)
print(f"Recognizer cree: {type(recognizer)}")

# Creer un stream
stream = recognizer.create_stream()
print(f"\nStream type: {type(stream)}")
print(f"Stream dir: {[x for x in dir(stream) if not x.startswith('_')]}")

# Tester avec un fichier WAV test
import wave
import numpy as np
test_wav = os.path.join(model_dir, 'test_wavs', 'common_voice_fr_19364697.wav')
if os.path.exists(test_wav):
    print(f"\nTest avec {test_wav}")
    with wave.open(test_wav, 'rb') as wf:
        print(f"  Rate: {wf.getframerate()}, Channels: {wf.getnchannels()}, Frames: {wf.getnframes()}")
        frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        
    stream2 = recognizer.create_stream()
    stream2.accept_waveform(16000, audio)
    recognizer.decode_stream(stream2)
    
    # Essayer differentes manieres d'obtenir le resultat
    print(f"\n  stream.result: {hasattr(stream2, 'result')}")
    if hasattr(stream2, 'result'):
        print(f"  stream.result type: {type(stream2.result)}")
        print(f"  stream.result dir: {[x for x in dir(stream2.result) if not x.startswith('_')]}")
        try:
            print(f"  stream.result.text: '{stream2.result.text}'")
        except Exception as e:
            print(f"  stream.result.text ERROR: {e}")
    
    print(f"\n  stream.get_result: {hasattr(stream2, 'get_result')}")
    
    # Essayer d'autres methodes
    for method in ['get_text', 'text', 'result_text']:
        if hasattr(stream2, method):
            try:
                val = getattr(stream2, method)
                if callable(val):
                    val = val()
                print(f"  stream.{method}: '{val}'")
            except Exception as e:
                print(f"  stream.{method} ERROR: {e}")

# Verifier la version de sherpa_onnx
print(f"\nsherpa_onnx version info:")
print(f"  __version__: {getattr(sherpa_onnx, '__version__', 'N/A')}")
print(f"  file: {sherpa_onnx.__file__}")
PYEOF
