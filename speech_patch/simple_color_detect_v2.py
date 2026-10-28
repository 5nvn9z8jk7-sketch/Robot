#!/usr/bin/env python3
# encoding: utf-8
"""simple_color_detect v2 - avec scaling de coordonnees RGB->depth."""

import numpy as np
import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from interfaces.msg import ColorsInfo, ColorInfo
from cv_bridge import CvBridge

DEPTH_WIDTH = 320
DEPTH_HEIGHT = 200

class SimpleColorDetect(Node):
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
        self.image_sub = self.create_subscription(
            Image, '/depth_cam/rgb0/image_raw', self._image_callback, 1)
        self.info_pub = self.create_publisher(
            ColorsInfo, '/color_detect_node/color_info', 1)
        self.timer = self.create_timer(0.1, self._detect_loop)
        self.get_logger().info('Simple color detect v2 pret (rouge HSV + scaling)')

    def _image_callback(self, msg):
        try:
            self._latest_frame = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
            self._frame_h, self._frame_w = self._latest_frame.shape[:2]
        except Exception as e:
            self.get_logger().error('Erreur conversion image: ' + str(e))

    def _detect_loop(self):
        if self._latest_frame is None:
            return
        frame = self._latest_frame.copy()
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(hsv, self.lower_red1, self.upper_red1)
        mask2 = cv2.inRange(hsv, self.lower_red2, self.upper_red2)
        mask = mask1 + mask2
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area < self.min_area:
            return
        M = cv2.moments(largest)
        if M['m00'] == 0:
            return
        cx = int(M['m10'] / M['m00'])
        cy = int(M['m01'] / M['m00'])
        x, y, w, h = cv2.boundingRect(largest)
        scale_x = DEPTH_WIDTH / self._frame_w
        scale_y = DEPTH_HEIGHT / self._frame_h
        cx_d = int(cx * scale_x)
        cy_d = int(cy * scale_y)
        w_d = int(w * scale_x)
        h_d = int(h * scale_y)
        radius_d = int(max(w_d, h_d) / 2)
        msg = ColorsInfo()
        info = ColorInfo()
        info.color = 'red'
        info.width = w_d
        info.height = h_d
        info.x = cx_d
        info.y = cy_d
        info.radius = radius_d
        info.angle = 0
        msg.data = [info]
        self.info_pub.publish(msg)
        self.get_logger().info(
            'Rouge: RGB(' + str(cx) + ',' + str(cy) + ') ' + str(w) + 'x' + str(h) +
            ' -> depth(' + str(cx_d) + ',' + str(cy_d) + ') ' + str(w_d) + 'x' + str(h_d),
            throttle_duration_sec=2)

def main():
    rclpy.init()
    node = SimpleColorDetect()
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
