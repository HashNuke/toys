Clock ticking for ChucK

Run from the repository root:

  chuck clock/clock-ticking.ck

Stop with Ctrl-C. No samples or external chugins are needed.

Play the included five-tick synthesized render:

  afplay clock/clock-ticking.wav

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
  milliseconds between beats : volume (0..1) : seconds (0 = forever) : WAV path

  chuck clock/clock-ticking.ck:1000:0.4
  chuck clock/clock-ticking.ck:1000:0.65:10
  chuck --silent clock/clock-ticking.ck:1000:0.65:10:/tmp/clock-ticking.wav

Minimum interval: 300 ms. Default volume: 0.65. Default duration: infinite.
Finite renders include a 300 ms tail. clock-ticking.wav is a five-tick synthesized
example at the default settings. --silent renders without playing audio.

No source or separate license for Session's reference recording was identified.
The original WAV is not included here.
