"""Backend ROS2 réel : navigation via Nav2.

Sur le robot : utilise l'action nav2_msgs/action/NavigateToPose.
"""
from __future__ import annotations

from ..core.types import Vec3


class Ros2Navigation:
    """À câbler sur le robot : action client Nav2 + pose initiale."""

    def __init__(self, action_name: str = "navigate_to_pose"):
        self.action_name = action_name

    def goto(self, target: Vec3) -> bool:
        """ Boucle réelle (pseudo-code) :

        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.pose.position.x = target.x
        goal.pose.pose.position.y = target.y
        envoyer le goal, attendre le résultat (rclpy action client)
        """
        raise NotImplementedError("à connecter à Nav2 sur le robot")
