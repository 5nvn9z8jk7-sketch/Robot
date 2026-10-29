#!/usr/bin/env python3
# encoding: utf-8
"""simple_color_detect v3 — detection du cube rouge, plus robuste que v2.

Changements par rapport a v2 :
  - Publie un message VIDE quand aucun cube n'est vu (avant, le dernier cube
    restait en memoire chez pick_and_place et le robot visait un cube fantome).
  - Ne traite que les NOUVELLES images (pas deux fois la meme frame).
  - Filtre forme : rapport largeur/hauteur et remplissage proches d'un cube
    (evite les objets rouges/oranges allonges, mains, meubles...).
  - Seuils HSV reglables en parametres ROS2 (s_min, v_min, min_area).
  - Image de debug annotee publiee sur /color_detect_node/debug_image
    (a regarder avec rqt_image_view pour regler les seuils).
  - Coordonnees toujours exprimees en 320x200 (compatible v5 / mission).
"""

import numpy as np
import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from interfaces.msg import ColorsInfo, ColorInfo
from cv_bridge import CvBridge

OUT_W = 320
OUT_H = 200


class SimpleColorDetectV3(Node):
    def __init__(self):
        super().__init__('simple_color_detect')
        self.bridge = CvBridge()
        self._frame = None
        self._frame_id = 0
        self._processed_id = 0

        self.declare_parameter('s_min', 110)     # saturation min (80 en v2 : trop large)
        self.declare_parameter('v_min', 60)      # luminosite min
        self.declare_parameter('h_low_max', 10)  # rouge bas : 0..h_low_max
        self.declare_parameter('h_high_min', 170)  # rouge haut : h_high_min..180
        self.declare_parameter('min_area', 250)  # aire min en pixels (resolution RGB native)
        self.declare_parameter('min_fill', 0.55)  # aire contour / aire rectangle
        self.declare_parameter('max_aspect', 2.0)  # rapport max largeur/hauteur
        self.declare_parameter('publish_debug', True)

        self.create_subscription(Image, '/depth_cam/rgb0/image_raw', self._image_cb, 1)
        self.info_pub = self.create_publisher(ColorsInfo, '/color_detect_node/color_info', 1)
        self.debug_pub = self.create_publisher(Image, '/color_detect_node/debug_image', 1)
        self.create_timer(0.066, self._detect_loop)  # ~15 Hz
        self.get_logger().info('simple_color_detect v3 pret (rouge HSV, filtre forme, message vide si rien)')

    def _p(self, name):
        return self.get_parameter(name).value

    def _image_cb(self, msg):
        try:
            self._frame = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
            self._frame_id += 1
        except Exception as e:
            self.get_logger().error(f'Erreur conversion image: {e}')

    def _detect_loop(self):
        if self._frame is None or self._frame_id == self._processed_id:
            return
        self._processed_id = self._frame_id
        frame = self._frame.copy()
        fh, fw = frame.shape[:2]

        blur = cv2.GaussianBlur(frame, (5, 5), 0)
        hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)
        s_min, v_min = int(self._p('s_min')), int(self._p('v_min'))
        m1 = cv2.inRange(hsv, np.array([0, s_min, v_min]),
                         np.array([int(self._p('h_low_max')), 255, 255]))
        m2 = cv2.inRange(hsv, np.array([int(self._p('h_high_min')), s_min, v_min]),
                         np.array([180, 255, 255]))
        mask = cv2.bitwise_or(m1, m2)
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best = None
        best_area = 0.0
        min_area = float(self._p('min_area'))
        min_fill = float(self._p('min_fill'))
        max_aspect = float(self._p('max_aspect'))
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            aspect = max(w, h) / max(1, min(w, h))
            fill = area / float(max(1, w * h))
            if aspect > max_aspect or fill < min_fill:
                continue
            if area > best_area:
                best_area = area
                best = (c, x, y, w, h)

        out = ColorsInfo()
        if best is not None:
            c, x, y, w, h = best
            M = cv2.moments(c)
            if M['m00'] > 0:
                cx = M['m10'] / M['m00']
                cy = M['m01'] / M['m00']
                sx, sy = OUT_W / fw, OUT_H / fh
                info = ColorInfo()
                info.color = 'red'
                info.x = int(round(cx * sx))
                info.y = int(round(cy * sy))
                info.width = int(round(w * sx))
                info.height = int(round(h * sy))
                info.radius = int(max(info.width, info.height) / 2)
                info.angle = 0
                out.data = [info]
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.circle(frame, (int(cx), int(cy)), 4, (0, 255, 0), -1)
                cv2.putText(frame, f'({info.x},{info.y}) {info.width}x{info.height}',
                            (x, max(15, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                self.get_logger().info(
                    f'Rouge: ({info.x},{info.y}) {info.width}x{info.height} [320x200]',
                    throttle_duration_sec=2.0)
        # Toujours publier : un message vide signifie "pas de cube"
        self.info_pub.publish(out)

        if self._p('publish_debug') and self.debug_pub.get_subscription_count() > 0:
            small = cv2.resize(mask, (fw // 4, fh // 4))
            frame[0:small.shape[0], 0:small.shape[1]] = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
            self.debug_pub.publish(self.bridge.cv2_to_imgmsg(frame, 'bgr8'))


def main():
    rclpy.init()
    node = SimpleColorDetectV3()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception:
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
