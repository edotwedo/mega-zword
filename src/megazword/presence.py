"""Optional local webcam presence. Frames are neither saved nor served."""

from __future__ import annotations

import threading
import time
from pathlib import Path


class ReturnGate:
    """Require a real absence, a stable return, and a cooldown between briefings."""

    def __init__(self, away_seconds=15, stable_seconds=2, cooldown=120):
        self.away_seconds, self.stable_seconds, self.cooldown = away_seconds, stable_seconds, cooldown
        self.absent_since = self.present_since = None
        self.armed = False
        self.last_trigger = float("-inf")

    def observe(self, present: bool, now: float) -> bool:
        if not present:
            self.present_since = None
            if self.absent_since is None:
                self.absent_since = now
            if now - self.absent_since >= self.away_seconds:
                self.armed = True
            return False
        self.absent_since = None
        if self.present_since is None:
            self.present_since = now
        if self.armed and now - self.present_since >= self.stable_seconds:
            self.armed = False  # even a suppressed return requires another absence
            if now - self.last_trigger >= self.cooldown:
                self.last_trigger = now
                return True
        return False


class OpenCVCamera:
    def __init__(self, index=0):
        try:
            import cv2
        except ImportError as exc:
            raise ValueError('Camera support needs: python -m pip install -e ".[camera]" '
                             'from your Mega Zword checkout, using its Python environment.') from exc
        if not all(hasattr(cv2, name) for name in ("VideoCapture", "CascadeClassifier", "data")):
            raise ValueError('Camera support requires OpenCV 4.x with its face classifier. '
                             'Install the .[camera] extra in the dashboard Python environment.')
        self.cv = cv2
        self.capture = cv2.VideoCapture(index)
        try:
            if not self.capture.isOpened():
                raise ValueError("Cannot open the local webcam. Check Windows camera access or another app using it.")
            self.detector = cv2.CascadeClassifier(str(
                Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
            if self.detector.empty():
                raise ValueError("OpenCV face detector is missing; reinstall the camera extra.")
        except Exception:
            self.close()
            raise

    def read(self) -> bool:
        ok, frame = self.capture.read()
        if not ok:
            raise ValueError("The local webcam stopped returning frames.")
        gray = self.cv.cvtColor(self.cv.resize(frame, (320, 240)), self.cv.COLOR_BGR2GRAY)
        faces = self.detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                              minSize=(40, 40))
        return len(faces) > 0

    def close(self):
        self.capture.release()


class CameraWatcher:
    """One opt-in capture thread per dashboard; startup never opens the camera."""

    def __init__(self, factory=OpenCVCamera, clock=time.monotonic):
        self.factory, self.clock = factory, clock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._event = 0
        self._error = ""
        self._status = "off"
        self._present = None

    def view(self):
        with self._lock:
            return {"status": self._status, "error": self._error,
                    "present": self._present, "event": self._event}

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._error, self._status, self._present = "", "starting", None
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="megazword-camera")
            self._thread.start()

    def _run(self):
        camera = None
        gate = ReturnGate()
        try:
            camera = self.factory()
            while not self._stop.is_set():
                present = camera.read()
                if self._stop.is_set():
                    break
                trigger = gate.observe(present, self.clock())
                with self._lock:
                    self._status, self._present = "watching", present
                    if trigger:
                        self._event += 1
                self._stop.wait(0.5)
        except Exception as exc:
            with self._lock:
                self._error = str(exc)[:300]
        finally:
            try:
                if camera is not None:
                    camera.close()
            finally:
                with self._lock:
                    self._status, self._present = "off", None

    def stop(self):
        with self._lock:
            thread = self._thread
            self._stop.set()
            if thread is not None and thread.is_alive():
                self._status = "stopping"
        if thread is not None:
            thread.join(2)
