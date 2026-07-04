# 🎬 Video Editor

A personal, local video editor — a thin [Gradio](https://gradio.app) UI over
[FFmpeg](https://ffmpeg.org). Everything runs on your machine; nothing uploads
anywhere.

## Features

| Operation | What it does |
|-----------|--------------|
| **Caption** | Burn text onto video (position + font size) |
| **Speed** | 0.25×–4×, pitch-corrected audio, optional mute |
| **GIF** | Palette-based GIF with trim / width / FPS control |
| **Cut** | Frame-accurate start/end trim |
| **Mute** | Strip audio instantly (no re-encode) |
| **Denoise** | AI (`arnndn`) for voice, or `afftdn` fallback |

## Requirements

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) on your `PATH`

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

```bash
./run.sh
```

Then open <http://localhost:7860>. Upload a video, pick a tab, run.
Results are also saved to `output/`.

## Adding an operation

Each operation is one function plus one tab in [`app.py`](app.py) (~15 lines).

## License

Personal use.

See [CHANGELOG.md](CHANGELOG.md) for version history.
