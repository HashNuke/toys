# Long-form clock audio and videos

Run from the repository root with uv and FFmpeg installed:

```sh
# Keep an existing one-hour WAV; create it if missing, then build both videos.
uv run clock/long-form/build.py

# Recreate the one-hour WAV, including metadata and embedded square cover art.
uv run clock/long-form/build.py wav

# Recreate both videos using the existing WAV.
uv run clock/long-form/build.py videos --overwrite

# Regenerate landscape video stills only.
uv run clock/long-form/build.py art
```

Use `--hours 1` or `--hours 2` to render just one video. Python dependencies are
pinned in the scripts' inline metadata; the repository's dependency files are
unchanged. Default paths are relative to the scripts, so any working directory
can be used.

The audio source is the committed ten-second `../clock-ticking.wav`. It repeats
continuously at its original volume. Recreating the one-hour WAV preserves the
PCM samples and embeds the title, artist, website, and front cover. `tag_audio.py`
can regenerate the artwork and reapply metadata to an existing one-hour WAV.

Outputs:

- `../clock-ticking-1hr.wav`: exactly one hour, 44.1 kHz, 16-bit mono PCM with
  ID3 metadata and embedded artwork. An existing file is preserved unless the
  `wav` target or `--rebuild-wav` is explicitly used.
- `pomodoro-clock-tick-1hr.mp4`: exactly one hour.
- `pomodoro-clock-tick-2hr.mp4`: exactly two hours.
- Native 3840×2160 PNG video stills for each duration. The WAV's personalized
  square cover is generated in memory and embedded directly; no separate square
  cover files are needed.

Videos use H.264 at 3840×2160 (4K), 24 fps, CRF 12, with AAC audio at 192 kbit/s.
The colorful waveform artwork remains static throughout playback. It is drawn
directly at the final landscape resolution, with antialiased waveform detail and
crisp text on a flat dark background. The video artwork and metadata omit the
artist's name and website; the WAV's tags and square cover remain personalized.
Each video has its own duration label.

The image is encoded once as a ten-second segment and its video packets are
reused. Audio is encoded continuously, so AAC padding is not repeated at each
ten-second boundary. The video metadata contains its track title. The one-hour
WAV retains Akash Manohar John and https://definerun.com/ in its metadata.

Large media files are local outputs. Nothing from this workflow is committed
automatically. The one-hour WAV, long-form MP4s, and temporary render directories
are excluded through the repository's `.gitignore`.
