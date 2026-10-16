"""Opt-in, local-only owner matching with OpenCV YuNet and SFace."""
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import time

from .presence import ReturnGate
from .workspace import load, save


def user_protect(data, decrypt=False):
    """Windows DPAPI binds the face template to the current Windows account."""
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    api = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    api.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    api.restype = wintypes.BOOL
    if not api(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(result.data)


def matches(scores, threshold=.50):
    return any(score >= threshold for score in scores)


class OwnerCamera:
    def __init__(self, root, enrolled=True):
        import cv2
        import numpy as np
        self.cv, self.np = cv2, np
        self.references = []
        if enrolled:
            if not (root / 'owner.dpapi').exists():
                raise ValueError('Use the Enroll my face desktop shortcut first. Only Phil triggers the camera.')
            data = user_protect((root / 'owner.dpapi').read_bytes(), decrypt=True)
            self.references = [np.asarray(x, dtype=np.float32) for x in json.loads(data)]
            if not self.references:
                raise ValueError('Owner enrollment is empty; enroll again')
        self.detector = cv2.FaceDetectorYN.create(str(root / 'yunet.onnx'), '', (640, 480), .85)
        self.recognizer = cv2.FaceRecognizerSF.create(str(root / 'sface.onnx'), '')
        self.capture = cv2.VideoCapture(0)
        if not self.capture.isOpened():
            self.capture.release()
            raise ValueError('Cannot open the webcam; close another camera app and retry')

    def frame(self):
        ok, frame = self.capture.read()
        if not ok:
            raise ValueError('Camera stopped returning frames')
        height, width = frame.shape[:2]
        target = min(640, width)
        frame = self.cv.resize(frame, (target, round(height * target / width)))
        self.detector.setInputSize((frame.shape[1], frame.shape[0]))
        faces = self.detector.detect(frame)[1]
        features = []
        for face in ([] if faces is None else faces):
            aligned = self.recognizer.alignCrop(frame, face)
            features.append(self.recognizer.feature(aligned))
        return frame, features

    def read(self):
        _, features = self.frame()
        return matches([self.recognizer.match(feature, ref, self.cv.FaceRecognizerSF_FR_COSINE)
                        for feature in features for ref in self.references])

    def close(self):
        self.capture.release()


def enroll(root):
    """Only deliberate SPACE presses enroll. No unattended enrollment or saved photos."""
    camera = OwnerCamera(root, enrolled=False)
    cv = camera.cv
    samples = []
    try:
        while len(samples) < 5:
            frame, features = camera.frame()
            cv.putText(frame, f'Phil only. SPACE: save pose {len(samples)+1}/5. ESC: cancel',
                       (8, 25), cv.FONT_HERSHEY_SIMPLEX, .52, (0, 255, 0), 1)
            cv.imshow('Enroll Phil - local camera', frame)
            key = cv.waitKey(50) & 255
            if key == 27 or cv.getWindowProperty('Enroll Phil - local camera', cv.WND_PROP_VISIBLE) < 1:
                return 0
            if key == 32 and len(features) == 1:
                feature = features[0]
                if samples and not matches([camera.recognizer.match(
                        feature, samples[0], cv.FaceRecognizerSF_FR_COSINE)]):
                    continue
                samples.append(feature)
        from .filelock import write_atomic
        template = json.dumps([x.tolist() for x in samples]).encode()
        # Atomic replace; no raw frame or plaintext embedding is written to disk.
        encrypted = user_protect(template)
        path = root / 'owner.dpapi'
        temp = root / 'owner.dpapi.tmp'
        temp.write_bytes(encrypted)
        os.replace(temp, path)
        save(root / 'camera-status.json', {'state': 'enrolled', 'time': time.time()})
    finally:
        camera.close()
        cv.destroyAllWindows()
    windowless = str(__import__('pathlib').Path(sys.executable).with_name('pythonw.exe'))
    subprocess.Popen([windowless, '-m', 'megazword.workspace', 'watch'],
                     env=dict(os.environ, PYTHONPATH=str(__import__('pathlib').Path(__file__).resolve().parents[1])),
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return 0


def watch(root):
    if not (root / 'owner.dpapi').exists():
        save(root / 'camera-status.json', {'state': 'enrollment required'})
        return 0
    from .filelock import locked
    with locked(root / 'camera-watcher', timeout=0) as acquired:
        if not acquired:
            return 0
        camera = OwnerCamera(root)
        gate = ReturnGate()
        try:
            save(root / 'camera-status.json', {'state': 'watching for Phil', 'time': time.time()})
            while True:
                if gate.observe(camera.read(), time.monotonic()):
                    save(root / 'return.json', {'event': time.time(), 'trigger': 'owner return'})
                    from .workspace import restore
                    try:
                        restore(root, automatic=True)
                    except (OSError, ValueError, subprocess.SubprocessError) as exc:
                        save(root / 'camera-status.json', {'state': 'restore failed; watcher continues',
                             'time': time.time(), 'error': str(exc)})
                time.sleep(.25)
        finally:
            camera.close()
