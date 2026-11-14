# encoding: utf-8
"""bras_etat.py — Lit la position réelle des servomoteurs du bras (sans les bouger).

Service Hiwonder : /ros_robot_controller/bus_servo/get_state (GetBusServoState).
Utilisé par teach_pick_v6.py --regard-actuel et lire_bras.py.
"""
import time

from ros_robot_controller_msgs.msg import GetBusServoCmd
from ros_robot_controller_msgs.srv import GetBusServoState

SERVICE = '/ros_robot_controller/bus_servo/get_state'
SERVOS_BRAS = (1, 2, 3, 4, 5)


def _premier(v):
    try:
        return v[0]
    except (TypeError, IndexError):
        return v


def lire_positions(node, ids=SERVOS_BRAS, delai=3.0):
    """{id: position} pour chaque servo lu ; lève RuntimeError si le service ne répond pas."""
    client = node.create_client(GetBusServoState, SERVICE)
    if not client.wait_for_service(timeout_sec=delai):
        raise RuntimeError(f'service {SERVICE} absent')
    positions = {}
    for i in ids:
        req = GetBusServoState.Request()
        cmd = GetBusServoCmd()
        cmd.id = i
        cmd.get_position = 1
        req.cmd = [cmd]
        fut = client.call_async(req)
        fin = time.monotonic() + delai
        while not fut.done() and time.monotonic() < fin:
            time.sleep(0.02)
        if not fut.done() or fut.result() is None:
            raise RuntimeError(f'pas de réponse pour le servo {i}')
        rep = fut.result()
        if not getattr(rep, 'success', True) or not rep.state:
            raise RuntimeError(f'lecture refusée pour le servo {i} : {rep}')
        positions[i] = int(_premier(rep.state[0].position))
    node.destroy_client(client)
    return positions
