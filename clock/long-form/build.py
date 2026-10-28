# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.5.4", "pillow==13.0.0", "mutagen==1.48.1"]
# ///
"""Recreate the tagged 1HR WAV and cover-art 1HR/2HR MP4s."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from tag_audio import AUDIO, REFERENCE, tag_wav

HERE = Path(__file__).resolve().parent
VIDEO_WIDTH, VIDEO_HEIGHT = 3840, 2160


def run(command):
    subprocess.run(command, check=True)


def probe(path):
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
    ]))


def make_wav(force=False):
    if AUDIO.exists() and not force:
        with wave.open(str(AUDIO)) as source:
            if source.getnframes() != 3600 * source.getframerate():
                raise ValueError("Existing WAV is not one hour; use --rebuild-wav to replace it.")
        print(f"Keeping existing 1HR WAV: {AUDIO}", flush=True)
        return
    with tempfile.TemporaryDirectory(prefix="clock-audio-", dir=HERE) as temporary:
        destination = Path(temporary) / "one-hour.wav"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-stream_loop", "-1", "-i", str(REFERENCE), "-map", "0:a:0",
            "-t", "3600", "-c:a", "pcm_s16le", str(destination)
        ])
        tag_wav(destination)
        destination.replace(AUDIO)
    print(f"Created tagged 1HR WAV: {AUDIO}", flush=True)


def make_art(hours):
    # Draw for the final landscape resolution rather than stretching a cover.
    image = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), (12, 15, 26))
    draw = ImageDraw.Draw(image)
    regular = "/System/Library/Fonts/Supplemental/Arial.ttf"
    bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    draw.text((240, 220), "POMODORO", font=ImageFont.truetype(regular, 66), fill=(139, 161, 181))
    draw.text((224, 338), "Clock Tick", font=ImageFont.truetype(bold, 264), fill=(242, 246, 252))
    duration_font = ImageFont.truetype(bold, 172)
    draw.text((3600, 406), f"{hours}HR", font=duration_font, fill=(223, 232, 243), anchor="ra")

    # Actual waveform at 2x resolution for fine, antialiased signal detail.
    with wave.open(str(REFERENCE)) as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
        samples = samples.reshape(-1, source.getnchannels()).mean(axis=1) / 32768.0
    left, width, center, amplitude = 240, 3360, 1230, 440
    scale = 2
    strip_height = 1000
    strip = Image.new("RGB", (width * scale, strip_height * scale), (12, 15, 26))
    waveform = ImageDraw.Draw(strip)
    palette = np.array([
        [21, 221, 235], [48, 234, 160], [166, 243, 76],
        [255, 213, 72], [255, 126, 107], [227, 94, 246],
    ])
    stops = np.linspace(0, 1, len(palette))
    columns = width * scale
    peak = max(float(np.max(np.abs(samples))), 1e-9)
    for column in range(columns):
        lo = int(column / columns * len(samples))
        hi = max(lo + 1, int((column + 1) / columns * len(samples)))
        value = float(np.max(np.abs(samples[lo:hi])))
        extent = max(1.0, (value / peak) ** 0.48 * amplitude) * scale
        color = tuple(int(np.interp(column / columns, stops, palette[:, i])) for i in range(3))
        mid = strip_height * scale / 2
        waveform.line((column, mid - extent, column, mid + extent), fill=color)
    strip = strip.resize((width, strip_height), Image.Resampling.LANCZOS)
    image.paste(strip, (left, center - strip_height // 2))
    path = HERE / f"pomodoro-clock-tick-{hours}hr-3840x2160.png"
    image.save(path)
    (HERE / f"pomodoro-clock-tick-{hours}hr-1920x1080.png").unlink(missing_ok=True)
    return path


def make_video(hours, artwork, overwrite=False):
    destination = HERE / f"pomodoro-clock-tick-{hours}hr.mp4"
    seconds = hours * 3600
    if destination.exists() and not overwrite:
        print(f"Keeping existing video: {destination} (use --overwrite to rebuild)", flush=True)
        return
    print(f"Rendering {hours}HR MP4 with static cover art...", flush=True)
    with tempfile.TemporaryDirectory(prefix=f"clock-{hours}hr-", dir=HERE) as temporary:
        segment = Path(temporary) / "cover-segment.mp4"
        # Encode the still only once, then copy its H.264 packets into the long
        # video. Continuous audio encoding avoids AAC gaps at repeat boundaries.
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-framerate", "24", "-i", str(artwork),
            "-t", "10", "-an", "-c:v", "libx264", "-tune", "stillimage",
            "-preset", "medium", "-crf", "12", "-pix_fmt", "yuv420p",
            "-bf", "0", "-g", "240", "-keyint_min", "240", "-sc_threshold", "0", str(segment)
        ])
        output = Path(temporary) / "finished.mp4"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-stream_loop", "-1", "-i", str(segment),
            "-stream_loop", "-1", "-i", str(AUDIO),
            "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "-1",
            "-t", str(seconds), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-metadata", f"title=Pomodoro Clock Tick {hours}HR",
            "-movflags", "+faststart+use_metadata_tags", "-progress", "pipe:1", str(output)
        ]
        started = time.monotonic()
        process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
        last_report = started
        for line in process.stdout:
            if line.startswith("out_time_us=") and time.monotonic() - last_report > 20:
                value = line.strip().split("=", 1)[1]
                if value != "N/A":
                    progress = min(100, int(value) / 1e6 / seconds * 100)
                    print(f"  {hours}HR: {progress:.0f}%", flush=True)
                    last_report = time.monotonic()
        if process.wait():
            raise RuntimeError(f"ffmpeg failed for {hours}HR video")
        info = probe(output)
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
        assert (video["width"], video["height"], video["codec_name"]) == (VIDEO_WIDTH, VIDEO_HEIGHT, "h264")
        assert audio["codec_name"] == "aac"
        assert int(video["nb_frames"]) == seconds * 24
        assert abs(float(video["duration"]) - seconds) < 0.05
        assert abs(float(info["format"]["duration"]) - seconds) < 0.05
        assert abs(float(audio["duration"]) - seconds) < 0.05
        assert info["format"]["tags"]["title"] == f"Pomodoro Clock Tick {hours}HR"
        assert "artist" not in info["format"]["tags"]
        assert "website" not in info["format"]["tags"]
        output.replace(destination)
    print(f"Verified {destination.name}: {seconds}s, {VIDEO_WIDTH}x{VIDEO_HEIGHT}, H.264/AAC", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=["all", "wav", "videos", "art"], default="all")
    parser.add_argument("--hours", nargs="+", type=int, choices=[1, 2], default=[1, 2])
    parser.add_argument("--rebuild-wav", action="store_true", help="Replace an existing 1HR WAV")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing MP4s")
    args = parser.parse_args()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        parser.error("Install FFmpeg (including ffprobe) first.")
    if args.target in ["all", "wav", "videos"]:
        make_wav(force=args.rebuild_wav or args.target == "wav")
    if args.target in ["all", "videos", "art"]:
        for hours in args.hours:
            artwork = make_art(hours)
            if args.target != "art":
                make_video(hours, artwork, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
