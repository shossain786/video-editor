# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.1] - 2026-07-05

### Added
- **Live zoom-region preview** — after picking (or when you drag Zoom factor /
  Focus), the Zoom tab draws a yellow rectangle showing exactly what will fill
  the screen, so you can tune the zoom instead of guessing.

### Changed
- Clarified that "zoom to a box" keeps the whole selection visible, so a wide,
  short selection (e.g. two code lines spanning the width) only zooms a little —
  drag Zoom factor up to tighten. The preview makes this obvious.

## [0.4.0] - 2026-07-04

### Added
- **Smooth zoom** — the Zoom tab can now ease the punch-in in and out over an
  adjustable duration (via `zoompan`) instead of a hard cut. Toggle "Smooth"
  off for the original instant zoom.
- **Highlight tab** — spotlight a rectangular region for a time window: dims
  everything outside it and draws a colored border. Region, dim amount, border
  color, and thickness are all configurable. Good for calling out a code block.
- **Zoom and Highlight in the Combine tab** — both now stack in the pipeline
  (Cut → Speed → Denoise/Mute → Highlight → Caption → Zoom). Zoom runs as a
  chained second pass since it needs a filter graph the others don't.
- **Visual region picker for Highlight** — load a frame and click the two
  opposite corners to select the spotlight area; the X/Y/W/H sliders fill in
  automatically and the box is drawn on the preview. Manual sliders still work.
- **Visual zoom-to-box for Zoom** — load a frame and click the two opposite
  corners around the region to frame (e.g. two lines of code); the zoom factor
  and focus point are computed to fit that box (zoom clamped to the slider
  range). Manual sliders still work.

## [0.3.0] - 2026-07-04

### Added
- **Zoom tab** — punch-in zoom onto a region for a time window, for
  highlighting things like a line of code. Set start/end, a zoom factor, and a
  focus point (X/Y as a % of the frame); the full frame shows outside the
  window and the zoomed region fills it inside.

## [0.2.2] - 2026-07-04

### Changed
- Combine tab: each step now auto-enables its checkbox as soon as you edit any
  of its fields (cut times, speed factor, denoise method, or any caption
  setting), so a step can't be silently skipped by forgetting to tick it. You
  can still untick a checkbox to skip that step.

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

[Unreleased]: https://github.com/shossain786/video-editor/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/shossain786/video-editor/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/shossain786/video-editor/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/shossain786/video-editor/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/shossain786/video-editor/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/shossain786/video-editor/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/shossain786/video-editor/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/shossain786/video-editor/releases/tag/v0.1.0
