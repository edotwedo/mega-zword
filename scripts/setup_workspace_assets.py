"""Download public local-inference models and the pinned desktop helper. No private data is sent."""
import hashlib
import json
from pathlib import Path
import re
import urllib.request

ZOO = '47534e27c9851bb1128ccc0102f1145e27f23f98'
MODELS = {'yunet.onnx': 'face_detection_yunet/face_detection_yunet_2023mar.onnx',
          'sface.onnx': 'face_recognition_sface/face_recognition_sface_2021dec.onnx'}


def install(root):
    root.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, model in MODELS.items():
        pointer_url = f'https://raw.githubusercontent.com/opencv/opencv_zoo/{ZOO}/models/{model}'
        pointer = urllib.request.urlopen(pointer_url, timeout=30).read().decode()
        expected = re.search(r'oid sha256:([a-f0-9]{64})', pointer).group(1)
        url = f'https://media.githubusercontent.com/media/opencv/opencv_zoo/{ZOO}/models/{model}'
        path = root / name
        data = path.read_bytes() if path.exists() else urllib.request.urlopen(url, timeout=120).read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected:
            raise ValueError(f'{name} model hash mismatch')
        path.write_bytes(data)
        manifest[name] = dict(url=url, sha256=digest)
    url = ('https://github.com/Ciantic/VirtualDesktopAccessor/releases/download/'
           '2024-12-16-windows11/VirtualDesktopAccessor.dll')
    data = urllib.request.urlopen(url, timeout=60).read()
    (root / 'VirtualDesktopAccessor.dll').write_bytes(data)
    manifest['VirtualDesktopAccessor.dll'] = dict(url=url, sha256=hashlib.sha256(data).hexdigest())
    (root / 'assets.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Installed and recorded local face models and desktop helper; no camera opened.')


if __name__ == '__main__':
    install(Path.home() / '.megazword/workspace')
