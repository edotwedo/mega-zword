"""Camera lifecycle and return detection use fake input; never open a webcam."""

import threading

import pytest

from megazword.presence import CameraWatcher, OpenCVCamera, ReturnGate


def test_gate_requires_absence_stable_return_and_cooldown():
    gate = ReturnGate()
    assert not gate.observe(True, 0)  # opening the camera while seated is not a return
    assert not gate.observe(False, 5)
    assert not gate.observe(True, 6)  # a glance away
    assert not gate.observe(False, 10)
    assert not gate.observe(False, 25)
    assert not gate.observe(True, 26)
    assert gate.observe(True, 28)
    assert not gate.observe(True, 40)  # staying seated never retriggers
    assert not gate.observe(False, 50)
    assert not gate.observe(False, 65)
    assert not gate.observe(True, 66)
    assert not gate.observe(True, 68)  # within the cooldown
    assert not gate.observe(True, 160)  # suppressed return does not trigger late
    assert not gate.observe(False, 170)
    assert not gate.observe(False, 185)
    assert not gate.observe(True, 186)
    assert gate.observe(True, 188)


def test_unstable_face_detection_resets_return_timer():
    gate = ReturnGate()
    for present, now in [(False, 0), (False, 15), (True, 16), (False, 17), (True, 18)]:
        assert not gate.observe(present, now)
    assert not gate.observe(True, 19)
    assert gate.observe(True, 20)


def test_watcher_is_off_until_enabled_releases_camera_and_can_restart():
    read = threading.Event()
    cameras = []

    class Camera:
        closed = False

        def __init__(self):
            cameras.append(self)

        def read(self):
            read.set()
            return True

        def close(self):
            self.closed = True

    watcher = CameraWatcher(Camera)
    assert watcher.view()["status"] == "off" and not cameras
    watcher.start()
    assert read.wait(2)
    watcher.start()
    watcher.stop()
    assert len(cameras) == 1 and cameras[0].closed
    assert watcher.view()["status"] == "off"
    read.clear()
    watcher.start()
    assert read.wait(2)
    watcher.stop()
    assert len(cameras) == 2 and cameras[1].closed


def test_failed_capture_is_reported_and_released():
    finished = threading.Event()

    class BrokenCamera:
        def read(self):
            raise ValueError("camera unavailable")

        def close(self):
            finished.set()

    watcher = CameraWatcher(BrokenCamera)
    watcher.start()
    assert finished.wait(2)
    watcher.stop()
    assert watcher.view() == {"status": "off", "error": "camera unavailable",
                              "present": None, "event": 0}


def test_opencv_missing_dependency_does_not_open_camera(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "cv2", None)
    with pytest.raises(ValueError, match=r"\.\[camera\]"):
        OpenCVCamera()


def test_watcher_publishes_one_return_event_and_keeps_no_frames():
    finished = threading.Event()
    samples = iter([False, False, True, True])
    ticks = iter([0, 15, 16, 18])

    class Camera:
        def read(self):
            try:
                return next(samples)
            except StopIteration:
                raise ValueError("end of test capture")

        def close(self):
            finished.set()

    watcher = CameraWatcher(Camera, clock=lambda: next(ticks))
    # No real-time delays for a deterministic camera-sequence test.
    watcher._stop.wait = lambda timeout: False
    watcher.start()
    assert finished.wait(2)
    watcher.stop()
    assert watcher.view()["event"] == 1
    assert set(watcher.view()) == {"status", "present", "error", "event"}


def test_opencv_open_failure_releases_capture(monkeypatch):
    import sys
    from types import SimpleNamespace
    closed = []
    capture = SimpleNamespace(isOpened=lambda: False, release=lambda: closed.append(True))
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(
        VideoCapture=lambda index: capture, CascadeClassifier=object, data=object()))
    with pytest.raises(ValueError, match="Cannot open"):
        OpenCVCamera()
    assert closed == [True]


@pytest.mark.parametrize("width,height", [(1280, 720), (640, 480), (320, 240)])
def test_camera_detects_small_seated_face_without_distorting_frame(width, height):
    from types import SimpleNamespace

    class Frame:
        shape = (height, width, 3)

    resized = []
    enhanced = []

    def resize(frame, size):
        resized.append(size)
        # Model a face occupying 10% of this wide-angle webcam frame.
        return {"face_width": size[0] * .1}

    def equalize(gray):
        enhanced.append(True)
        return {**gray, "equalized": True}

    def detect(gray, **options):
        # A 320px/min40 pipeline rejects the seated face. The corrected
        # pipeline must preserve a detectable face and improve contrast.
        return [(0, 0, 32, 32)] if (
            gray.get("equalized") and gray["face_width"] >= options["minSize"][0]
        ) else []

    camera = OpenCVCamera.__new__(OpenCVCamera)
    camera.capture = SimpleNamespace(read=lambda: (True, Frame()))
    camera.cv = SimpleNamespace(resize=resize, cvtColor=lambda frame, code: frame,
                                equalizeHist=equalize, COLOR_BGR2GRAY=0)
    camera.detector = SimpleNamespace(detectMultiScale=detect)
    assert camera.read() is True
    target_width = min(width, 640)
    assert resized == [(target_width, round(height * target_width / width))]
    assert enhanced == [True]
