#!/usr/bin/env python3
# encoding: utf-8
"""simple_color_detect v3 - comme v2 mais publie TOUJOURS le message.

Difference avec v2: quand aucun cube rouge n'est visible, publie un
ColorsInfo VIDE (data: []) au lieu de ne rien publier. Indispensable pour
la calibration (teach_pick_v6 doit savoir que le cube n'est PAS vu).
"""

import numpy as np
import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from interfaces.msg import ColorsInfo, ColorInfo
from cv_bridge import CvBridge

import time

DEPTH_WIDTH = 640
DEPTH_HEIGHT = 400
FRAME_MAX_AGE_S = 1.0   # image plus vieille -> consideree morte, on publie vide


class SimpleColorDetectV3(Node):
    def __init__(self):
        super().__init__('simple_color_detect')
        self.bridge = CvBridge()
        self._latest_frame = None
        self._frame_w = 0
        self._frame_h = 0
        self.lower_red1 = np.array([0, 80, 80])
        self.upper_red1 = np.array([10, 255, 255])
        self.lower_red2 = np.array([170, 80, 80])
        self.upper_red2 = np.array([180, 255, 255])
        self.min_area = 100
        self._last_frame_time = None
        self._stale_warned = False
        self.image_sub = self.create_subscription(
            Image, '/depth_cam/rgb0/image_raw', self._image_callback, 1)
        self.info_pub = self.create_publisher(
            ColorsInfo, '/color_detect_node/color_info', 1)
        self.timer = self.create_timer(0.1, self._detect_loop)
        self.get_logger().info('Simple color detect v3 pret (publie toujours, meme vide)')

    def _image_callback(self, msg):
        try:
            self._latest_frame = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
            self._frame_h, self._frame_w = self._latest_frame.shape[:2]
            self._last_frame_time = time.monotonic()
        except Exception as e:
            self.get_logger().error('Erreur conversion image: ' + str(e))

    def _detect_loop(self):
        msg = ColorsInfo()
        msg.data = []
        # Fraicheur: une image en cache sans nouveau frame = camera morte.
        if (self._last_frame_time is None or
                time.monotonic() - self._last_frame_time > FRAME_MAX_AGE_S):
            if not self._stale_warned and self._last_frame_time is not None:
                self.get_logger().warn('Image plus fraiche depuis >1s -> publie vide (camera morte ?)')
                self._stale_warned = True
            self.info_pub.publish(msg)
            return
        self._stale_warned = False
        if self._latest_frame is not None:
            frame = self._latest_frame.copy()
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask1 = cv2.inRange(hsv, self.lower_red1, self.upper_red1)
            mask2 = cv2.inRange(hsv, self.lower_red2, self.upper_red2)
            mask = mask1 + mask2
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(largest)
                if area >= self.min_area:
                    M = cv2.moments(largest)
                    if M['m00'] != 0:
                        cx = int(M['m10'] / M['m00'])
                        cy = int(M['m01'] / M['m00'])
                        x, y, w, h = cv2.boundingRect(largest)
                        scale_x = DEPTH_WIDTH / max(1, self._frame_w)
                        scale_y = DEPTH_HEIGHT / max(1, self._frame_h)
                        info = ColorInfo()
                        info.color = 'red'
                        info.x = int(cx * scale_x)
                        info.y = int(cy * scale_y)
                        info.width = int(w * scale_x)
                        info.height = int(h * scale_y)
                        info.radius = int(max(info.width, info.height) / 2)
                        info.angle = 0
                        msg.data = [info]
                        self.get_logger().info(
                            'Rouge: depth(' + str(info.x) + ',' + str(info.y) + ') ' +
                            str(info.width) + 'x' + str(info.height),
                            throttle_duration_sec=2)
        # Publie TOUJOURS (cube vu -> data remplie, cube absent -> data [])
        self.info_pub.publish(msg)


def main():
    rclpy.init()
    node = SimpleColorDetectV3()
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
