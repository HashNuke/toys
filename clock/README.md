# Clock ticking for ChucK

Run from the repository root:

```sh
chuck clock/clock-ticking.ck
```

Stop with Ctrl-C. No samples or external chugins are needed.

Play the included ten-second, ten-tick synthesized render:

```sh
afplay clock/clock-ticking.wav
```

This version models the Clock Ticking.wav bundled with Session. It synthesizes
fresh noise through 32 resonators and applies measured, interpolated frequency
band envelopes. The program contains synthesis parameters, not recorded audio,
and does not need Session installed. The output is a mono approximation;
it does not reproduce the original recording's exact waveform or stereo space.

Reference measurements:

- Five ticks in a five-second stereo, 44.1 kHz recording: one tick per second.
- A lighter contact precedes the main impact by approximately 10 ms.
- Main impact energy is concentrated around 1.2-1.4 kHz and 2.4-2.8 kHz.
- Lower case resonances around 180-210 Hz and 350-530 Hz outlast the attack.
- Strong transient decay over about 30 ms, with a much quieter tail.

Optional colon-separated arguments:

```text
milliseconds between beats : volume (0..1) : seconds (0 = forever) : WAV path
```

```sh
chuck clock/clock-ticking.ck:1000:0.4
chuck clock/clock-ticking.ck:1000:0.65:10
chuck --silent clock/clock-ticking.ck:1000:0.65:10:/tmp/clock-ticking.wav
```

Minimum interval: 300 ms. Default volume: 0.65. Default duration: infinite.
Finite renders include a 300 ms tail. `clock-ticking.wav` contains ten ticks at
the default settings, trimmed to exactly ten seconds. `--silent` renders without
playing audio. To regenerate the distributed WAV:

```sh
chuck --silent clock/clock-ticking.ck:1000:0.65:10:/tmp/clock-ticking-render.wav
ffmpeg -y -i /tmp/clock-ticking-render.wav -t 10 -c:a pcm_s16le clock/clock-ticking.wav
```

This trims only the extra trailing silence after the ten-second render. Each
render synthesizes new noise, so individual tick waveforms vary slightly.

No source or separate license for Session's reference recording was identified.
The original WAV is not included here.
