# Clock ticking

A ChucK program that synthesizes a mechanical clock ticking once per second.

<audio controls src="clock-ticking.wav"></audio>

[Play or download the WAV](clock-ticking.wav).

To render a 10-second WAV, install ChucK and FFmpeg, then run from the repository root:

```sh
chuck --silent clock/clock-ticking.ck:1000:0.65:10:/tmp/clock-ticking-render.wav
ffmpeg -y -i /tmp/clock-ticking-render.wav -t 10 -c:a pcm_s16le clock/clock-ticking.wav
```
