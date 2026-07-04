# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-07-04

### Fixed
- Captions were silently dropped (or errored) when added through the UI:
  `gr.Dataframe` passed a pandas DataFrame, which the caption builder iterated
  as column names instead of rows. The tables now hand over a plain array, and
  the builder also tolerates a DataFrame defensively. Affected both the Caption
  and Combine tabs.

## [0.2.0] - 2026-07-04

### Added
- **Combine (all-in-one) tab** — run Cut, Speed, Denoise/Mute, and Caption
  together in a single ffmpeg pass instead of one operation at a time. Steps
  apply in a fixed order (Cut → Speed → Denoise/Mute → Caption); caption times
  are on the final timeline after any speed change.
- **Timed captions** — Caption tab now takes a table of rows (Start / End / Text),
  burning each as a separate overlay shown only during its time window
  (e.g. 2–6 s one line, 6–8 s another). Times accept seconds or `HH:MM:SS`;
  a blank End shows the caption to the end of the clip.
- **Caption colors** — pickers for text color and background color, plus a
  background-opacity slider.

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

[Unreleased]: https://github.com/shossain786/video-editor/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/shossain786/video-editor/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/shossain786/video-editor/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/shossain786/video-editor/releases/tag/v0.1.0
