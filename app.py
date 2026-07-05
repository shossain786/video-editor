"""
Personal video editor — a local FFmpeg wrapper with a Gradio UI.

Operations: Caption, Speed, GIF, Cut, Mute, Denoise, Zoom, Highlight, plus a
Combine tab that chains them. Runs locally by shelling out to ffmpeg.

Run:  .venv/bin/python app.py   then open http://localhost:7860
"""

import os
import shlex
import subprocess
import tempfile
import uuid

import gradio as gr
import numpy as np
from PIL import Image, ImageDraw

__version__ = "0.4.1"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "output")
MODEL = os.path.join(HERE, "models", "denoise.rnnn")
os.makedirs(OUT_DIR, exist_ok=True)


def _out(suffix: str) -> str:
    """A fresh path in the output dir with the given extension, e.g. '.mp4'."""
    return os.path.join(OUT_DIR, f"{uuid.uuid4().hex[:8]}{suffix}")


def _run(cmd: list[str]) -> str:
    """Run ffmpeg, raising a readable Gradio error on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # ffmpeg puts the useful part at the end of stderr
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise gr.Error(f"ffmpeg failed:\n{tail}")
    return proc.stderr


def _need(video):
    if not video:
        raise gr.Error("Upload a video first.")
    return video


def _to_seconds(val) -> float | None:
    """Parse '2', '2.5', '1:30', or '00:00:02' into seconds. Blank -> None."""
    s = str(val).strip()
    if not s:
        return None
    if ":" in s:
        secs = 0.0
        for p in s.split(":"):               # accumulate H:M:S or M:S
            secs = secs * 60 + float(p)
        return secs
    return float(s)


def _ffcolor(hexstr: str, opacity: float = 1.0) -> str:
    """Turn a '#rrggbb' picker value into ffmpeg's '0xrrggbb@a' color form."""
    h = str(hexstr).strip().lstrip("#") or "000000"
    return f"0x{h}@{opacity:.3f}"


def _atempo_chain(factor: float) -> str:
    """
    ffmpeg's atempo only accepts 0.5–2.0, so decompose the factor into a
    chain of steps that multiply to it (e.g. 4x -> atempo=2,atempo=2).
    """
    steps = []
    f = factor
    while f > 2.0:
        steps.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        steps.append("atempo=0.5")
        f /= 0.5
    steps.append(f"atempo={f:.6f}")
    return ",".join(steps)


POSITIONS = {
    "Bottom": "x=(w-text_w)/2:y=h-text_h-40",
    "Top": "x=(w-text_w)/2:y=40",
    "Center": "x=(w-text_w)/2:y=(h-text_h)/2",
}


def _denoise_filter(method: str) -> str:
    """Pick the ffmpeg audio-denoise filter for the chosen method."""
    if method.startswith("arnndn") and os.path.exists(MODEL):
        return f"arnndn=m={MODEL}"
    return "afftdn=nf=-25"  # FFT denoise fallback


def _caption_draws(rows, text_color, bg_color, bg_opacity, position, fontsize):
    """Build a list of drawtext filters, one per non-empty caption row."""
    # gr.Dataframe may hand us a pandas DataFrame; normalize to list-of-rows.
    if hasattr(rows, "values") and hasattr(rows, "columns"):
        rows = rows.values.tolist()
    elif rows is None:
        rows = []
    pos = POSITIONS[position]
    fontcol = _ffcolor(text_color)
    boxcol = _ffcolor(bg_color, bg_opacity)
    draws = []
    for row in rows:
        if not row or len(row) < 3:
            continue
        start, end, text = row[0], row[1], row[2]
        if text is None or not str(text).strip():
            continue
        # escape characters that are special inside the filtergraph
        safe = (str(text).replace("\\", "\\\\")
                .replace(":", r"\:").replace("'", r"\\'"))
        d = (
            f"drawtext=text='{safe}':fontcolor={fontcol}:fontsize={int(fontsize)}:"
            f"box=1:boxcolor={boxcol}:boxborderw=12:{pos}"
        )
        s, e = _to_seconds(start), _to_seconds(end)
        if s is not None and e is not None:
            d += f":enable='between(t,{s},{e})'"
        elif s is not None:
            d += f":enable='gte(t,{s})'"
        draws.append(d)
    return draws


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def op_caption(video, rows, text_color, bg_color, bg_opacity, position, fontsize):
    """
    Burn one or more timed captions. `rows` is a table of [start, end, text];
    each row becomes a drawtext gated with enable=between(t,start,end). Blank
    start/end means "show for the whole clip".
    """
    _need(video)
    draws = _caption_draws(rows, text_color, bg_color, bg_opacity, position, fontsize)
    if not draws:
        raise gr.Error("Add at least one caption row with text.")
    out = _out(".mp4")
    _run(["ffmpeg", "-y", "-i", video, "-vf", ",".join(draws),
          "-c:a", "copy", out])
    return out


def op_speed(video, factor, keep_audio):
    _need(video)
    if factor <= 0:
        raise gr.Error("Speed factor must be > 0.")
    out = _out(".mp4")
    vf = f"setpts={1/factor:.6f}*PTS"
    if keep_audio:
        af = _atempo_chain(factor)
        _run(["ffmpeg", "-y", "-i", video,
              "-filter:v", vf, "-filter:a", af, out])
    else:
        _run(["ffmpeg", "-y", "-i", video, "-filter:v", vf, "-an", out])
    return out


def op_gif(video, fps, width, start, end):
    _need(video)
    out = _out(".gif")
    trim = []
    if start.strip():
        trim += ["-ss", start.strip()]
    if end.strip():
        trim += ["-to", end.strip()]
    vf = (
        f"fps={int(fps)},scale={int(width)}:-1:flags=lanczos,"
        f"split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
    )
    _run(["ffmpeg", "-y", *trim, "-i", video,
          "-filter_complex", vf, out])
    return out


def op_cut(video, start, end):
    _need(video)
    if not start.strip() and not end.strip():
        raise gr.Error("Enter a start and/or end time (e.g. 00:00:05).")
    out = _out(".mp4")
    args = ["ffmpeg", "-y"]
    if start.strip():
        args += ["-ss", start.strip()]
    if end.strip():
        args += ["-to", end.strip()]
    args += ["-i", video, "-c:v", "libx264", "-c:a", "aac", out]
    _run(args)
    return out


def op_mute(video):
    _need(video)
    out = _out(".mp4")
    _run(["ffmpeg", "-y", "-i", video, "-c", "copy", "-an", out])
    return out


def op_denoise(video, method):
    _need(video)
    out = _out(".mp4")
    _run(["ffmpeg", "-y", "-i", video, "-af", _denoise_filter(method),
          "-c:v", "copy", out])
    return out


def _dimensions(video) -> tuple[int, int]:
    """Return (width, height) of the first video stream via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", video],
        capture_output=True, text=True).stdout.strip()
    w, h = out.split("x")
    return int(w), int(h)


def _even(v: int) -> int:
    """Round down to an even number (libx264/yuv420p needs even dimensions)."""
    v = int(round(v))
    return v - (v % 2)


def _fps(video) -> float:
    """Return the (average) frame rate as a float via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", video],
        capture_output=True, text=True).stdout.strip()
    n, d = out.split("/") if "/" in out else (out, "1")
    return float(n) / float(d)


def _zoom_filter(video, s, e, zoom, focus_x, focus_y, smooth, ramp):
    """
    Build the video filtergraph (ending in [v]) for a region zoom during
    [s, e]. Smooth mode eases the zoom in/out over `ramp` seconds via zoompan;
    otherwise it's an instant punch-in via crop+overlay.
    """
    w, h = _dimensions(video)
    fx, fy = focus_x / 100.0, focus_y / 100.0

    if smooth:
        fps = _fps(video)
        r = max(0.05, ramp)
        t = f"on/{fps:.6f}"                               # output time in seconds
        # trapezoid: 1 -> zoom over `r`, hold, zoom -> 1 over `r` (commas escaped)
        zexpr = (f"1+({zoom}-1)*max(0\\,min(min(({t}-{s})/{r}\\,1)\\,"
                 f"min(({e}-{t})/{r}\\,1)))")
        xexpr = f"iw*{fx}-(iw/zoom)/2"
        yexpr = f"ih*{fy}-(ih/zoom)/2"
        return (f"zoompan=z='{zexpr}':x='{xexpr}':y='{yexpr}':"
                f"d=1:s={w}x{h}:fps={fps:.6f}[v]")

    cw, ch = _even(w / zoom), _even(h / zoom)             # cropped region size
    x = _even(max(0, min(w - cw, fx * w - cw / 2)))       # keep crop in-frame
    y = _even(max(0, min(h - ch, fy * h - ch / 2)))
    return (f"[0:v]split[base][z];"
            f"[z]crop={cw}:{ch}:{x}:{y},scale={w}:{h}[zoomed];"
            f"[base][zoomed]overlay=0:0:enable='between(t,{s},{e})'[v]")


def op_zoom(video, start, end, zoom, focus_x, focus_y, smooth, ramp):
    """
    Zoom onto a region for a time window — good for highlighting a line of code.
    Focus is the center point as a % of width/height. Smooth eases in/out.
    """
    _need(video)
    s, e = _to_seconds(start), _to_seconds(end)
    if s is None or e is None or e <= s:
        raise gr.Error("Enter a valid Start and End (End after Start).")
    if zoom <= 1:
        raise gr.Error("Zoom must be greater than 1.")

    filt = _zoom_filter(video, s, e, zoom, focus_x, focus_y, smooth, ramp)
    out = _out(".mp4")
    _run(["ffmpeg", "-y", "-i", video, "-filter_complex", filt,
          "-map", "[v]", "-map", "0:a?", "-c:a", "copy", out])
    return out


def _grab_frame(video, at):
    """Grab a still frame (RGB numpy) from `video` at time `at` for picking."""
    _need(video)
    s = _to_seconds(at) or 0
    tmp = _out(".png")
    _run(["ffmpeg", "-y", "-ss", str(s), "-i", video, "-frames:v", "1", tmp])
    frame = np.array(Image.open(tmp).convert("RGB"))
    # (display frame, keep a clean copy for redraws, reset the first-corner state)
    return frame, frame, None


def _draw_overlay(frame, box=None, dot=None, color=(255, 59, 48)):
    """Return a copy of `frame` with a rectangle and/or a corner dot drawn on."""
    im = Image.fromarray(frame).copy()
    d = ImageDraw.Draw(im)
    if box:
        x, y, w, h = box
        d.rectangle([x, y, x + w, y + h], outline=color, width=3)
    if dot:
        x, y = dot
        d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=color)
    return np.array(im)


def _pick_region(evt: gr.SelectData, first, orig):
    """
    Two-click region picker. First click marks a corner; second click computes
    the rectangle, fills the X/Y/W/H sliders (as %), and draws the box.
    Returns: (new first-state, x%, y%, w%, h%, display-image).
    """
    if orig is None:
        return first, gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
    h, w = orig.shape[:2]
    x, y = int(evt.index[0]), int(evt.index[1])
    if not first:
        return ([x, y], gr.update(), gr.update(), gr.update(), gr.update(),
                _draw_overlay(orig, dot=(x, y)))
    x0, y0 = first
    bx, by = min(x0, x), min(y0, y)
    bw, bh = abs(x - x0), abs(y - y0)
    return (None, round(bx / w * 100, 1), round(by / h * 100, 1),
            round(bw / w * 100, 1), round(bh / h * 100, 1),
            _draw_overlay(orig, box=(bx, by, bw, bh)))


def _pick_zoom_box(evt: gr.SelectData, first, orig, zmax=4.0, zmin=1.1):
    """
    Two-click zoom-to-box: click the two opposite corners around the region to
    frame (e.g. two lines of code). Computes the focus point AND a zoom factor
    that makes that box fill the frame, filling Zoom factor + Focus X/Y.
    Returns (new first-state, zoom, x%, y%, display-image).
    """
    if orig is None:
        return first, gr.update(), gr.update(), gr.update(), gr.update()
    h, w = orig.shape[:2]
    x, y = int(evt.index[0]), int(evt.index[1])
    if not first:
        return ([x, y], gr.update(), gr.update(), gr.update(),
                _draw_overlay(orig, dot=(x, y)))
    x0, y0 = first
    bx, by = min(x0, x), min(y0, y)
    bw, bh = max(1, abs(x - x0)), max(1, abs(y - y0))
    fx = (bx + bw / 2) / w * 100
    fy = (by + bh / 2) / h * 100
    # zoom so the crop region (W/z x H/z, frame aspect) just contains the box
    zoom = max(zmin, min(zmax, min(w / bw, h / bh)))
    return (None, round(zoom, 1), round(fx, 1), round(fy, 1),
            _draw_overlay(orig, box=(bx, by, bw, bh)))


def _preview_zoom(orig, zoom, fx, fy):
    """
    Draw the exact region that a zoom will make fill the screen: a rectangle of
    W/zoom x H/zoom (frame aspect) centered on the focus point. Lets you see and
    tune what gets zoomed. Returns the annotated frame (or a no-op update).
    """
    if orig is None or not zoom or zoom <= 1:
        return gr.update()
    h, w = orig.shape[:2]
    cw, ch = w / zoom, h / zoom
    cx, cy = fx / 100.0 * w, fy / 100.0 * h
    x = max(0, min(w - cw, cx - cw / 2))
    y = max(0, min(h - ch, cy - ch / 2))
    return _draw_overlay(orig, box=(x, y, cw, ch), color=(255, 215, 0))


def _highlight_boxes(w, h, s, e, rx, ry, rw, rh, dim, border_color, thickness):
    """Build the drawbox filters (4 dim margins + border) for a spotlight."""
    x = _even(max(0, min(w - 2, rx / 100.0 * w)))
    y = _even(max(0, min(h - 2, ry / 100.0 * h)))
    bw = _even(max(2, min(w - x, rw / 100.0 * w)))
    bh = _even(max(2, min(h - y, rh / 100.0 * h)))
    on = f"enable='between(t,{s},{e})'"
    dark = _ffcolor("#000000", dim)
    bcol = _ffcolor(border_color)
    return [
        f"drawbox=x=0:y=0:w={w}:h={y}:color={dark}:t=fill:{on}",
        f"drawbox=x=0:y={y + bh}:w={w}:h={h - (y + bh)}:color={dark}:t=fill:{on}",
        f"drawbox=x=0:y={y}:w={x}:h={bh}:color={dark}:t=fill:{on}",
        f"drawbox=x={x + bw}:y={y}:w={w - (x + bw)}:h={bh}:color={dark}:t=fill:{on}",
        f"drawbox=x={x}:y={y}:w={bw}:h={bh}:color={bcol}:t={int(thickness)}:{on}",
    ]


def op_highlight(video, start, end, rx, ry, rw, rh, dim, border_color, thickness):
    """
    Spotlight a rectangular region during [start,end]: dim everything outside it
    and draw a border around it. Region given as %s of the frame (top-left x/y,
    width/height). Good for calling out a block of code without zooming.
    """
    _need(video)
    s, e = _to_seconds(start), _to_seconds(end)
    if s is None or e is None or e <= s:
        raise gr.Error("Enter a valid Start and End (End after Start).")
    w, h = _dimensions(video)
    filters = _highlight_boxes(w, h, s, e, rx, ry, rw, rh, dim, border_color, thickness)
    out = _out(".mp4")
    _run(["ffmpeg", "-y", "-i", video, "-vf", ",".join(filters),
          "-c:a", "copy", out])
    return out


def op_combine(video, do_cut, cut_start, cut_end, do_speed, speed_factor,
               do_denoise, denoise_method, do_mute,
               do_highlight, h_start, h_end, h_x, h_y, h_w, h_h, h_dim,
               h_border, h_thick,
               do_caption, rows, tcol, bcol, bop, position, fontsize,
               do_zoom, z_start, z_end, z_factor, z_fx, z_fy, z_smooth, z_ramp):
    """
    Run several operations in order: Cut -> Speed -> Highlight -> Caption
    (one ffmpeg pass) -> Zoom (a second pass, since it needs zoompan/overlay).
    Only enabled steps are applied. Highlight/Caption/Zoom times are on the
    final timeline (after any speed change).
    """
    _need(video)
    if not any([do_cut, do_speed, do_denoise, do_mute, do_highlight,
                do_caption, do_zoom]):
        raise gr.Error("Enable at least one operation.")

    pass1 = do_cut or do_speed or do_denoise or do_mute or do_highlight or do_caption
    mid = video

    if pass1:
        args = ["ffmpeg", "-y"]
        # Cut via input options so downstream filters see a trimmed clip.
        if do_cut:
            if cut_start.strip():
                args += ["-ss", cut_start.strip()]
            if cut_end.strip():
                args += ["-to", cut_end.strip()]
        args += ["-i", video]

        # Video chain: speed first, so highlight/caption times are on the final
        # (post-speed) timeline.
        vf = []
        if do_speed:
            if speed_factor <= 0:
                raise gr.Error("Speed factor must be > 0.")
            vf.append(f"setpts={1/speed_factor:.6f}*PTS")
        if do_highlight:
            hs, he = _to_seconds(h_start), _to_seconds(h_end)
            if hs is None or he is None or he <= hs:
                raise gr.Error("Highlight needs a valid Start and End.")
            w, h = _dimensions(video)
            vf += _highlight_boxes(w, h, hs, he, h_x, h_y, h_w, h_h,
                                   h_dim, h_border, h_thick)
        if do_caption:
            draws = _caption_draws(rows, tcol, bcol, bop, position, fontsize)
            if not draws:
                raise gr.Error("Caption is enabled but no row has text.")
            vf += draws

        af = []
        if do_speed and not do_mute:
            af.append(_atempo_chain(speed_factor))
        if do_denoise and not do_mute:
            af.append(_denoise_filter(denoise_method))

        if vf:
            args += ["-filter:v", ",".join(vf)]
        elif not do_cut:
            args += ["-c:v", "copy"]        # nothing touches video; copy it
        if do_mute:
            args += ["-an"]
        elif af:
            args += ["-filter:a", ",".join(af)]

        mid = _out(".mp4")
        args += [mid]
        _run(args)

    if do_zoom:
        return op_zoom(mid, z_start, z_end, z_factor, z_fx, z_fy,
                       z_smooth, z_ramp)
    return mid


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="Video Editor") as demo:
    gr.Markdown("# 🎬 Personal Video Editor\nLocal FFmpeg tool — pick a tab, upload, run.")

    with gr.Tab("Combine (all-in-one)"):
        gr.Markdown(
            "Enable the steps you want; they run in order: "
            "**Cut → Speed → Denoise/Mute → Highlight → Caption → Zoom**. "
            "Highlight / Caption / Zoom times are on the *final* timeline "
            "(after speed)."
        )
        cv = gr.Video(label="Input")

        with gr.Accordion("✂️ Cut", open=False):
            c_cut = gr.Checkbox(label="Enable cut (auto-checks when you edit below)")
            with gr.Row():
                c_cs = gr.Textbox(label="Start (e.g. 00:00:05)")
                c_ce = gr.Textbox(label="End (e.g. 00:00:20)")

        with gr.Accordion("⏩ Speed", open=False):
            c_speed = gr.Checkbox(label="Enable speed change (auto-checks when you edit below)")
            c_fac = gr.Slider(0.25, 4.0, value=2.0, step=0.05, label="Speed factor")

        with gr.Accordion("🔇 Audio (denoise / mute)", open=False):
            c_den = gr.Checkbox(label="Enable denoise (auto-checks when you pick a method)")
            c_denm = gr.Radio(
                ["arnndn (AI, best for voice)", "afftdn (FFT, no model)"],
                value="arnndn (AI, best for voice)", label="Denoise method")
            c_mute = gr.Checkbox(label="Mute (removes audio — overrides denoise)")

        with gr.Accordion("🔦 Highlight (spotlight a region)", open=False):
            c_hl = gr.Checkbox(label="Enable highlight (auto-checks when you edit below)")
            with gr.Row():
                c_hs = gr.Textbox(label="Start (e.g. 00:00:03)")
                c_he = gr.Textbox(label="End (e.g. 00:00:06)")
            with gr.Row():
                c_hx = gr.Slider(0, 100, value=20, step=1, label="X (%)")
                c_hy = gr.Slider(0, 100, value=45, step=1, label="Y (%)")
            with gr.Row():
                c_hw = gr.Slider(5, 100, value=60, step=1, label="Width (%)")
                c_hh = gr.Slider(5, 100, value=15, step=1, label="Height (%)")
            with gr.Row():
                c_hdim = gr.Slider(0, 0.95, value=0.6, step=0.05, label="Dim outside")
                c_hbc = gr.ColorPicker(value="#FF3B30", label="Border color")
                c_hth = gr.Slider(0, 12, value=4, step=1, label="Border thickness")

        with gr.Accordion("💬 Caption", open=False):
            c_cap = gr.Checkbox(label="Enable captions (auto-checks when you edit below)")
            c_rows = gr.Dataframe(
                headers=["Start", "End", "Text"],
                datatype=["str", "str", "str"],
                type="array",
                value=[["0", "4", "First caption"], ["4", "8", "Second caption"]],
                row_count=(1, "dynamic"),
                column_count=(3, "fixed"),
                label="Times in seconds or HH:MM:SS. Blank End = show to clip end.",
            )
            with gr.Row():
                c_tcol = gr.ColorPicker(value="#FFFFFF", label="Text color")
                c_bcol = gr.ColorPicker(value="#000000", label="Background color")
                c_bop = gr.Slider(0, 1, value=0.5, step=0.05, label="Background opacity")
            with gr.Row():
                c_pos = gr.Radio(["Bottom", "Top", "Center"], value="Bottom", label="Position")
                c_fs = gr.Slider(12, 96, value=36, step=1, label="Font size")

        with gr.Accordion("🔍 Zoom (punch-in)", open=False):
            c_zoom = gr.Checkbox(label="Enable zoom (auto-checks when you edit below)")
            with gr.Row():
                c_zs = gr.Textbox(label="Start (e.g. 00:00:03)")
                c_ze = gr.Textbox(label="End (e.g. 00:00:06)")
            c_zf = gr.Slider(1.1, 4.0, value=2.0, step=0.1, label="Zoom factor")
            with gr.Row():
                c_zx = gr.Slider(0, 100, value=50, step=1, label="Focus X (%)")
                c_zy = gr.Slider(0, 100, value=50, step=1, label="Focus Y (%)")
            with gr.Row():
                c_zsm = gr.Checkbox(value=True, label="Smooth (ease in/out)")
                c_zr = gr.Slider(0.1, 1.0, value=0.3, step=0.05, label="Ease duration (s)")

        c_out = gr.Video(label="Result")
        gr.Button("Run pipeline", variant="primary").click(
            op_combine,
            [cv, c_cut, c_cs, c_ce, c_speed, c_fac, c_den, c_denm, c_mute,
             c_hl, c_hs, c_he, c_hx, c_hy, c_hw, c_hh, c_hdim, c_hbc, c_hth,
             c_cap, c_rows, c_tcol, c_bcol, c_bop, c_pos, c_fs,
             c_zoom, c_zs, c_ze, c_zf, c_zx, c_zy, c_zsm, c_zr],
            c_out)

        # Auto-enable each step the moment its fields are touched, so you can't
        # forget the checkbox. (You can still untick a checkbox to skip a step.)
        _enable = lambda: gr.update(value=True)
        for field in (c_cs, c_ce):
            field.change(_enable, None, c_cut)
        c_fac.change(_enable, None, c_speed)
        c_denm.change(_enable, None, c_den)
        for field in (c_hs, c_he, c_hx, c_hy, c_hw, c_hh, c_hdim, c_hbc, c_hth):
            field.change(_enable, None, c_hl)
        for field in (c_rows, c_tcol, c_bcol, c_bop, c_pos, c_fs):
            field.change(_enable, None, c_cap)
        for field in (c_zs, c_ze, c_zf, c_zx, c_zy, c_zsm, c_zr):
            field.change(_enable, None, c_zoom)

    with gr.Tab("Caption"):
        v = gr.Video(label="Input")
        rows = gr.Dataframe(
            headers=["Start", "End", "Text"],
            datatype=["str", "str", "str"],
            type="array",
            value=[["0", "4", "First caption"], ["4", "8", "Second caption"]],
            row_count=(1, "dynamic"),
            column_count=(3, "fixed"),
            label="Captions — time in seconds or HH:MM:SS. Blank End = show to clip end.",
        )
        with gr.Row():
            tcol = gr.ColorPicker(value="#FFFFFF", label="Text color")
            bcol = gr.ColorPicker(value="#000000", label="Background color")
            bop = gr.Slider(0, 1, value=0.5, step=0.05, label="Background opacity")
        with gr.Row():
            pos = gr.Radio(["Bottom", "Top", "Center"], value="Bottom", label="Position")
            fs = gr.Slider(12, 96, value=36, step=1, label="Font size")
        out = gr.Video(label="Result")
        gr.Button("Add captions", variant="primary").click(
            op_caption, [v, rows, tcol, bcol, bop, pos, fs], out)

    with gr.Tab("Zoom"):
        gr.Markdown(
            "Punch-in zoom for a time window — e.g. to frame two lines of code. "
            "**Zoom to a box:** set a Start time, load the frame, then click the "
            "**two opposite corners** around the region. The **yellow rectangle** "
            "then shows *exactly what will fill the screen* — drag **Zoom factor** "
            "up to tighten it (a wide selection only zooms a little, since the "
            "whole box has to stay visible). Times set *when* the zoom happens."
        )
        v = gr.Video(label="Input")
        with gr.Row():
            zs = gr.Textbox(label="Start (e.g. 00:00:03)")
            ze = gr.Textbox(label="End (e.g. 00:00:06)")
        zpick_btn = gr.Button("① Load frame at Start")
        zpick_img = gr.Image(
            label="② Click the two opposite corners around the region",
            type="numpy", interactive=True, height=320)
        z_orig = gr.State()     # clean frame copy for redraws
        z_first = gr.State()    # first corner clicked, or None
        zf = gr.Slider(1.1, 4.0, value=2.0, step=0.1, label="Zoom factor")
        with gr.Row():
            zx = gr.Slider(0, 100, value=50, step=1, label="Focus X (% from left)")
            zy = gr.Slider(0, 100, value=50, step=1, label="Focus Y (% from top)")
        with gr.Row():
            zsm = gr.Checkbox(value=True, label="Smooth (ease in/out)")
            zr = gr.Slider(0.1, 1.0, value=0.3, step=0.05, label="Ease duration (s)")
        out = gr.Video(label="Result")
        gr.Button("Apply zoom", variant="primary").click(
            op_zoom, [v, zs, ze, zf, zx, zy, zsm, zr], out)

        zpick_btn.click(_grab_frame, [v, zs], [zpick_img, z_orig, z_first])
        zpick_img.select(_pick_zoom_box, [z_first, z_orig],
                         [z_first, zf, zx, zy, zpick_img])
        # Live preview: show the exact crop region whenever zoom/focus changes.
        for comp in (zf, zx, zy):
            comp.change(_preview_zoom, [z_orig, zf, zx, zy], zpick_img)

    with gr.Tab("Highlight"):
        gr.Markdown(
            "Spotlight a region for a time window — dims everything outside it "
            "and draws a border. **Select the area visually:** load a frame, then "
            "click the two opposite corners of the region. Or set X/Y/W/H (% of "
            "frame) by hand."
        )
        v = gr.Video(label="Input")
        with gr.Row():
            hs = gr.Textbox(label="Start (e.g. 00:00:03)")
            he = gr.Textbox(label="End (e.g. 00:00:06)")
        pick_btn = gr.Button("① Load frame at Start")
        pick_img = gr.Image(
            label="② Click two opposite corners to select the region",
            type="numpy", interactive=True, height=320)
        _orig = gr.State()     # clean frame copy for redraws
        _first = gr.State()    # first corner clicked, or None
        with gr.Row():
            hx = gr.Slider(0, 100, value=20, step=1, label="X (% from left)")
            hy = gr.Slider(0, 100, value=45, step=1, label="Y (% from top)")
        with gr.Row():
            hw = gr.Slider(5, 100, value=60, step=1, label="Width (%)")
            hh = gr.Slider(5, 100, value=15, step=1, label="Height (%)")
        with gr.Row():
            hdim = gr.Slider(0, 0.95, value=0.6, step=0.05, label="Dim outside (opacity)")
            hbc = gr.ColorPicker(value="#FF3B30", label="Border color")
            hth = gr.Slider(0, 12, value=4, step=1, label="Border thickness")
        out = gr.Video(label="Result")
        gr.Button("Apply highlight", variant="primary").click(
            op_highlight, [v, hs, he, hx, hy, hw, hh, hdim, hbc, hth], out)

        pick_btn.click(_grab_frame, [v, hs], [pick_img, _orig, _first])
        pick_img.select(_pick_region, [_first, _orig],
                        [_first, hx, hy, hw, hh, pick_img])

    with gr.Tab("Speed"):
        v = gr.Video(label="Input")
        with gr.Row():
            fac = gr.Slider(0.25, 4.0, value=2.0, step=0.05, label="Speed factor (2 = 2× faster)")
            ka = gr.Checkbox(value=True, label="Keep audio (pitch-corrected)")
        out = gr.Video(label="Result")
        gr.Button("Change speed", variant="primary").click(
            op_speed, [v, fac, ka], out)

    with gr.Tab("GIF"):
        v = gr.Video(label="Input")
        with gr.Row():
            fps = gr.Slider(5, 30, value=15, step=1, label="FPS")
            w = gr.Slider(120, 1080, value=480, step=20, label="Width (px)")
        with gr.Row():
            s = gr.Textbox(label="Start (optional, e.g. 00:00:02)")
            e = gr.Textbox(label="End (optional, e.g. 00:00:07)")
        out = gr.Image(label="Result GIF")
        gr.Button("Convert to GIF", variant="primary").click(
            op_gif, [v, fps, w, s, e], out)

    with gr.Tab("Cut"):
        v = gr.Video(label="Input")
        with gr.Row():
            s = gr.Textbox(label="Start (e.g. 00:00:05)")
            e = gr.Textbox(label="End (e.g. 00:00:20)")
        out = gr.Video(label="Result")
        gr.Button("Cut", variant="primary").click(op_cut, [v, s, e], out)

    with gr.Tab("Mute"):
        v = gr.Video(label="Input")
        out = gr.Video(label="Result")
        gr.Button("Mute (remove audio)", variant="primary").click(op_mute, [v], out)

    with gr.Tab("Denoise"):
        v = gr.Video(label="Input")
        m = gr.Radio(
            ["arnndn (AI, best for voice)", "afftdn (FFT, no model)"],
            value="arnndn (AI, best for voice)", label="Method")
        out = gr.Video(label="Result")
        gr.Button("Reduce noise", variant="primary").click(op_denoise, [v, m], out)

    gr.Markdown(f"Outputs saved to `{OUT_DIR}` · v{__version__}")


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, inbrowser=False)
