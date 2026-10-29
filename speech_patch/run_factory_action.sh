#!/bin/bash
# Lance une action groupe d'usine (comme le fait le logiciel arm d'origine)
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash 2>/dev/null
python3 - <<PYEOF
import rclpy, time, sqlite3
from servo_controller_msgs.msg import ServosPosition, ServoPosition
rclpy.init()
node = rclpy.create_node("run_factory_action")
pub = node.create_publisher(ServosPosition, "servo_controller", 1)
time.sleep(1.5)   # laisser le temps a la decouverte ROS (sinon 1er message perdu)
action = "$1"
ag = sqlite3.connect(f"/home/ubuntu/software/arm_pc/ActionGroups/{action}.d6a")
cu = ag.cursor()
cu.execute("select * from ActionGroup")
for act in cu.fetchall():
    msg = ServosPosition()
    msg.position_unit = "pulse"
    msg.duration = float(act[1]) / 1000.0
    data = []
    for i in range(0, len(act) - 2):
        servo = ServoPosition()
        servo.id = 10 if i + 1 == 6 else i + 1
        servo.position = float(act[2 + i])
        data.append(servo)
    msg.position = data
    pub.publish(msg)
    print(f"etape: {act}")
    time.sleep(float(act[1]) / 1000.0)
    rclpy.spin_once(node, timeout_sec=0.1)
print("ACTION TERMINEE:", action)
PYEOF
