"""shortvid: turn a small JSON script into vertical short videos and carousel slides.

Free replacement for paid "AI marketing video" tools (Hive #744). No paid APIs.
Needs: Python 3.10+, Pillow, ffmpeg on PATH. Optional: Piper TTS (`piper` on PATH) for a voiceover.

    python tools/shortvid/shortvid.py render tools/shortvid/scripts/spanda-001.json --out out/2026-10-25
    python tools/shortvid/shortvid.py batch tools/shortvid/scripts --out out/2026-10-25

Each script makes:
    <id>.mp4           1080x1920, 30 fps, H.264, burned-in captions
    <id>-slide-N.png   1080x1350 carousel slides (Instagram / TikTok photo mode)
    <id>.txt           the post caption and hashtags, ready to paste

Phil reviews the folder and posts by hand. Nothing here posts anywhere.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920          # video frame
SW, SH = 1080, 1350        # carousel slide
FPS = 30
WORDS_PER_SEC = 2.6        # caption pace when there is no voiceover
MIN_SCENE = 1.6
HOLD_END = 0.9             # seconds the full text holds at the end of a scene

FONT_DIRS = [Path("/usr/share/fonts"), Path("C:/Windows/Fonts"), Path("/Library/Fonts"),
             Path.home() / "AppData/Local/Microsoft/Windows/Fonts"]
BOLD_NAMES = ["Inter-ExtraBold.otf", "Inter-Bold.otf", "InterDisplay-Bold.otf", "seguibl.ttf",
              "arialbd.ttf", "DejaVuSans-Bold.ttf"]
REG_NAMES = ["Inter-Medium.otf", "Inter-Regular.otf", "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]


def find_font(names: list[str]) -> str:
    for name in names:
        for root in FONT_DIRS:
            if root.exists():
                hit = next(root.rglob(name), None)
                if hit:
                    return str(hit)
    raise SystemExit(f"No font found (looked for {names}). Install Inter or DejaVu.")


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


class Theme:
    def __init__(self, raw: dict):
        self.bg1 = hex_rgb(raw.get("bg1", "#0b0f1a"))
        self.bg2 = hex_rgb(raw.get("bg2", "#132a3a"))
        self.ink = hex_rgb(raw.get("ink", "#f4f7fb"))
        self.dim = hex_rgb(raw.get("dim", "#8aa0b4"))
        self.accent = hex_rgb(raw.get("accent", "#29e0c2"))
        self.bold = find_font(BOLD_NAMES)
        self.reg = find_font(REG_NAMES)


def background(w: int, h: int, t: Theme) -> Image.Image:
    img = Image.new("RGB", (w, h), t.bg1)
    px = ImageDraw.Draw(img)
    for y in range(h):
        k = y / (h - 1)
        px.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(t.bg1, t.bg2)))
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse([w * 0.45, -h * 0.15, w * 1.35, h * 0.35], fill=t.accent)
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    return Image.blend(img, Image.composite(glow, img, glow.convert("L")), 0.25)


def wrap(draw: ImageDraw.ImageDraw, words: list[str], font, width: int) -> list[list[str]]:
    lines, line = [], []
    for word in words:
        trial = " ".join(line + [word])
        if line and draw.textlength(trial, font=font) > width:
            lines.append(line)
            line = [word]
        else:
            line.append(word)
    if line:
        lines.append(line)
    return lines


def fit_font(draw, words, path, width, max_lines, start, floor=56):
    size = start
    while size > floor:
        font = ImageFont.truetype(path, size)
        if len(wrap(draw, words, font, width)) <= max_lines:
            return font
        size -= 6
    return ImageFont.truetype(path, floor)


def draw_text_block(img, text, t: Theme, shown: int | None, top: int, width: int,
                    max_lines: int, size: int, highlight: set[str]):
    """Draw text centred, revealing the first `shown` words (None = all). Highlighted words use accent."""
    draw = ImageDraw.Draw(img)
    words = text.split()
    font = fit_font(draw, words, t.bold, width, max_lines, size)
    lines = wrap(draw, words, font, width)
    lh = int(font.size * 1.18)
    y = top - (len(lines) * lh) // 2
    count = 0
    for line in lines:
        x = (img.width - draw.textlength(" ".join(line), font=font)) / 2
        for word in line:
            visible = shown is None or count < shown
            key = word.strip(".,!?:;\"'").lower()
            colour = t.accent if key in highlight else t.ink
            if visible:
                draw.text((x + 4, y + 5), word, font=font, fill=(0, 0, 0))   # soft shadow
                draw.text((x, y), word, font=font, fill=colour)
            x += draw.textlength(word + " ", font=font)
            count += 1
        y += lh
    return y


def brand_bar(img, brand: str, t: Theme, bottom: bool = True):
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(t.bold, 44)
    y = img.height - 150 if bottom else 90
    pad = 26
    tw = draw.textlength(brand, font=font)
    x = (img.width - tw) / 2
    draw.rounded_rectangle([x - pad - 30, y - 18, x + tw + pad, y + 62], radius=40,
                           outline=t.accent, width=3)
    draw.ellipse([x - pad - 12, y + 14, x - pad + 4, y + 30], fill=t.accent)
    draw.text((x, y - 4), brand, font=font, fill=t.ink)


def place_image(img, path: Path, box: tuple[int, int, int, int], t: Theme):
    """Fit a screenshot into box with rounded corners and an accent frame."""
    shot = Image.open(path).convert("RGB")
    bw, bh = box[2] - box[0], box[3] - box[1]
    scale = min(bw / shot.width, bh / shot.height)
    shot = shot.resize((int(shot.width * scale), int(shot.height * scale)), Image.LANCZOS)
    x = box[0] + (bw - shot.width) // 2
    y = box[1] + (bh - shot.height) // 2
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, *shot.size], radius=28, fill=255)
    ImageDraw.Draw(img).rounded_rectangle([x - 6, y - 6, x + shot.width + 6, y + shot.height + 6],
                                          radius=34, fill=t.accent)
    img.paste(shot, (x, y), mask)


def frame(scene: dict, t: Theme, base: Image.Image, root: Path, shown, brand: str,
          index: int, total: int, highlight: set[str]) -> Image.Image:
    img = base.copy()
    draw = ImageDraw.Draw(img)
    # progress dots, so a viewer sees how long the clip is
    gap, r = 34, 9
    x0 = (W - gap * (total - 1)) / 2
    for i in range(total):
        fill = t.accent if i <= index else t.dim
        draw.ellipse([x0 + i * gap - r, 70 - r, x0 + i * gap + r, 70 + r], fill=fill)
    if scene.get("kicker"):
        kf = ImageFont.truetype(t.bold, 40)
        k = scene["kicker"].upper()
        draw.text(((W - draw.textlength(k, font=kf)) / 2, 150), k, font=kf, fill=t.accent)
    image = scene.get("image")
    if image and (root / image).exists():
        place_image(img, root / image, (90, 860, W - 90, 1600), t)
        draw_text_block(img, scene["text"], t, shown, 520, W - 140, 4, 104, highlight)
    else:
        draw_text_block(img, scene["text"], t, shown, 900, W - 140, 6, 118, highlight)
    if scene.get("sub"):
        sf = ImageFont.truetype(t.reg, 46)
        lines = wrap(draw, scene["sub"].split(), sf, W - 200)
        y = 1560 if not image else 1660
        for line in lines:
            s = " ".join(line)
            draw.text(((W - draw.textlength(s, font=sf)) / 2, y), s, font=sf, fill=t.dim)
            y += 62
    brand_bar(img, brand, t)
    return img


def slide(scene: dict, t: Theme, root: Path, brand: str, n: int, total: int,
          highlight: set[str]) -> Image.Image:
    img = background(SW, SH, t)
    draw = ImageDraw.Draw(img)
    nf = ImageFont.truetype(t.bold, 36)
    draw.text((70, 70), f"{n}/{total}", font=nf, fill=t.dim)
    image = scene.get("image")
    if image and (root / image).exists():
        draw_text_block(img, scene["text"], t, None, 330, SW - 140, 4, 84, highlight)
        place_image(img, root / image, (110, 560, SW - 110, 1130), t)
    else:
        end = draw_text_block(img, scene["text"], t, None, 560, SW - 140, 6, 100, highlight)
        if scene.get("sub"):
            sf = ImageFont.truetype(t.reg, 42)
            y = end + 40
            for line in wrap(draw, scene["sub"].split(), sf, SW - 200):
                s = " ".join(line)
                draw.text(((SW - draw.textlength(s, font=sf)) / 2, y), s, font=sf, fill=t.dim)
                y += 56
    brand_bar(img, brand, t)
    if n < total:
        af = ImageFont.truetype(t.bold, 44)
        draw.text((SW - 140, SH - 140), "→", font=af, fill=t.accent)
    return img


def tts(text: str, out: Path, voice: str | None) -> float | None:
    """Piper voiceover if available. Returns seconds, or None to fall back to silent captions."""
    if not voice or not shutil.which("piper"):
        return None
    subprocess.run(["piper", "--model", voice, "--output_file", str(out)],
                   input=text.encode(), check=True, capture_output=True)
    with wave.open(str(out)) as w:
        return w.getnframes() / w.getframerate()


def render(script_path: Path, out_dir: Path, voice: str | None = None, keep: bool = False) -> Path:
    spec = json.loads(script_path.read_text(encoding="utf-8"))
    root = script_path.parent
    t = Theme(spec.get("theme", {}))
    brand = spec.get("brand", "")
    highlight = {w.lower() for w in spec.get("highlight", [])}
    scenes = spec["scenes"]
    vid = spec["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"shortvid-{vid}-"))
    base = background(W, H, t)
    concat, audio_parts = [], []
    try:
        for i, scene in enumerate(scenes):
            words = scene["text"].split()
            voiced = tts(scene.get("say", scene["text"]), work / f"a{i}.wav", voice)
            length = voiced if voiced else max(MIN_SCENE, len(words) / WORDS_PER_SEC + HOLD_END)
            reveal = max(0.35, length - HOLD_END)
            step = reveal / len(words)
            for k in range(1, len(words) + 1):
                p = work / f"s{i:02d}-{k:03d}.png"
                frame(scene, t, base, root, k, brand, i, len(scenes), highlight).save(p)
                dur = step if k < len(words) else length - step * (len(words) - 1)
                concat.append((p, dur))
            if voiced:
                audio_parts.append(work / f"a{i}.wav")
            else:
                silent = work / f"a{i}.wav"
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                                "anullsrc=r=22050:cl=mono", "-t", f"{length:.3f}", str(silent)],
                               check=True)
                audio_parts.append(silent)
        listing = work / "frames.txt"
        with listing.open("w") as f:
            for p, d in concat:
                f.write(f"file '{p.as_posix()}'\nduration {d:.4f}\n")
            f.write(f"file '{concat[-1][0].as_posix()}'\n")
        alist = work / "audio.txt"
        alist.write_text("".join(f"file '{p.as_posix()}'\n" for p in audio_parts))
        audio = work / "audio.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(alist), "-c", "copy", str(audio)], check=True)
        music = spec.get("music")
        mp4 = out_dir / f"{vid}.mp4"
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
               "-i", str(audio)]
        if music and (root / music).exists():
            cmd += ["-stream_loop", "-1", "-i", str(root / music), "-filter_complex",
                    "[2:a]volume=0.18[m];[1:a][m]amix=inputs=2:duration=first[a]", "-map", "0:v",
                    "-map", "[a]"]
        else:
            cmd += ["-map", "0:v", "-map", "1:a"]
        cmd += ["-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "20", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
                str(mp4)]
        subprocess.run(cmd, check=True)
        for n, scene in enumerate(scenes, 1):
            slide(scene, t, root, brand, n, len(scenes), highlight).save(out_dir / f"{vid}-slide-{n}.png")
        caption = spec.get("caption", "")
        tags = " ".join("#" + x.lstrip("#") for x in spec.get("hashtags", []))
        (out_dir / f"{vid}.txt").write_text(f"{caption}\n\n{tags}\n".strip() + "\n", encoding="utf-8")
        return mp4
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("render", "batch"):
        p = sub.add_parser(name)
        p.add_argument("path", type=Path)
        p.add_argument("--out", type=Path, required=True)
        p.add_argument("--voice", help="path to a Piper .onnx voice model (optional)")
        p.add_argument("--keep", action="store_true", help="keep the temp frame folder")
    args = ap.parse_args(argv)
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is not on PATH")
    paths = [args.path] if args.cmd == "render" else sorted(args.path.glob("*.json"))
    for p in paths:
        print(render(p, args.out, args.voice, args.keep))


if __name__ == "__main__":
    main()
