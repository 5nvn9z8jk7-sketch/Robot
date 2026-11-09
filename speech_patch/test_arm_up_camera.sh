#!/bin/bash
# Test: bras remonte (config teach) -> la camera survit-elle ? le cube est-il visible ?
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash 2>/dev/null

check_stream() {
  timeout 5 ros2 topic hz /depth_cam/rgb0/image_raw 2>&1 | grep "average rate" | head -1
}

echo "--- stream avant:"
check_stream

echo "--- remontee bras (comme teach):"
ros2 topic pub --once /servo_controller servo_controller_msgs/msg/ServosPosition \
  "{duration: 1.5, position_unit: pwm, position: [{id: 1, position: 500}, {id: 2, position: 700}, {id: 3, position: 15}, {id: 4, position: 180}, {id: 5, position: 500}, {id: 10, position: 200}]}" >/dev/null 2>&1
sleep 3
echo "--- stream apres remontee:"
check_stream

sleep 2
python3 - <<'PYEOF'
import rclpy, time, numpy as np, cv2
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
rclpy.init()
node = rclpy.create_node("probe_arm_up")
bridge = CvBridge()
got = []
def cb(msg):
    if not got:
        got.append(bridge.imgmsg_to_cv2(msg, "bgr8"))
node.create_subscription(Image, "/depth_cam/rgb0/image_raw", cb, 1)
end = time.time() + 8
while not got and time.time() < end:
    rclpy.spin_once(node, timeout_sec=0.5)
if not got:
    print("PAS DIMAGE")
else:
    frame = got[0]
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    m1 = cv2.inRange(hsv, np.array([0,80,80]), np.array([10,255,255]))
    m2 = cv2.inRange(hsv, np.array([170,80,80]), np.array([180,255,255]))
    mask = m1 + m2
    k = np.ones((5,5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:3]
    print("contours rouges:", len(contours))
    sx, sy = 640.0/w, 400.0/h
    for i, c in enumerate(contours):
        a = cv2.contourArea(c)
        x, y, bw, bh = cv2.boundingRect(c)
        M = cv2.moments(c)
        cx = int(M["m10"]/max(1,M["m00"])); cy = int(M["m01"]/max(1,M["m00"]))
        print(f"  contour {i+1}: aire={a:.0f} RGB({cx},{cy}) {bw}x{bh} -> depth({int(cx*sx)},{int(cy*sy)}) {int(bw*sx)}x{int(bh*sy)}")
        cv2.rectangle(frame, (x,y), (x+bw,y+bh), (0,255,0), 2)
    cv2.imwrite("/tmp/probe_arm_up.jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print("IMG /tmp/probe_arm_up.jpg")
PYEOF
echo "--- FIN ---"
