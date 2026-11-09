#!/bin/bash
echo "=== Methode _transcribe_buffer ==="
sed -n '298,600p' /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py | awk '/def _transcribe_buffer/,/def [a-z_]+\(/' | head -40

echo ""
echo "=== Methode _listen_loop complete ==="
sed -n '298,600p' /home/ubuntu/.local/lib/python3.10/site-packages/speech/speech_offline_patch.py | awk '/def _listen_loop/,/^class [A-Z]/' | head -80

echo ""
echo "=== Verifier scipy disponible ==="
python3 -c "import scipy.signal; print('scipy OK')" 2>&1

echo ""
echo "=== Verifier numpy resample ==="
python3 -c "import numpy as np; print('numpy OK, version:', np.__version__)" 2>&1
