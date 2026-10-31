#!/usr/bin/env python3
"""camera_supervisor.py — superviseur UNIQUE de la camera aurora930 (remplace camera_watchdog_v2.sh).

Pourquoi (session 31/10/2026) :
  Les anciens watchdogs testaient la camera avec `timeout 2|4 ros2 topic hz ...`.
  Sur la Jetson, le CLI ros2 met souvent 2-4 s juste a demarrer + decouvrir le topic :
  le test echouait alors que la camera marchait, et le watchdog TUAIT une camera saine
  (robot_watchdog.py la relancait apres 60 s "d'inactivite" => le crash ~1x/min observe).
  En plus, DEUX watchdogs relancaient la camera en meme temps (robot_watchdog + v2).

Ce superviseur :
  - reste abonne en permanence (pas de CLI relance a chaque test) -> mesure fiable
  - verifie que les images ARRIVENT et que leur horodatage AVANCE (detecte les images gelees)
  - ne relance qu'apres STALE_S secondes sans image valide, avec une periode de grace apres relance
  - escalade : relance du driver -> au 2e echec consecutif, reset USB du port camera
  - journalise chaque panne avec l'extrait dmesg (USB) -> ~/camera_events.log pour le diagnostic materiel

Usage (sur le robot) :
  bash ~/speech_patch/start_camera_supervisor.sh
  Options env : CAM_STALE_S (8), CAM_GRACE_S (30), CAM_USB_PORT (1-2.2.1), CAM_DRY_RUN=1 (log sans relancer)
"""
import os
import subprocess
import time

STALE_S = float(os.environ.get("CAM_STALE_S", "8"))
GRACE_S = float(os.environ.get("CAM_GRACE_S", "30"))
USB_PORT = os.environ.get("CAM_USB_PORT", "1-2.2.1")
DRY_RUN = os.environ.get("CAM_DRY_RUN", "0") == "1"
TOPIC = os.environ.get("CAM_TOPIC", "/depth_cam/rgb0/image_raw")
EVENTS_LOG = os.path.expanduser("~/camera_events.log")
DRIVER_LOG = os.path.expanduser("~/aurora.log")

DRIVER_BIN = os.path.expanduser(
    "~/third_party/aurora_ws/install/deptrum-ros-driver-aurora930/lib/"
    "deptrum-ros-driver-aurora930/aurora930_node")
DRIVER_ARGS = [
    "--ros-args", "-r", "__ns:=/",
    "-r", "depth/image_raw:=depth_cam/depth0/image_raw",
    "-r", "ir/camera_info:=depth_cam/depth0/camera_info",
    "-r", "ir/image_raw:=depth_cam/ir0/image_raw",
    "-r", "points2:=depth_cam/depth0/points",
    "-r", "rgb/camera_info:=depth_cam/rgb0/camera_info",
    "-r", "rgb/image_raw:=depth_cam/rgb0/image_raw",
]


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(EVENTS_LOG, "a") as f:
        f.write(line + "\n")


def sh(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"(erreur: {e})"


class HealthTracker:
    """Logique pure (testable sans ROS) : decide quand la camera est en panne."""

    def __init__(self, stale_s=STALE_S, grace_s=GRACE_S, now=None):
        now = time.monotonic() if now is None else now
        self.stale_s = stale_s
        self.grace_s = grace_s
        self.last_good = now          # derniere image valide (horloge locale)
        self.last_stamp = None        # dernier header.stamp vu (ns)
        self.grace_until = now + grace_s
        self.frames = 0
        self.frozen = 0
        self.consecutive_failures = 0

    def on_frame(self, stamp_ns, now=None):
        now = time.monotonic() if now is None else now
        if self.last_stamp is not None and stamp_ns <= self.last_stamp:
            self.frozen += 1          # meme image re-publiee : on ne la compte pas
            return
        self.last_stamp = stamp_ns
        self.last_good = now
        self.frames += 1
        self.consecutive_failures = 0

    def is_stale(self, now=None):
        now = time.monotonic() if now is None else now
        if now < self.grace_until:
            return False
        return (now - self.last_good) > self.stale_s

    def on_restart(self, now=None):
        now = time.monotonic() if now is None else now
        self.consecutive_failures += 1
        self.grace_until = now + self.grace_s
        self.last_good = now


def driver_running():
    return sh("pgrep -f '[a]urora930_node'") != ""


def kill_driver():
    sh("pkill -9 -f '[a]urora930_node'")
    sh("pkill -9 -f '[d]eptrum'")
    time.sleep(3)


def usb_reset():
    path = f"/sys/bus/usb/devices/{USB_PORT}"
    if not os.path.exists(path):
        log(f"   reset USB ignore : port {USB_PORT} introuvable (lsusb -t pour le trouver)")
        return
    sh(f"echo '{USB_PORT}' | sudo -n tee /sys/bus/usb/drivers/usb/unbind")
    time.sleep(2)
    sh(f"echo '{USB_PORT}' | sudo -n tee /sys/bus/usb/drivers/usb/bind")
    time.sleep(4)


def start_driver():
    with open(DRIVER_LOG, "a") as out:
        subprocess.Popen([DRIVER_BIN] + DRIVER_ARGS, stdout=out, stderr=out,
                         stdin=subprocess.DEVNULL, start_new_session=True)


def snapshot_reason(tracker):
    alive = "vivant" if driver_running() else "MORT"
    dmesg = sh("dmesg 2>/dev/null | grep -iE 'usb|uvc|over-current|disconnect|reset|error -' | tail -8"
               " || sudo -n dmesg | tail -8")
    drv = sh(f"tail -5 {DRIVER_LOG} 2>/dev/null")
    return (f"process driver={alive}, images recues={tracker.frames}, gelees={tracker.frozen}\n"
            f"   --- dmesg (USB) ---\n   " + dmesg.replace("\n", "\n   ") +
            f"\n   --- aurora.log ---\n   " + drv.replace("\n", "\n   "))


def main():
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Image

    rclpy.init()
    node = Node("camera_supervisor")
    tracker = HealthTracker()
    restarts = 0

    def cb(msg):
        tracker.on_frame(msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec)

    node.create_subscription(Image, TOPIC, cb, qos_profile_sensor_data)
    log(f"Superviseur camera demarre (topic={TOPIC}, stale={STALE_S}s, grace={GRACE_S}s, dry_run={DRY_RUN})")

    if not driver_running() and not DRY_RUN:
        log("Driver absent au demarrage -> lancement")
        start_driver()

    last_report = time.monotonic()
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.5)
            now = time.monotonic()
            if now - last_report > 300:   # bilan toutes les 5 min
                log(f"OK bilan : {tracker.frames} images, {tracker.frozen} gelees, {restarts} relances")
                last_report = now
            if not tracker.is_stale(now):
                continue
            log(f"PANNE : aucune image valide depuis {now - tracker.last_good:.1f}s\n   " + snapshot_reason(tracker))
            if DRY_RUN:
                tracker.on_restart()
                continue
            kill_driver()
            if tracker.consecutive_failures >= 1:
                log("   2e echec consecutif -> reset USB du port camera")
                usb_reset()
            start_driver()
            restarts += 1
            tracker.on_restart()
            log(f"   driver relance (relance n°{restarts})")
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
