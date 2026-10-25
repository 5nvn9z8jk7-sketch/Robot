import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import numpy as np

class TestCam(Node):
    def __init__(self):
        super().__init__('test_cam2')
        self.bridge = CvBridge()
        self.got = False
        self.sub = self.create_subscription(Image, '/depth_cam/rgb0/image_raw', self.cb, 1)
    def cb(self, msg):
        if self.got: return
        self.got = True
        img = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        h, w = img.shape[:2]
        print('Image: ' + str(w) + 'x' + str(h))
        print('BGR mean: ' + str(img.mean(axis=(0,1))))
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        print('HSV mean: ' + str(hsv.mean(axis=(0,1))))
        for sat_min, val_min in [(80,80),(50,50),(30,30)]:
            m1 = cv2.inRange(hsv, np.array([0,sat_min,val_min]), np.array([10,255,255]))
            m2 = cv2.inRange(hsv, np.array([170,sat_min,val_min]), np.array([180,255,255]))
            mask = m1 + m2
            cnt = cv2.countNonZero(mask)
            print('  HSV sat>=' + str(sat_min) + ' val>=' + str(val_min) + ': ' + str(cnt) + ' pixels rouges')
        cv2.imwrite('/home/ubuntu/test_cam.jpg', img)
        print('Image sauvegardee: ~/test_cam.jpg')
        m1 = cv2.inRange(hsv, np.array([0,80,80]), np.array([10,255,255]))
        m2 = cv2.inRange(hsv, np.array([170,80,80]), np.array([180,255,255]))
        mask = m1 + m2
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:3]:
            area = cv2.contourArea(c)
            if area > 50:
                M = cv2.moments(c)
                cx = int(M['m10']/M['m00']) if M['m00'] else 0
                cy = int(M['m01']/M['m00']) if M['m00'] else 0
                x,y,w,h = cv2.boundingRect(c)
                print('  Contour: area=' + str(int(area)) + ' centre=(' + str(cx) + ',' + str(cy) + ') taille=' + str(w) + 'x' + str(h))

rclpy.init()
node = TestCam()
import threading
def spin():
    rclpy.spin_once(node, timeout_sec=5)
t = threading.Thread(target=spin)
t.start()
t.join()
rclpy.shutdown()
