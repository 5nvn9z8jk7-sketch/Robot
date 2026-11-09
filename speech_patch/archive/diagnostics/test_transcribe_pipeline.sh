#!/bin/bash
echo "=== Test pipeline transcription complete ==="
python3 << 'PYEOF'
import os
import wave
import numpy as np
from scipy.signal import resample_poly
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

# Test 1: fichier WAV 16kHz mono direct (pas de resampling)
print("\n=== Test 1: WAV 16kHz mono direct ===")
test_wav = os.path.join(model_dir, 'test_wavs', 'common_voice_fr_19364697.wav')
with wave.open(test_wav, 'rb') as wf:
    rate = wf.getframerate()
    ch = wf.getnchannels()
    frames = wf.readframes(wf.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16)
    
print(f"  Fichier: rate={rate}, ch={ch}, samples={len(audio)}, duree={len(audio)/rate:.2f}s")

# Direct 16kHz mono
if rate == 16000 and ch == 1:
    s = audio.astype(np.float32) / 32768.0
    stream = recognizer.create_stream()
    stream.accept_waveform(16000, s)
    stream.input_finished()
    recognizer.decode_stream(stream)
    text = recognizer.get_result(stream)
    print(f"  Resultat direct: '{text}'")

# Test 2: simuler la pipeline (stereo 48kHz -> mono -> 16kHz)
print("\n=== Test 2: Pipeline stereo 48kHz -> mono -> 16kHz ===")
# Convertir le WAV 16kHz en "48kHz stereo" puis resampler
audio_48k_stereo = np.column_stack([audio, audio])  # stereo
audio_48k_up = resample_poly(audio_48k_stereo.astype(np.float32), 48000, 16000)  # upsample to 48k
print(f"  Simule 48kHz stereo: shape={audio_48k_up.shape}")

# Downmix
mono = audio_48k_up.mean(axis=1)
# Resample back to 16k
resampled = resample_poly(mono, 16000, 48000)
resampled_int16 = resampled.astype(np.int16)
print(f"  Resample 16kHz: samples={len(resampled_int16)}")

s2 = resampled_int16.astype(np.float32) / 32768.0
stream2 = recognizer.create_stream()
stream2.accept_waveform(16000, s2)
stream2.input_finished()
recognizer.decode_stream(stream2)
text2 = recognizer.get_result(stream2)
print(f"  Resultat pipeline: '{text2}'")

# Test 3: avec int8 model (plus rapide)
print("\n=== Test 3: Modele int8 ===")
encoder_i8 = os.path.join(model_dir, 'encoder-epoch-29-avg-9-with-averaged-model.int8.onnx')
decoder_i8 = os.path.join(model_dir, 'decoder-epoch-29-avg-9-with-averaged-model.int8.onnx')
joiner_i8 = os.path.join(model_dir, 'joiner-epoch-29-avg-9-with-averaged-model.int8.onnx')

recognizer_i8 = sherpa_onnx.OnlineRecognizer.from_transducer(
    encoder=encoder_i8, decoder=decoder_i8, joiner=joiner_i8, tokens=tokens
)
stream3 = recognizer_i8.create_stream()
stream3.accept_waveform(16000, s)
stream3.input_finished()
recognizer_i8.decode_stream(stream3)
text3 = recognizer_i8.get_result(stream3)
print(f"  Resultat int8: '{text3}'")

# Test 4: tous les fichiers test
print("\n=== Test 4: Tous les fichiers test WAV ===")
import glob
for wav_file in sorted(glob.glob(os.path.join(model_dir, 'test_wavs', '*.wav'))):
    with wave.open(wav_file, 'rb') as wf:
        frames = wf.readframes(wf.getnframes())
        audio_t = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    stream_t = recognizer.create_stream()
    stream_t.accept_waveform(16000, audio_t)
    stream_t.input_finished()
    recognizer.decode_stream(stream_t)
    text_t = recognizer.get_result(stream_t)
    print(f"  {os.path.basename(wav_file)}: '{text_t}'")
PYEOF
