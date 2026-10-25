import sys
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import numpy as np

class TestCam(Node):
    def __init__(self):
        super().__init__('test_cam3')
        self.bridge = CvBridge()
        self.got = False
        self.sub = self.create_subscription(Image, '/depth_cam/rgb0/image_raw', self.cb, 1)
        self.get_logger().info('TestCam3 en attente d image...')
    def cb(self, msg):
        if self.got: return
        self.got = True
        img = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        h, w = img.shape[:2]
        self.get_logger().info('Image recue: ' + str(w) + 'x' + str(h))
        self.get_logger().info('BGR mean: ' + str(img.mean(axis=(0,1)).tolist()))
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        self.get_logger().info('HSV mean: ' + str(hsv.mean(axis=(0,1)).tolist()))
        self.get_logger().info('HSV max: ' + str(hsv.max(axis=(0,1)).tolist()))
        # Test seuils
        m1 = cv2.inRange(hsv, np.array([0,80,80]), np.array([10,255,255]))
        m2 = cv2.inRange(hsv, np.array([170,80,80]), np.array([180,255,255]))
        mask = m1 + m2
        cnt = cv2.countNonZero(mask)
        self.get_logger().info('Pixels rouges (S>=80,V>=80): ' + str(cnt))
        # Plus permissif
        m1b = cv2.inRange(hsv, np.array([0,50,50]), np.array([10,255,255]))
        m2b = cv2.inRange(hsv, np.array([170,50,50]), np.array([180,255,255]))
        maskb = m1b + m2b
        cntb = cv2.countNonZero(maskb)
        self.get_logger().info('Pixels rouges (S>=50,V>=50): ' + str(cntb))
        # Contours
        contours, _ = cv2.findContours(maskb, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
            area = cv2.contourArea(c)
            if area > 30:
                M = cv2.moments(c)
                cx = int(M['m10']/M['m00']) if M['m00'] else 0
                cy = int(M['m01']/M['m00']) if M['m00'] else 0
                x,y,bw,bh = cv2.boundingRect(c)
                self.get_logger().info('  Contour area=' + str(int(area)) + ' centre=(' + str(cx) + ',' + str(cy) + ') taille=' + str(bw) + 'x' + str(bh))
        cv2.imwrite('/home/ubuntu/test_cam.jpg', img)
        self.get_logger().info('Image sauvegardee')

rclpy.init()
node = TestCam()
rclpy.spin_once(node, timeout_sec=8)
rclpy.shutdown()
