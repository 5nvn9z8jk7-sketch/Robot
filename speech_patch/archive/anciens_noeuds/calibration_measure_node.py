#!/usr/bin/env python3
# encoding: utf-8
"""
calibration_measure_node — Mesure la taille (pixels) et la profondeur (mm)
du cube rouge détecté, pour la calibration automatique du pick-and-place.

Topics:
  SUB: /color_detect_node/color_info  (interfaces/msg/ColorsInfo)
  SUB: /depth_cam/depth0/image_raw    (sensor_msgs/Image, uint16 mm)
  PUB: /calibration/measurement        (std_msgs/String, JSON)

Le JSON publié contient:
  {"x": 320, "y": 200, "width": 50, "height": 54, "radius": 27,
   "depth_mm": 250, "depth_m": 0.25, "timestamp": 1234567890.123}
"""

import json
import time
import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Image
from interfaces.msg import ColorsInfo

MIN_DEPTH_MM = 100   # 10cm min
MAX_DEPTH_MM = 4000  # 4m max


class CalibrationMeasureNode(Node):
    def __init__(self):
        super().__init__('calibration_measure')

        self._latest_color = None
        self._latest_depth = None
        self._depth_shape = None

        self.create_subscription(
            ColorsInfo, '/color_detect_node/color_info',
            self._color_cb, 1)
        self.create_subscription(
            Image, '/depth_cam/depth0/image_raw',
            self._depth_cb, 1)

        self.measure_pub = self.create_publisher(
            String, '/calibration/measurement', 10)

        # Timer: publie les mesures à 5 Hz
        self.timer = self.create_timer(0.2, self._measure_loop)

        self.get_logger().info('Calibration measure node pret')

    def _color_cb(self, msg):
        self._latest_color = msg

    def _depth_cb(self, msg):
        try:
            depth = np.frombuffer(msg.data, dtype=np.uint16).reshape(
                msg.height, msg.width)
            self._latest_depth = depth
            self._depth_shape = (msg.height, msg.width)
        except Exception as e:
            self.get_logger().error(f'Erreur depth: {e}')

    def _get_depth_at(self, x, y, window=5):
        """Lit la profondeur médiane autour du pixel (x,y)."""
        if self._latest_depth is None:
            return None
        h, w = self._latest_depth.shape
        x0 = max(0, x - window)
        x1 = min(w, x + window + 1)
        y0 = max(0, y - window)
        y1 = min(h, y + window + 1)
        patch = self._latest_depth[y0:y1, x0:x1].flatten()
        valid = patch[(patch > MIN_DEPTH_MM) & (patch < MAX_DEPTH_MM)]
        if len(valid) == 0:
            return None
        return float(np.median(valid))

    def _measure_loop(self):
        if self._latest_color is None or len(self._latest_color.data) == 0:
            return

        # Prendre le plus grand cube rouge
        reds = [c for c in self._latest_color.data if c.color == 'red']
        if not reds:
            return
        cube = max(reds, key=lambda c: c.width * c.height)

        # Lire la profondeur au centre du cube
        depth_mm = self._get_depth_at(cube.x, cube.y)

        result = {
            'x': int(cube.x),
            'y': int(cube.y),
            'width': int(cube.width),
            'height': int(cube.height),
            'radius': int(cube.radius),
            'color': cube.color,
            'depth_mm': int(depth_mm) if depth_mm else None,
            'depth_m': round(depth_mm / 1000.0, 4) if depth_mm else None,
            'timestamp': time.time(),
        }

        msg = String()
        msg.data = json.dumps(result)
        self.measure_pub.publish(msg)


def main():
    rclpy.init()
    node = CalibrationMeasureNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
