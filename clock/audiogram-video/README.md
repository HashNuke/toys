# Clock ticking audiogram video

An animated waveform made from `../clock-ticking.wav`, inspired by the
[frequency-colored sound previews on Freesound](https://freesound.org/).
No Freesound images, recordings, or branding are used.

The complete waveform stays visible and fixed horizontally, with its centerline
exactly halfway down the frame. A moving playhead tracks playback. The waveform
locally swells around the current position, driven by the actual audio level,
then settles with a 140 ms release. A Gaussian falloff blends the magnified area
into the rest of the waveform. Quiet parts of the track remain still.

Its shape follows the WAV's amplitude; green, yellow, and orange colors follow
the local spectral centroid. The background is dark navy. There is no added
music, narration, looping, or change to the source audio's level.

## Render

Install `ffmpeg` and `uv`, then run from the repository root:

```sh
uv run clock/audiogram-video/render.py
```

Python dependencies are pinned in the script's inline metadata. uv uses an
isolated script environment without changing the repository's dependencies.
The script also works from other working directories; default paths are relative
to the script itself.

Outputs, written beside the script:

- `clock-ticking.mp4`: 1920 × 1080, 60 fps, H.264 video with AAC audio, matching
  the WAV's duration (10 seconds for the current source).
- `clock-ticking.png`: a still preview of the generated animation.

The MP4 audio is encoded from the supplied WAV at 320 kbit/s, not resynthesized.
Rerunning the script overwrites these outputs.

For a different frame size, magnification, or output path:

```sh
uv run clock/audiogram-video/render.py --width 1280 --height 720 --fps 30 --zoom 2 --focus-width 0.2 --output clock/audiogram-video/clock-ticking-720p.mp4
```

`--zoom` sets the maximum local height multiplier (1..2.2). `--focus-width` sets
the pulse radius in seconds. `--input` accepts another 16-bit PCM WAV. The entire
track is always visible, and the video ends at the input audio's duration.
