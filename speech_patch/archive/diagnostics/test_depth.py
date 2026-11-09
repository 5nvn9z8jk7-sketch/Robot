#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from interfaces.msg import ColorsInfo
import numpy as np

class DepthTest(Node):
    def __init__(self):
        super().__init__('depth_test')
        self.depth_img = None
        self.color_info = None
        self.create_subscription(Image, '/depth_cam/depth0/image_raw', self.depth_cb, 1)
        self.create_subscription(ColorsInfo, '/color_detect_node/color_info', self.color_cb, 1)

    def depth_cb(self, msg):
        self.depth_img = np.frombuffer(msg.data, dtype=np.uint16).reshape(msg.height, msg.width)

    def color_cb(self, msg):
        self.color_info = msg

rclpy.init()
node = DepthTest()
for i in range(20):
    rclpy.spin_once(node, timeout_sec=0.1)
    if node.depth_img is not None and node.color_info is not None and len(node.color_info.data) > 0:
        break

if node.depth_img is None:
    print("ERROR: No depth image")
elif node.color_info is None or len(node.color_info.data) == 0:
    print("ERROR: No color detection")
else:
    cube = node.color_info.data[0]
    print("Cube: x=%d, y=%d, w=%d, h=%d" % (cube.x, cube.y, cube.width, cube.height))
    x, y = cube.x, cube.y
    window = 5
    h, w = node.depth_img.shape
    x0 = max(0, x - window)
    x1 = min(w, x + window + 1)
    y0 = max(0, y - window)
    y1 = min(h, y + window + 1)
    patch = node.depth_img[y0:y1, x0:x1].flatten()
    valid = patch[(patch > 100) & (patch < 4000)]
    print("Depth patch (%d:%d, %d:%d): %d valid pixels" % (x0, x1, y0, y1, len(valid)))
    if len(valid) > 0:
        med = float(np.median(valid))
        print("  median: %.1f mm = %.1f cm" % (med, med / 10.0))
        print("  min: %.1f mm, max: %.1f mm" % (float(np.min(valid)), float(np.max(valid))))
    print("Depth center (160,100): %d mm" % node.depth_img[100, 160])
    print("Depth bottom (160,180): %d mm" % node.depth_img[180, 160])

node.destroy_node()
rclpy.shutdown()
