#!/usr/bin/env python3
"""regle_survol.py CM — correction finale du survol, en cm.
Positif = le robot avance d'autant avant de descendre la pince ; négatif = il recule.
Ex. pince 1 cm APRÈS le cube : python3 regle_survol.py -1"""
import json, os, shutil, sys, time
f = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pick_calib.json')
cm = float(sys.argv[1].replace(',', '.'))
if not -5 <= cm <= 5:
    sys.exit('Valeur invraisemblable (entre -5 et 5 cm). Rien n\'est modifié.')
os.makedirs(os.path.join(os.path.dirname(f), 'sauvegardes'), exist_ok=True)
shutil.copy(f, os.path.join(os.path.dirname(f), 'sauvegardes',
                            'pick_calib.json.' + time.strftime('%Y%m%d_%H%M%S')))
d = json.load(open(f))
d['survol_extra_m'] = round(cm / 100.0, 4)
json.dump(d, open(f, 'w'), indent=2)
print(f"Correction finale du survol : {cm:+.1f} cm (pris en compte au prochain P)")
