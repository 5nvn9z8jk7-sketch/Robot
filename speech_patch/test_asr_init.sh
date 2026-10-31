#!/bin/bash
echo "=== Test import et init ASR ==="
python3 << 'PYEOF'
import os, sys
os.environ['SPEECH_LANG'] = 'fr'
os.environ['SHERPA_DIR'] = os.path.expanduser('~/third_party/sherpa-onnx')

from speech.speech_offline_patch import OfflineRealTimeASR
print("Import OK")

asr = OfflineRealTimeASR(language='fr')
print(f"ASR init OK, recognizer: {asr._recognizer is not None}")
print(f"Sample rate: {asr.sample_rate}")
print(f"Language: {asr.language}")

# Test rapide: transcrire un fichier test s'il existe
import glob
test_wavs = glob.glob(os.path.expanduser('~/third_party/sherpa-onnx/sherpa-onnx-streaming-zipformer-fr-2023-04-14/test_wavs/*.wav'))
if test_wavs:
    print(f"\nTest transcription: {test_wavs[0]}")
    text = asr.transcribe_file(test_wavs[0])
    print(f"Resultat: '{text}'")
else:
    print("\nPas de fichier test WAV trouve")
PYEOF
