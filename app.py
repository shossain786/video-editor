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

__version__ = "0.1.0"

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


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def op_caption(video, text, position, fontsize):
    _need(video)
    if not text.strip():
        raise gr.Error("Enter caption text.")
    out = _out(".mp4")
    pos = {
        "Bottom": "x=(w-text_w)/2:y=h-text_h-40",
        "Top": "x=(w-text_w)/2:y=40",
        "Center": "x=(w-text_w)/2:y=(h-text_h)/2",
    }[position]
    # escape characters that are special inside the filtergraph
    safe = text.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\\'")
    draw = (
        f"drawtext=text='{safe}':fontcolor=white:fontsize={int(fontsize)}:"
        f"box=1:boxcolor=black@0.5:boxborderw=12:{pos}"
    )
    _run(["ffmpeg", "-y", "-i", video, "-vf", draw,
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
    if method == "arnndn (AI, best for voice)" and os.path.exists(MODEL):
        af = f"arnndn=m={MODEL}"
    else:
        af = "afftdn=nf=-25"  # FFT denoise fallback
    _run(["ffmpeg", "-y", "-i", video, "-af", af,
          "-c:v", "copy", out])
    return out


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="Video Editor") as demo:
    gr.Markdown("# 🎬 Personal Video Editor\nLocal FFmpeg tool — pick a tab, upload, run.")

    with gr.Tab("Caption"):
        v = gr.Video(label="Input")
        txt = gr.Textbox(label="Caption text")
        with gr.Row():
            pos = gr.Radio(["Bottom", "Top", "Center"], value="Bottom", label="Position")
            fs = gr.Slider(12, 96, value=36, step=1, label="Font size")
        out = gr.Video(label="Result")
        gr.Button("Add caption", variant="primary").click(
            op_caption, [v, txt, pos, fs], out)

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
