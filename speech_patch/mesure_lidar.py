#!/usr/bin/env python3
# encoding: utf-8
"""mesure_lidar.py — LECTURE SEULE. Lit 10 balayages du lidar (/scan) et affiche :
  - les paramètres (repère, angles, portée)
  - la distance minimale dans 8 secteurs de 45° autour de l'angle 0 du lidar
  - l'angle exact de l'objet le plus proche

Sert à savoir où est « l'avant » du robot pour le lidar : poser une boîte
à ~40 cm DEVANT le robot, lancer le script, regarder quel secteur voit 0,4 m.

Usage sur le robot :  python3 mesure_lidar.py [topic]   (défaut /scan, ex. /scan_raw)
"""
import math
import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

N_SCANS = 10
SECTEURS = [(-22.5 + 45 * i, 22.5 + 45 * i) for i in range(8)]  # centrés sur 0, 45, 90...


class MesureLidar(Node):
    def __init__(self):
        super().__init__('mesure_lidar')
        self.scans = []
        topic = sys.argv[1] if len(sys.argv) > 1 else '/scan'
        print(f'Topic           : {topic}')
        self.create_subscription(LaserScan, topic, self._cb, qos_profile_sensor_data)

    def _cb(self, msg):
        if len(self.scans) < N_SCANS:
            self.scans.append(msg)


def norm_deg(a):
    a = (a + 180.0) % 360.0 - 180.0
    return a


def main():
    rclpy.init()
    node = MesureLidar()
    while rclpy.ok() and len(node.scans) < N_SCANS:
        rclpy.spin_once(node, timeout_sec=1.0)
    s = node.scans[0]
    print(f'Repère          : {s.header.frame_id}')
    print(f'Angles          : {math.degrees(s.angle_min):.1f}° -> {math.degrees(s.angle_max):.1f}°, '
          f'pas {math.degrees(s.angle_increment):.2f}°, {len(s.ranges)} points')
    print(f'Portée          : {s.range_min:.2f} m -> {s.range_max:.2f} m')

    # distance minimale (médiane sur les 10 balayages) par point
    n = min(len(x.ranges) for x in node.scans)
    best = []
    for i in range(n):
        vals = sorted(x.ranges[i] for x in node.scans
                      if s.range_min < x.ranges[i] < s.range_max and math.isfinite(x.ranges[i]))
        best.append(vals[len(vals) // 2] if vals else float('inf'))

    print('\nDistance minimale par secteur (angle du lidar, 0° = son axe) :')
    for lo, hi in SECTEURS:
        centre = norm_deg((lo + hi) / 2)
        d = float('inf')
        for i in range(n):
            a = norm_deg(math.degrees(s.angle_min + i * s.angle_increment))
            if lo <= a < hi or lo <= a + 360 < hi or lo <= a - 360 < hi:
                d = min(d, best[i])
        print(f'  secteur {centre:+6.0f}° : {d:5.2f} m' if math.isfinite(d) else f'  secteur {centre:+6.0f}° :  rien')

    i_min = min(range(n), key=lambda i: best[i])
    a_min = norm_deg(math.degrees(s.angle_min + i_min * s.angle_increment))
    print(f'\nObjet le plus proche : {best[i_min]:.2f} m à {a_min:+.1f}° (angle du lidar)')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
