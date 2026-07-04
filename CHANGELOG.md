# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-04

### Added
- Local Gradio UI (`app.py`) wrapping FFmpeg — runs at `http://localhost:7860`.
- **Caption** — burn text onto video with selectable position and font size.
- **Speed** — 0.25×–4× playback; chains `atempo` for pitch-correct audio, optional mute.
- **GIF** — palette-based conversion with optional trim, width, and FPS control.
- **Cut** — start/end trim, re-encoded for frame accuracy.
- **Mute** — strips audio with no re-encode.
- **Denoise** — AI `arnndn` model for voice, with `afftdn` FFT fallback.
- `run.sh` launcher, pinned `requirements.txt`, and bundled RNN denoise model.

[Unreleased]: https://github.com/shossain786/video-editor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/shossain786/video-editor/releases/tag/v0.1.0
