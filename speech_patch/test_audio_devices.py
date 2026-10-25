#!/usr/bin/env python3
# encoding: utf-8
"""
test_audio_devices.py — Teste tous les micros et casques du PC.

Usage:
    python3 test_audio_devices.py
    python3 test_audio_devices.py --test-input   (test micros uniquement)
    python3 test_audio_devices.py --test-output  (test casques uniquement)
"""

import argparse
import time
import numpy as np
import sounddevice as sd


def list_devices():
    devices = sd.query_devices()
    inputs = []
    outputs = []
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            inputs.append((i, d['name'], d['max_input_channels'], d['default_samplerate']))
        if d['max_output_channels'] > 0:
            outputs.append((i, d['name'], d['max_output_channels'], d['default_samplerate']))
    return inputs, outputs


def test_input(device_idx, duration=5):
    """Teste un micro: affiche le niveau sonore en temps reel."""
    print(f"\n{'='*50}")
    print(f"  TEST MICRO [{device_idx}]")
    print(f"{'='*50}")
    
    try:
        dev = sd.query_devices(device_idx)
        print(f"  Nom: {dev['name']}")
        print(f"  Canaux: {dev['max_input_channels']}")
        print(f"  Rate: {dev['default_samplerate']} Hz")
        print(f"  Parle dans ce micro pendant {duration}s...")
        print()
    except Exception as e:
        print(f"  ERREUR: {e}")
        return False

    max_rms = 0
    samples_count = 0
    
    def callback(indata, frames, time_info, status):
        nonlocal max_rms, samples_count
        if status:
            print(f"  Status: {status}")
        rms = float(np.sqrt(np.mean(indata**2)))
        samples_count += 1
        if rms > max_rms:
            max_rms = rms
        # Barre de niveau
        level = int(rms * 200)
        bar = '#' * min(level, 50)
        # Couleur selon le niveau
        if rms > 0.01:
            indicator = '>>> PAROLE DETECTEE <<<'
        elif rms > 0.001:
            indicator = '(bruit faible)'
        else:
            indicator = '(silence)'
        print(f"  RMS: {rms:.4f} |{bar:<50}| {indicator}")

    try:
        with sd.InputStream(
            samplerate=16000,
            channels=1,
            dtype='float32',
            blocksize=8000,
            device=device_idx,
            callback=callback,
        ):
            sd.sleep(duration * 1000)
    except Exception as e:
        print(f"  ERREUR: {e}")
        return False

    print()
    print(f"  Resultat: RMS max = {max_rms:.4f} ({samples_count} chunks)")
    if max_rms > 0.01:
        print(f"  >>> CE MICRO FONCTIONNE ! Utilise --device {device_idx}")
        return True
    elif max_rms > 0.001:
        print(f"  >>> Micro faible. Parle plus fort ou rapproche-toi.")
        return False
    else:
        print(f"  >>> CE MICRO EST MUET. Essaie un autre.")
        return False


def test_output(device_idx, duration=3):
    """Teste un casque/haut-parleur: emet un son de test."""
    print(f"\n{'='*50}")
    print(f"  TEST CASQUE [{device_idx}]")
    print(f"{'='*50}")
    
    try:
        dev = sd.query_devices(device_idx)
        print(f"  Nom: {dev['name']}")
        print(f"  Canaux: {dev['max_output_channels']}")
        print(f"  Tu dois entendre un 'bip' de 3 secondes...")
        print()
    except Exception as e:
        print(f"  ERREUR: {e}")
        return False

    # Generer un son de test (440Hz + 880Hz)
    sr = 44100
    t = np.linspace(0, duration, int(sr * duration))
    # Bip agreable
    audio = (np.sin(2 * np.pi * 440 * t) * 0.3 + 
             np.sin(2 * np.pi * 880 * t) * 0.1)
    # Fade in/out
    fade = int(sr * 0.1)
    audio[:fade] *= np.linspace(0, 1, fade)
    audio[-fade:] *= np.linspace(1, 0, fade)
    audio = audio.astype(np.float32)

    try:
        sd.play(audio, samplerate=sr, device=device_idx)
        sd.wait()
        print(f"  Son emis. Tu as entendu ? (oui/non)")
        return True
    except Exception as e:
        print(f"  ERREUR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Test des peripheriques audio')
    parser.add_argument('--test-input', action='store_true', help='Tester les micros')
    parser.add_argument('--test-output', action='store_true', help='Tester les casques')
    parser.add_argument('--device', type=int, default=None, help='Tester un device specifique')
    parser.add_argument('--duration', type=int, default=5, help='Duree du test micro (s)')
    args = parser.parse_args()

    print("=" * 60)
    print("  TEST DES PERIPHERIQUES AUDIO")
    print("=" * 60)

    inputs, outputs = list_devices()

    print(f"\n  {len(inputs)} micro(s) trouve(s):")
    for i, name, ch, sr in inputs:
        print(f"    [{i}] {name} ({ch}ch, {sr}Hz)")

    print(f"\n  {len(outputs)} casque(s)/enceinte(s) trouve(s):")
    for i, name, ch, sr in outputs:
        print(f"    [{i}] {name} ({ch}ch, {sr}Hz)")

    print(f"\n  Device par defaut: input={sd.default.device[0]}, output={sd.default.device[1]}")

    # Test d'un device specifique
    if args.device is not None:
        test_input(args.device, args.duration)
        return

    # Test de tous les micros
    if args.test_input or not args.test_output:
        print(f"\n{'='*60}")
        print("  TEST DE TOUS LES MICROS")
        print("  (Parle dans chaque micro quand c'est indique)")
        print(f"{'='*60}")
        
        working_mics = []
        for idx, name, ch, sr in inputs:
            # Ignorer les devices virtuels
            if 'VAC' in name or 'Virtual' in name or 'Mappeur' in name or 'Pilote' in name:
                print(f"\n  [{idx}] {name} -> IGNORE (virtuel)")
                continue
            
            ok = test_input(idx, args.duration)
            if ok:
                working_mics.append(idx)
            
            time.sleep(1)

        print(f"\n{'='*60}")
        print("  RESUME MICROS")
        print(f"{'='*60}")
        if working_mics:
            print(f"  Micros qui fonctionnent: {working_mics}")
            print(f"  Utilise: python3 pc_mic_sender.py --device {working_mics[0]}")
        else:
            print("  AUCUN micro ne fonctionne !")
            print("  Verifie dans Windows: Parametres > Systeme > Son > Entree")

    # Test de tous les casques
    if args.test_output:
        print(f"\n{'='*60}")
        print("  TEST DE TOUS LES CASQUES")
        print(f"{'='*60}")
        
        for idx, name, ch, sr in outputs:
            if 'VAC' in name or 'Virtual' in name or 'Mappeur' in name:
                print(f"\n  [{idx}] {name} -> IGNORE (virtuel)")
                continue
            
            test_output(idx, 2)
            time.sleep(1)

    if not args.test_input and not args.test_output and args.device is None:
        print(f"\n{'='*60}")
        print("  AIDE")
        print(f"{'='*60}")
        print("  python3 test_audio_devices.py              # Liste + test micros")
        print("  python3 test_audio_devices.py --test-input # Test micros seulement")
        print("  python3 test_audio_devices.py --test-output# Test casques seulement")
        print("  python3 test_audio_devices.py --device 1   # Test micro [1]")
        print("  python3 test_audio_devices.py --duration 10# Test plus long")


if __name__ == '__main__':
    main()
