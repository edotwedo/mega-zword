# shortvid: free short videos for Spanda (and later RobinTHood)

Hive item #744. Our own replacement for paid tools like HeyCatch. Started by Tern-25 (Claude cloud), 2026-10-25.

## What it makes

From one small JSON script:
- `<id>.mp4`: 1080x1920 vertical video, 30 fps, words appear as they are "spoken"
- `<id>-slide-N.png`: 1080x1350 carousel slides for Instagram or TikTok photo mode
- `<id>.txt`: the post caption and hashtags, ready to paste

Phil reviews the folder and posts by hand. Nothing here posts anywhere.

## Run it

Needs Python with Pillow, and ffmpeg on PATH.

```
python tools/shortvid/shortvid.py batch tools/shortvid/scripts --out %USERPROFILE%\Desktop\videos\2026-10-25
```

Three Spanda scripts are in `scripts/`. A batch of three renders in about 35 seconds.

## Script format

```json
{
  "id": "spanda-001",
  "brand": "Spanda",
  "highlight": ["asking", "approve"],
  "scenes": [
    {"kicker": "small top line", "text": "Big caption.", "sub": "small line under it",
     "image": "shots/radar.png", "say": "what the voice says, if different"}
  ],
  "caption": "post text",
  "hashtags": ["leadgen"],
  "music": "music/bed.mp3",
  "theme": {"bg1": "#0b0f1a", "bg2": "#132a3a", "accent": "#29e0c2"}
}
```

`image` puts a real screenshot of the app in the frame. `music` mixes a quiet bed under it
(Phil can make these on his MPK). Paths are relative to the script file.

## Voice (optional)

Install Piper (free, runs offline) and pass a voice model: `--voice en_US-lessac-medium.onnx`.
Each scene then lasts as long as its voiceover. Without `--voice`, the video is captions only.

## Rules for scripts

- Honest claims only. No invented numbers, user counts or results.
- The price is $29.99, which matches the live checkout.
- Say that the user approves every reply. Spanda must not look like a spam tool.

## Next steps (for the seat that claims #744)

1. Add real Spanda screenshots to the scripts (`image`).
2. Install Piper on Phil's PC and pick a voice.
3. Write more scripts, five a day, from the Spanda copy in `interference/docs`.
4. Optional: a Remotion version for motion graphics (free for companies with 3 or fewer employees).
