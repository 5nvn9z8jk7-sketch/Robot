#!/usr/bin/env python3
# encoding: utf-8
"""
simple_color_detect.py — Detection de couleur rouge avec OpenCV (autonome).

S'abonne a /depth_cam/rgb0/image_raw, detecte le rouge (HSV), publie
sur /color_detect_node/color_info (compatible avec pick_and_place_node).

Usage sur le robot:
    python3 simple_color_detect.py
"""

import os
import sys

import numpy as np
import cv2

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from interfaces.msg import ColorsInfo, ColorInfo
from cv_bridge import CvBridge


class SimpleColorDetect(Node):
    def __init__(self):
        super().__init__('simple_color_detect')

        self.bridge = CvBridge()
        self._latest_frame = None

        # Seuils HSV pour le rouge (deux plages: 0-10 et 170-180)
        self.lower_red1 = np.array([0, 100, 100])
        self.upper_red1 = np.array([10, 255, 255])
        self.lower_red2 = np.array([170, 100, 100])
        self.upper_red2 = np.array([180, 255, 255])

        # Taille minimale du contour (pixels)
        self.min_area = 500

        # S'abonner a l'image RGB
        self.image_sub = self.create_subscription(
            Image, '/depth_cam/rgb0/image_raw', self._image_callback, 1)

        # Publier sur le meme topic que color_detect_node
        self.info_pub = self.create_publisher(
            ColorsInfo, '/color_detect_node/color_info', 1)

        # Boucle de detection a 10 Hz
        self.timer = self.create_timer(0.1, self._detect_loop)

        self.get_logger().info('Simple color detect pret (rouge, HSV)')

    def _image_callback(self, msg):
        try:
            self._latest_frame = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        except Exception as e:
            self.get_logger().error('Erreur conversion image: ' + str(e))

    def _detect_loop(self):
        if self._latest_frame is None:
            return

        frame = self._latest_frame.copy()
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Masques rouge (deux plages)
        mask1 = cv2.inRange(hsv, self.lower_red1, self.upper_red1)
        mask2 = cv2.inRange(hsv, self.lower_red2, self.upper_red2)
        mask = mask1 + mask2

        # Nettoyage morphologique
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # Trouver les contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return

        # Prendre le plus grand contour
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)

        if area < self.min_area:
            return

        # Centre du contour
        M = cv2.moments(largest)
        if M['m00'] == 0:
            return
        cx = int(M['m10'] / M['m00'])
        cy = int(M['m01'] / M['m00'])

        # Dimensions
        x, y, w, h = cv2.boundingRect(largest)
        radius = int(max(w, h) / 2)

        # Publier
        msg = ColorsInfo()
        info = ColorInfo()
        info.color = 'red'
        info.width = int(w)
        info.height = int(h)
        info.x = int(cx)
        info.y = int(cy)
        info.radius = int(radius)
        info.angle = 0
        msg.data = [info]
        self.info_pub.publish(msg)

        # Log periodique
        self.get_logger().info('Rouge detecte: centre=(' + str(cx) + ',' + str(cy) + ') taille=' + str(w) + 'x' + str(h), throttle_duration_sec=2)


def main():
    rclpy.init()
    node = SimpleColorDetect()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
