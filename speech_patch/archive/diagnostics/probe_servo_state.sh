#!/bin/bash
# Interroge l'etat du bus servo (servo 10 = pince)
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash 2>/dev/null
python3 - <<'PYEOF'
import rclpy
from ros_robot_controller_msgs.srv import GetBusServoState
from ros_robot_controller_msgs.msg import GetBusServoCmd
rclpy.init()
node = rclpy.create_node("servo_state_probe")
cli = node.create_client(GetBusServoState, "/ros_robot_controller/bus_servo/get_state")
if not cli.wait_for_service(timeout_sec=5.0):
    print("SERVICE INDISPONIBLE")
else:
    for sid in (1, 2, 10):
        req = GetBusServoState.Request()
        cmd = GetBusServoCmd()
        cmd.id = sid
        cmd.get_id = 1
        cmd.get_position = 1
        cmd.get_voltage = 1
        cmd.get_torque_state = 1
        req.cmd = [cmd]
        fut = cli.call_async(req)
        rclpy.spin_until_future_complete(node, fut, timeout_sec=5.0)
        st = fut.result()
        if st and st.state:
            s = st.state[0]
            print(f"servo {sid}: present_id={list(s.present_id)} position={list(s.position)} voltage={list(s.voltage)} torque={list(s.enable_torque)}")
        else:
            print(f"servo {sid}: PAS DE REPONSE (bus mort ou servo sans alim)")
rclpy.shutdown()
PYEOF
