# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.5.4", "pillow==13.0.0", "mutagen==1.48.1"]
# ///
"""Create waveform cover art and tag the local one-hour WAV without reencoding."""

from pathlib import Path
import hashlib
import io
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from mutagen.wave import WAVE
from mutagen.id3 import APIC, COMM, TALB, TCON, TIT2, TLEN, TPE1, TPE2, WOAR, WXXX

HERE = Path(__file__).resolve().parent
AUDIO = HERE.parent / "clock-ticking-1hr.wav"
REFERENCE = HERE.parent / "clock-ticking.wav"
TITLE = "Pomodoro Clock Tick 1HR"
ARTIST = "Akash Manohar John"
WEBSITE = "https://definerun.com/"


def pcm_digest(path):
    digest = hashlib.sha256()
    with wave.open(str(path)) as stream:
        frames = stream.getnframes()
        rate = stream.getframerate()
        while chunk := stream.readframes(65536):
            digest.update(chunk)
    return digest.digest(), frames, rate


def cover_art(hours=1):
    size = 1600
    yy, xx = np.mgrid[:size, :size]
    base = np.empty((size, size, 3), dtype=np.float32)
    base[:] = (12, 14, 25)
    for cx, cy, sigma, color in [
        (250, 840, 460, (0, 21, 37)),
        (1320, 840, 400, (28, 4, 38)),
    ]:
        glow = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))
        base += glow[:, :, None] * np.array(color)
    image = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(image)
    regular = "/System/Library/Fonts/Supplemental/Arial.ttf"
    bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    title_font = ImageFont.truetype(bold, 151)
    subtitle_font = ImageFont.truetype(regular, 32)
    artist_font = ImageFont.truetype(regular, 43)
    small_font = ImageFont.truetype(regular, 31)
    draw.text((116, 100), f"POMODORO / {hours}HR", font=subtitle_font, fill=(139, 161, 180))
    draw.text((106, 190), "Pomodoro", font=title_font, fill=(241, 245, 251))
    draw.text((106, 352), "Clock Tick", font=title_font, fill=(241, 245, 251))

    # Actual ten-tick source waveform, mirrored and colored across time.
    with wave.open(str(REFERENCE)) as stream:
        pcm = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2")
        samples = pcm.reshape(-1, stream.getnchannels()).mean(axis=1) / 32768.0
    scale = 2
    layer = Image.new("RGBA", (size * scale, size * scale))
    waveform = ImageDraw.Draw(layer)
    left, width, center, amplitude = 115, 1370, 868, 253
    palette = np.array([
        [21, 221, 235], [48, 234, 160], [166, 243, 76],
        [255, 213, 72], [255, 126, 107], [227, 94, 246],
    ])
    stops = np.linspace(0, 1, len(palette))
    count = width * scale
    peak = max(float(np.max(np.abs(samples))), 1e-9)
    for column in range(count):
        lo = int(column / count * len(samples))
        hi = max(lo + 1, int((column + 1) / count * len(samples)))
        value = float(np.max(np.abs(samples[lo:hi])))
        extent = max(0.7, (value / peak) ** 0.48 * amplitude) * scale
        color = tuple(int(np.interp(column / count, stops, palette[:, i])) for i in range(3))
        x, y = left * scale + column, center * scale
        waveform.line((x, y - extent, x, y + extent), fill=(*color, 255))
    layer = layer.resize((size, size), Image.Resampling.LANCZOS)
    glow = layer.filter(ImageFilter.GaussianBlur(12))
    glow.putalpha(glow.getchannel("A").point(lambda a: round(a * 0.75)))
    image = Image.alpha_composite(image.convert("RGBA"), glow)
    image = Image.alpha_composite(image, layer).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.line((116, 1260, 1484, 1260), fill=(54, 65, 82), width=1)
    draw.text((116, 1310), ARTIST, font=artist_font, fill=(234, 240, 249))
    draw.text((116, 1380), WEBSITE, font=small_font, fill=(144, 166, 189))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95, subsampling=0)
    return buffer.getvalue()


def tag_wav(path=AUDIO):
    before = pcm_digest(path)
    artwork = cover_art(1)
    audio = WAVE(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    tags.add(TIT2(encoding=3, text=TITLE))
    tags.add(TPE1(encoding=3, text=ARTIST))
    tags.add(TPE2(encoding=3, text=ARTIST))
    tags.add(TALB(encoding=3, text=TITLE))
    tags.add(TCON(encoding=3, text="Sound Effects"))
    tags.add(TLEN(encoding=3, text="3600000"))
    tags.add(WOAR(url=WEBSITE))
    tags.add(WXXX(encoding=3, desc="Artist website", url=WEBSITE))
    tags.add(COMM(encoding=3, lang="eng", desc="Description",
                  text="One-hour loop of a ten-second mechanical clock synthesis created in ChucK."))
    tags.setall("APIC", [APIC(encoding=3, mime="image/jpeg", type=3,
                             desc="Colorful clock waveform cover", data=artwork)])
    audio.save(v2_version=3)
    after = pcm_digest(path)
    assert before == after, "PCM audio changed unexpectedly"
    check = WAVE(path)
    assert str(check.tags["TIT2"]) == TITLE
    assert str(check.tags["TPE1"]) == ARTIST
    assert check.tags.getall("WOAR")[0].url == WEBSITE
    assert check.tags.getall("APIC")[0].data == artwork
    assert check.info.length == 3600
    print(f"Tagged: {path}\nTitle: {TITLE}\nArtist: {ARTIST}\nWebsite: {WEBSITE}")
    print("Verified embedded front cover; PCM samples unchanged; duration exactly one hour.")


if __name__ == "__main__":
    tag_wav()
