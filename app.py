"""
Personal video editor — a local FFmpeg wrapper with a Gradio UI.

Six operations: Caption, Speed, GIF, Cut, Mute, Denoise.
Everything runs locally by shelling out to ffmpeg. Nothing leaves your machine.

Run:  .venv/bin/python app.py   then open http://localhost:7860
"""

import os
import shlex
import subprocess
import tempfile
import uuid

import gradio as gr

__version__ = "0.2.0"

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


def op_combine(video, do_cut, cut_start, cut_end, do_speed, speed_factor,
               do_denoise, denoise_method, do_mute,
               do_caption, rows, tcol, bcol, bop, position, fontsize):
    """
    Run several operations in a single ffmpeg pass, in the order
    Cut -> Speed -> Denoise/Mute -> Caption. Only enabled steps are applied.
    Caption times are on the FINAL timeline (after any speed change).
    """
    _need(video)
    if not any([do_cut, do_speed, do_denoise, do_mute, do_caption]):
        raise gr.Error("Enable at least one operation.")

    args = ["ffmpeg", "-y"]
    # Cut is applied as input options so downstream filters see a trimmed clip.
    if do_cut:
        if cut_start.strip():
            args += ["-ss", cut_start.strip()]
        if cut_end.strip():
            args += ["-to", cut_end.strip()]
    args += ["-i", video]

    # Video filterchain: speed first (so caption t is on the final timeline).
    vf = []
    if do_speed:
        if speed_factor <= 0:
            raise gr.Error("Speed factor must be > 0.")
        vf.append(f"setpts={1/speed_factor:.6f}*PTS")
    if do_caption:
        draws = _caption_draws(rows, tcol, bcol, bop, position, fontsize)
        if not draws:
            raise gr.Error("Caption is enabled but no row has text.")
        vf += draws

    # Audio filterchain (skipped entirely if muting).
    af = []
    if do_speed and not do_mute:
        af.append(_atempo_chain(speed_factor))
    if do_denoise and not do_mute:
        af.append(_denoise_filter(denoise_method))

    if vf:
        args += ["-filter:v", ",".join(vf)]
    if do_mute:
        args += ["-an"]
    elif af:
        args += ["-filter:a", ",".join(af)]

    out = _out(".mp4")
    args += [out]
    _run(args)
    return out


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="Video Editor") as demo:
    gr.Markdown("# 🎬 Personal Video Editor\nLocal FFmpeg tool — pick a tab, upload, run.")

    with gr.Tab("Combine (all-in-one)"):
        gr.Markdown(
            "Enable the steps you want; they run in **one pass** in this order: "
            "**Cut → Speed → Denoise/Mute → Caption**. "
            "Caption times are on the *final* timeline (after speed)."
        )
        cv = gr.Video(label="Input")

        with gr.Accordion("✂️ Cut", open=False):
            c_cut = gr.Checkbox(label="Enable cut")
            with gr.Row():
                c_cs = gr.Textbox(label="Start (e.g. 00:00:05)")
                c_ce = gr.Textbox(label="End (e.g. 00:00:20)")

        with gr.Accordion("⏩ Speed", open=False):
            c_speed = gr.Checkbox(label="Enable speed change")
            c_fac = gr.Slider(0.25, 4.0, value=2.0, step=0.05, label="Speed factor")

        with gr.Accordion("🔇 Audio (denoise / mute)", open=False):
            c_den = gr.Checkbox(label="Enable denoise")
            c_denm = gr.Radio(
                ["arnndn (AI, best for voice)", "afftdn (FFT, no model)"],
                value="arnndn (AI, best for voice)", label="Denoise method")
            c_mute = gr.Checkbox(label="Mute (removes audio — overrides denoise)")

        with gr.Accordion("💬 Caption", open=False):
            c_cap = gr.Checkbox(label="Enable captions")
            c_rows = gr.Dataframe(
                headers=["Start", "End", "Text"],
                datatype=["str", "str", "str"],
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

        c_out = gr.Video(label="Result")
        gr.Button("Run pipeline", variant="primary").click(
            op_combine,
            [cv, c_cut, c_cs, c_ce, c_speed, c_fac, c_den, c_denm, c_mute,
             c_cap, c_rows, c_tcol, c_bcol, c_bop, c_pos, c_fs],
            c_out)

    with gr.Tab("Caption"):
        v = gr.Video(label="Input")
        rows = gr.Dataframe(
            headers=["Start", "End", "Text"],
            datatype=["str", "str", "str"],
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
