"""Backend ROS2 réel : détection YOLO + transformation 3D.

Sur le robot : ce node s'abonne à la caméra RGB-D, exécute YOLO (TensorRT),
projette les détections en 3D via la profondeur + TF, publie les cibles.
"""
from __future__ import annotations

from ..core.types import Detection, Vec3


class Ros2Perception:
    """À câbler sur le robot : topics caméra + YOLO + tf2."""

    def __init__(self, engine_path: str, camera_frame: str = "camera_link"):
        self.engine_path = engine_path
        self.camera_frame = camera_frame
        self._model = None

    def _load(self):
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self.engine_path)

    def detect_toys(self) -> list:
        """ Boucle réelle (pseudo-code guidant l'implémentation) :

        1. img = self.latest_rgb()          # sensor_msgs/Image
        2. res = self._model(img, verbose=False)
        3. for box in res[0].boxes:
               u, v = centre du bbox (pixels)
               depth = depth_image[u, v]    # caméra de profondeur
               point_cam = projeter(u, v, depth, camera_info.K)
               point_base = tf2.transform(cam -> base_link, point_cam)
               detections.append(Detection(..., pos_3d=Vec3(*point_base)))
        """
        raise NotImplementedError("à connecter aux topics ROS2 du robot")
