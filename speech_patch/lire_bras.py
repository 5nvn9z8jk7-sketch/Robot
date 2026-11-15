#!/usr/bin/env python3
# encoding: utf-8
"""lire_bras.py — Affiche la position réelle des servomoteurs du bras (ne bouge rien)."""
import sys
import threading

import rclpy
from rclpy.node import Node

sys.path.insert(0, '/home/ubuntu/speech_patch')
from bras_etat import lire_positions  # noqa: E402


def main():
    rclpy.init()
    n = Node('lire_bras')
    threading.Thread(target=rclpy.spin, args=(n,), daemon=True).start()
    try:
        print('Position actuelle du bras :', lire_positions(n))
    except Exception as e:
        print('ERREUR :', e)
    rclpy.shutdown()


if __name__ == '__main__':
    main()
