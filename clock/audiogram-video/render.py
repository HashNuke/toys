# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.5.4", "pillow==13.0.0"]
# ///
"""Render a full waveform with an audio-reactive local magnification pulse."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import shutil
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
BACKGROUND = (17, 17, 29)


def read_audio(path: Path) -> tuple[int, np.ndarray]:
    with wave.open(str(path), "rb") as source:
        if source.getsampwidth() != 2:
            raise ValueError("Input must be a 16-bit PCM WAV.")
        rate = source.getframerate()
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
        samples = samples.astype(np.float64).reshape(-1, source.getnchannels())
    if not len(samples):
        raise ValueError("Input WAV is empty.")
    return rate, samples.mean(axis=1) / 32768.0


def waveform_geometry(samples, rate, width, height):
    """Analyze the complete track once; horizontal positions remain fixed."""
    scale = 2
    columns = width * scale
    extents = np.zeros(columns)
    colors = np.zeros((columns, 3), dtype=np.uint8)
    peak = max(float(np.max(np.abs(samples))), 1e-9)
    frequencies = np.fft.rfftfreq(1024, 1 / rate)
    window = np.hanning(1024)
    # Spectral centroid controls the hue, as in frequency-colored waveforms.
    stops = np.array([0, 1000, 1900, 2900, 4200, 8000])
    palette = np.array([
        [92, 191, 62], [0, 212, 85], [79, 218, 78],
        [209, 222, 72], [255, 199, 69], [255, 134, 63],
    ])
    for column in range(columns):
        lo = int(column / columns * len(samples))
        hi = min(len(samples), max(lo + 1, int((column + 1) / columns * len(samples))))
        if lo >= len(samples):
            continue
        amplitude = float(np.max(np.abs(samples[lo:hi])))
        # Gentle display compression makes the mechanical decay legible.
        extent = (amplitude / peak) ** 0.72 * height * scale * 0.22
        midpoint = (lo + hi) // 2
        snippet = np.zeros(1024)
        left, right = max(0, midpoint - 512), min(len(samples), midpoint + 512)
        destination = left - (midpoint - 512)
        snippet[destination:destination + right - left] = samples[left:right]
        spectrum = np.abs(np.fft.rfft(snippet * window)) ** 2
        centroid = float(np.dot(frequencies, spectrum) / max(spectrum.sum(), 1e-15))
        extents[column] = max(0.8, extent)
        colors[column] = [int(np.interp(centroid, stops, palette[:, channel])) for channel in range(3)]
    return extents, colors


def activity_envelope(samples, rate):
    """Fast attack and a 140 ms release let very brief clicks visibly settle."""
    hop = max(1, round(rate * 0.001))
    release = math.exp(-hop / rate / 0.14)
    values = []
    current = 0.0
    for start in range(0, len(samples), hop):
        current = max(float(np.max(np.abs(samples[start:start + hop]))), current * release)
        values.append(current)
    values = np.asarray(values)
    values /= max(float(values.max()), 1e-9)
    return np.arange(len(values)) * hop / rate, values ** 0.65


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=HERE.parent / "clock-ticking.wav")
    parser.add_argument("--output", type=Path, default=HERE / "clock-ticking.mp4")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--zoom", type=float, default=2.1, help="Maximum local vertical magnification (1..2.2)")
    parser.add_argument("--focus-width", type=float, default=0.2, help="Radius of the local pulse in seconds")
    args = parser.parse_args()
    if args.width < 320 or args.height < 240 or args.width % 2 or args.height % 2:
        parser.error("Use even dimensions, at least 320 x 240.")
    if args.fps <= 0 or args.focus_width <= 0 or not 1 <= args.zoom <= 2.2:
        parser.error("Frame rate and focus width must be positive; zoom must be 1..2.2.")
    if not shutil.which("ffmpeg"):
        parser.error("ffmpeg must be installed and available on PATH.")
    source = args.input.resolve()
    output = args.output.resolve()
    if output == source:
        parser.error("Output must differ from the input WAV.")
    output.parent.mkdir(parents=True, exist_ok=True)
    rate, samples = read_audio(source)
    duration = len(samples) / rate
    frames = math.ceil(duration * args.fps)
    margin = round(args.width / 15)
    plot_width = args.width - margin * 2
    plot_height = 2 * round(args.height * 0.23)
    # The waveform's horizontal axis is exactly the video's vertical midpoint.
    plot_top = args.height // 2 - plot_height // 2
    extents, colors = waveform_geometry(samples, rate, plot_width, plot_height)
    activity_times, activity = activity_envelope(samples, rate)
    column_times = np.linspace(0, duration, len(extents), endpoint=False)
    color_tuples = [tuple(map(int, color)) for color in colors]

    def frame_at(t):
        frame = Image.new("RGB", (args.width, args.height), BACKGROUND)
        # The full track stays visible; only height changes near current time.
        # A Gaussian focus keeps the transition into untouched regions smooth.
        focus = np.exp(-0.5 * ((column_times - t) / args.focus_width) ** 2)
        pulse = float(np.interp(t, activity_times, activity))
        magnified = extents * (1 + (args.zoom - 1) * pulse * focus)
        strip = Image.new("RGB", (plot_width * 2, plot_height * 2), BACKGROUND)
        draw_strip = ImageDraw.Draw(strip)
        center = plot_height
        for column, extent in enumerate(magnified):
            draw_strip.line((column, center - extent, column, center + extent), fill=color_tuples[column])
        strip = strip.resize((plot_width, plot_height), Image.Resampling.LANCZOS)
        frame.paste(strip, (margin, plot_top))
        draw = ImageDraw.Draw(frame)
        cy = args.height // 2
        draw.line((margin, cy, args.width - margin, cy), fill=(48, 55, 49), width=1)
        # The playhead moves across the stationary waveform.
        playhead = margin + min(plot_width - 1, round(t / duration * plot_width))
        radius = round(plot_height * 0.48)
        draw.line((playhead - 1, cy - radius, playhead - 1, cy + radius), fill=(72, 73, 88), width=3)
        draw.line((playhead, cy - radius, playhead, cy + radius), fill=(231, 233, 237), width=1)
        return frame

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{args.width}x{args.height}", "-framerate", str(args.fps),
        "-i", "pipe:0", "-i", str(source),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264",
        "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "320k", "-t", f"{duration:.9f}",
        "-movflags", "+faststart", str(output),
    ]
    print(f"Rendering {frames} frames, {duration:.3f}s, {args.width}x{args.height} at {args.fps}fps", flush=True)
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for number in range(frames):
            frame = frame_at(number / args.fps)
            process.stdin.write(frame.tobytes())
        process.stdin.close()
        if process.wait():
            raise RuntimeError("ffmpeg failed to encode the video.")
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.wait()
        raise
    preview_time = min(1.045, duration / 2)
    frame_at(preview_time).save(output.with_suffix(".png"))
    print(f"Video: {output}\nPreview: {output.with_suffix('.png')}", flush=True)


if __name__ == "__main__":
    main()
