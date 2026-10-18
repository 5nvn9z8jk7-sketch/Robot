#!/bin/bash
echo "=== API simple sherpa-onnx 1.12.14 ==="
python3 << 'PYEOF'
import sherpa_onnx
import os

sherpa_dir = os.path.expanduser('~/third_party/sherpa-onnx')
model_dir = os.path.join(sherpa_dir, 'sherpa-onnx-streaming-zipformer-fr-2023-04-14')

encoder = os.path.join(model_dir, 'encoder-epoch-29-avg-9-with-averaged-model.onnx')
decoder = os.path.join(model_dir, 'decoder-epoch-29-avg-9-with-averaged-model.onnx')
joiner = os.path.join(model_dir, 'joiner-epoch-29-avg-9-with-averaged-model.onnx')
tokens = os.path.join(model_dir, 'tokens.txt')

recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
    encoder=encoder, decoder=decoder, joiner=joiner, tokens=tokens
)

print("=== Recognizer methods ===")
for m in dir(recognizer):
    if not m.startswith('_'):
        print(f"  {m}")

print("\n=== Stream methods (sans audio) ===")
stream = recognizer.create_stream()
for m in dir(stream):
    if not m.startswith('_'):
        print(f"  {m}")

# Test get_result sans audio (juste pour voir la signature)
print("\n=== Test signatures ===")
import inspect
try:
    sig = inspect.signature(recognizer.get_result)
    print(f"  recognizer.get_result{sig}")
except:
    print("  recognizer.get_result: pas de signature inspectable")

# Lister les classes de resultat disponibles
print("\n=== Classes disponibles dans sherpa_onnx ===")
for name in dir(sherpa_onnx):
    if 'esult' in name or 'tream' in name or 'ecognizer' in name:
        print(f"  {name}")

# Chercher OnlineStream dans la doc
print("\n=== Aide sur OnlineRecognizer ===")
help_text = recognizer.__doc__ or "pas de doc"
print(help_text[:500])

# Essayer d'appeler get_result avec un stream vide
print("\n=== Test get_result(stream) avec stream frais ===")
try:
    s = recognizer.create_stream()
    r = recognizer.get_result(s)
    print(f"  Type: {type(r)}")
    print(f"  Attrs: {[x for x in dir(r) if not x.startswith('_')]}")
    if hasattr(r, 'text'):
        print(f"  text: '{r.text}'")
except Exception as e:
    print(f"  ERROR: {e}")
PYEOF
