"""
gen_demo_video.py — Apple-style product demo video for MermaOps TFM
Output: docs/MermaOps_Demo.mp4
Resolution: 1920x1080, 24fps, ~90s
"""
import sys
import os
import math
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(BASE_DIR, "docs", "MermaOps_Demo.mp4")
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

W, H = 1920, 1080
FPS = 24

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
BLACK   = (0, 0, 0)
WHITE   = (255, 255, 255)
GRAY    = (160, 160, 160)
LGRAY   = (200, 200, 200)
GREEN   = (16, 185, 129)   # #10B981
RED     = (239, 68, 68)
BLUE    = (59, 130, 246)
DGRAY   = (40, 40, 40)
TERMINAL_BG = (18, 18, 18)
TERMINAL_GREEN = (80, 220, 100)

# ---------------------------------------------------------------------------
# PIL helpers
# ---------------------------------------------------------------------------
from PIL import Image, ImageDraw, ImageFont

def get_font(size, bold=False):
    """Try to load a system font; fall back to PIL default."""
    candidates_bold = [
        "arialbd.ttf", "Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]
    candidates_regular = [
        "arial.ttf", "Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    candidates = candidates_bold if bold else candidates_regular
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()

def make_frame(draw_fn, w=W, h=H):
    """Return an RGB numpy array produced by draw_fn(ImageDraw, W, H)."""
    img = Image.new("RGB", (w, h), BLACK)
    d = ImageDraw.Draw(img)
    draw_fn(d, w, h)
    return np.array(img)

def text_center(d, text, y, font, color=WHITE, w=W):
    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (w - tw) // 2
    d.text((x, y), text, font=font, fill=color)

def alpha_blend(frame_a, frame_b, t):
    """Blend two numpy RGB arrays; t=0 -> a, t=1 -> b."""
    return (frame_a * (1 - t) + frame_b * t).astype(np.uint8)

# ---------------------------------------------------------------------------
# moviepy imports
# ---------------------------------------------------------------------------
from moviepy import VideoClip, ImageClip, concatenate_videoclips, AudioClip
from moviepy.video.fx import FadeIn, FadeOut

# ---------------------------------------------------------------------------
# Ambient audio: Am chord sine LFO
# ---------------------------------------------------------------------------
def make_audio(duration, fps=44100):
    """Am chord with slow LFO tremolo."""
    t = np.linspace(0, duration, int(fps * duration), endpoint=False)
    freqs = [220.0, 261.63, 329.63, 440.0]  # A3, C4, E4, A4
    wave = sum(0.15 * np.sin(2 * np.pi * f * t) for f in freqs)
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.25 * t)  # 0.25 Hz LFO
    wave = wave * lfo
    # stereo
    stereo = np.stack([wave, wave], axis=1).astype(np.float32)
    return stereo

# ---------------------------------------------------------------------------
# Slide builders — each returns a MoviePy clip
# ---------------------------------------------------------------------------

def slide_logo(duration=4.0):
    """[0-4s] MermaOps logo reveal."""
    font_logo  = get_font(80, bold=True)
    font_sub   = get_font(28)

    def make(t):
        img = Image.new("RGB", (W, H), BLACK)
        d   = ImageDraw.Draw(img)

        alpha = min(t / 1.5, 1.0)

        # Main title
        fa = int(255 * alpha)
        text_center(d, "MermaOps", H // 2 - 80, font_logo,
                    color=(fa, fa, fa))

        # Green line sliding in from left
        line_w = int(300 * min(t / 1.0, 1.0))
        line_x = (W - 300) // 2
        if line_w > 0:
            d.rectangle([line_x, H // 2 - 10, line_x + line_w, H // 2 - 7],
                        fill=GREEN)

        # Subtitle
        sub_alpha = min(max(t - 1.0, 0) / 1.0, 1.0)
        sa = int(200 * sub_alpha)
        text_center(d, "Sistema Multi-Agente de IA", H // 2 + 20,
                    font_sub, color=(sa, sa, sa))

        return np.array(img)

    return VideoClip(make, duration=duration)


def slide_problem_stat(duration=10.0):
    """[4-12s] 2-5% merma stat."""
    font_big  = get_font(180, bold=True)
    font_med  = get_font(32)
    font_sml  = get_font(28)

    def make(t):
        img = Image.new("RGB", (W, H), BLACK)
        d   = ImageDraw.Draw(img)

        a1 = min(t / 2.0, 1.0)
        a2 = min(max(t - 2.0, 0) / 1.5, 1.0)
        a3 = min(max(t - 3.5, 0) / 1.5, 1.0)

        def c(a): return (int(255*a), int(255*a), int(255*a))
        def g(a): return (int(160*a), int(160*a), int(160*a))

        text_center(d, "2-5%", H // 2 - 120, font_big, color=c(a1))
        text_center(d, "de los ingresos de tu supermercado",
                    H // 2 + 80, font_med, color=g(a2))
        text_center(d, "se pierde en merma alimentaria",
                    H // 2 + 130, font_sml, color=g(a3))

        return np.array(img)

    return VideoClip(make, duration=duration)


def slide_existing_solutions(duration=10.0):
    """[12-22s] Competitors."""
    font_w  = get_font(36)
    font_o  = get_font(32)
    font_r  = get_font(30)

    def make(t):
        img = Image.new("RGB", (W, H), BLACK)
        d   = ImageDraw.Draw(img)

        a1 = min(t / 1.0, 1.0)
        a2 = min(max(t - 1.0, 0) / 1.0, 1.0)
        a3 = min(max(t - 2.5, 0) / 1.0, 1.0)

        def w(a): return (int(255*a), int(255*a), int(255*a))
        def g(a): return (int(180*a), int(180*a), int(180*a))
        def r(a): return (int(239*a), int(68*a), int(68*a))

        y0 = H // 2 - 100
        text_center(d, "Winnow: 20.000 EUR + hardware especializado.",
                    y0, font_w, color=w(a1))
        text_center(d, "Orbisk: 15.000 EUR + instalacion de 3 semanas.",
                    y0 + 70, font_o, color=g(a2))
        text_center(d, "El 95% de supermercados no puede permitirselo.",
                    y0 + 150, font_r, color=r(a3))

        return np.array(img)

    return VideoClip(make, duration=duration)


def slide_mermaops_reveal(duration=10.0):
    """[22-32s] MermaOps solution reveal."""
    font_brand = get_font(90, bold=True)
    font_price = get_font(64, bold=True)
    font_sub   = get_font(26)

    lines = [
        "Sin hardware.",
        "Sin instalacion.",
        "Sin formacion.",
    ]

    def make(t):
        img = Image.new("RGB", (W, H), BLACK)
        d   = ImageDraw.Draw(img)

        a1 = min(t / 1.0, 1.0)
        a2 = min(max(t - 1.0, 0) / 1.0, 1.0)

        def gr(a): return (int(16*a), int(185*a), int(129*a))
        def w(a):  return (int(255*a), int(255*a), int(255*a))
        def gy(a): return (int(160*a), int(160*a), int(160*a))

        text_center(d, "MermaOps", H // 2 - 180, font_brand, color=gr(a1))
        text_center(d, "0,80 EUR/mes.", H // 2 - 60, font_price, color=w(a2))

        for i, line in enumerate(lines):
            ai = min(max(t - 2.0 - i * 0.8, 0) / 0.8, 1.0)
            text_center(d, line, H // 2 + 80 + i * 45, font_sub, color=gy(ai))

        return np.array(img)

    return VideoClip(make, duration=duration)


def slide_telegram_mockup(duration=18.0):
    """[32-50s] Telegram conversation mockup."""
    font_msg  = get_font(22)
    font_user = get_font(22)
    font_tiny = get_font(16)

    BOT_MSG = ("Yogur Danone x4 — REBAJAR HOY\n"
               "Pasillo 2 · Score: 87/100\n"
               "Precio actual 1,60 EUR -> Recomiendo 1,30 EUR\n"
               "(-19% · Margen 50% garantizado)")
    BOT_FULL = "[REBAJAR] " + BOT_MSG
    SPEED = 25  # chars per second
    CAPTION = "Kuine analizo 156 lotes · extended thinking · 6s"

    def make(t):
        img = Image.new("RGB", (W, H), (15, 15, 25))
        d   = ImageDraw.Draw(img)

        # Phone frame
        phone_w, phone_h = 480, 700
        px = (W - phone_w) // 2
        py = (H - phone_h) // 2
        d.rounded_rectangle([px, py, px+phone_w, py+phone_h],
                             radius=30, outline=(80, 80, 90), width=3,
                             fill=(20, 20, 30))

        # Header
        d.rectangle([px, py, px+phone_w, py+60], fill=(30, 30, 42))
        text_center(d, "@ChuwiMermaOpsBot", py + 18, get_font(18),
                    color=WHITE, w=phone_w)

        # User bubble (right)
        user_text = "Que hay critico ahora mismo?"
        a_user = min(t / 0.5, 1.0)
        if a_user > 0:
            ub_w, ub_h = 320, 44
            ub_x = px + phone_w - ub_w - 20
            ub_y = py + 100
            d.rounded_rectangle([ub_x, ub_y, ub_x+ub_w, ub_y+ub_h],
                                 radius=12, fill=(37, 99, 235))
            d.text((ub_x + 12, ub_y + 10), user_text, font=font_user,
                   fill=WHITE)

        # Bot bubble (left) — typewriter
        bot_start = 0.8
        chars_to_show = int(max(t - bot_start, 0) * SPEED)
        display_text = BOT_FULL[:chars_to_show]

        if display_text:
            bb_x = px + 20
            bb_y = py + 180
            bb_w = phone_w - 60
            # measure height
            lines = display_text.split("\n")
            bb_h = max(60, len(lines) * 30 + 20)
            d.rounded_rectangle([bb_x, bb_y, bb_x+bb_w, bb_y+bb_h],
                                 radius=12, fill=(45, 45, 58))
            for i, line in enumerate(lines):
                d.text((bb_x + 12, bb_y + 10 + i * 28),
                       line, font=font_msg, fill=LGRAY)

            # Caption below bubble
            if t > bot_start + len(BOT_FULL) / SPEED:
                d.text((bb_x, bb_y + bb_h + 8), CAPTION,
                       font=font_tiny, fill=(100, 100, 120))

        return np.array(img)

    return VideoClip(make, duration=duration)


def slide_kuine_decision(duration=12.0):
    """[50-62s] Terminal-style Kuine decision."""
    font_mono = get_font(22)
    font_title = get_font(26, bold=True)

    lines = [
        ("BRIEF 04/06/2026 · Super Martinez", WHITE, 0.5),
        ("", WHITE, 1.0),
        ("Yogur Danone x4 (Pasillo 2-E3-N1)", LGRAY, 1.5),
        ("REBAJAR -19% -> 1.30 EUR", TERMINAL_GREEN, 2.2),
        ("", WHITE, 2.8),
        ("Cluster 3 lotes · 12 packs al frente del lineal", GRAY, 3.0),
        ("Margen 50% · Coste 0.65 EUR · FEFO verificado", GRAY, 3.5),
    ]

    def make(t):
        img = Image.new("RGB", (W, H), BLACK)
        d   = ImageDraw.Draw(img)

        # Terminal window
        tw, th = 900, 360
        tx = (W - tw) // 2
        ty = (H - th) // 2
        d.rounded_rectangle([tx, ty, tx+tw, ty+th], radius=10,
                             fill=TERMINAL_BG, outline=(60, 60, 60), width=2)

        # Title bar
        d.rectangle([tx, ty, tx+tw, ty+36], fill=(35, 35, 35))
        d.ellipse([tx+12, ty+10, tx+24, ty+22], fill=(239, 68, 68))
        d.ellipse([tx+30, ty+10, tx+42, ty+22], fill=(234, 179, 8))
        d.ellipse([tx+48, ty+10, tx+60, ty+22], fill=(34, 197, 94))
        text_center(d, "kuine@mermaops", ty+10, get_font(14),
                    color=(150, 150, 150), w=tw)

        # Lines
        for i, (text, color, delay) in enumerate(lines):
            alpha = min(max(t - delay, 0) / 0.6, 1.0)
            if alpha <= 0 or not text:
                continue
            ca = tuple(int(c * alpha) for c in color)
            d.text((tx + 20, ty + 50 + i * 36), text,
                   font=font_mono, fill=ca)

        # Cursor blink
        if t % 1.0 < 0.5:
            last_shown = sum(1 for _, _, delay in lines if t > delay)
            cy = ty + 50 + last_shown * 36
            d.rectangle([tx + 20, cy, tx + 32, cy + 22],
                        fill=TERMINAL_GREEN)

        return np.array(img)

    return VideoClip(make, duration=duration)


def slide_metrics_cascade(duration=13.0):
    """[62-75s] Metrics cascade."""
    font_num  = get_font(120, bold=True)
    font_lbl  = get_font(28)

    metrics = [
        ("774",   WHITE, "tests automatizados",              0.5),
        ("100%",  GREEN, "precision vs 16,7% baseline",      2.0),
        ("23/23", WHITE, "ataques adversariales bloqueados",  3.5),
        ("483 EUR", GREEN, "merma identificada",              5.0),
    ]

    def make(t):
        img = Image.new("RGB", (W, H), BLACK)
        d   = ImageDraw.Draw(img)

        visible = [(v, c, l, s) for v, c, l, s in metrics if t >= s]
        n = len(visible)
        if n == 0:
            return np.array(img)

        # Show only the latest metric large, fade others up
        for idx, (val, col, lbl, start) in enumerate(visible):
            is_last = (idx == n - 1)
            age = t - start
            if is_last:
                alpha = min(age / 0.8, 1.0)
                y_offset = 0
            else:
                # slide up and shrink
                prog = min((t - metrics[idx + 1][3]) / 0.8, 1.0)
                alpha = 1.0 - prog * 0.7
                y_offset = -int(prog * 60)

            ca = tuple(int(c * alpha) for c in col)
            ga = (int(160 * alpha), int(160 * alpha), int(160 * alpha))

            y = H // 2 - 100 + y_offset
            text_center(d, val, y, font_num, color=ca)
            text_center(d, lbl, y + 130, font_lbl, color=ga)

        return np.array(img)

    return VideoClip(make, duration=duration)


def slide_close(duration=15.0):
    """[75-90s] Close slide."""
    font_brand = get_font(60, bold=True)
    font_bot   = get_font(24)

    def make(t):
        img = Image.new("RGB", (W, H), BLACK)
        d   = ImageDraw.Draw(img)

        a1 = min(t / 2.0, 1.0)
        a2 = min(max(t - 1.5, 0) / 1.0, 1.0)
        a3 = min(max(t - 2.5, 0) / 1.0, 1.0)

        # Fade out at end
        fade_out = 1.0
        if t > duration - 2.0:
            fade_out = max(0, 1.0 - (t - (duration - 2.0)) / 2.0)

        def w(a): return (int(255*a*fade_out),)*3
        def g(a): return (int(160*a*fade_out),)*3
        def gr(a): return (int(16*a*fade_out), int(185*a*fade_out), int(129*a*fade_out))

        text_center(d, "MermaOps", H // 2 - 60, font_brand, color=w(a1))

        line_w = int(200 * a2)
        line_x = (W - 200) // 2
        if line_w > 0:
            d.rectangle([line_x, H // 2 + 10, line_x + line_w, H // 2 + 14],
                        fill=gr(a2))

        text_center(d, "@ChuwiMermaOpsBot", H // 2 + 40, font_bot, color=g(a3))

        return np.array(img)

    return VideoClip(make, duration=duration)


# ---------------------------------------------------------------------------
# Assemble
# ---------------------------------------------------------------------------
def main():
    print("Building MermaOps Demo video...")

    clips = [
        slide_logo(4.0),
        slide_problem_stat(10.0),
        slide_existing_solutions(10.0),
        slide_mermaops_reveal(10.0),
        slide_telegram_mockup(18.0),
        slide_kuine_decision(12.0),
        slide_metrics_cascade(13.0),
        slide_close(15.0),
    ]

    total_duration = sum(c.duration for c in clips)
    print(f"  Total duration: {total_duration:.1f}s")

    video = concatenate_videoclips(clips, method="compose")

    # Build audio
    print("  Generating ambient audio...")
    audio_data = make_audio(total_duration)
    def audio_frame(t):
        t_arr = np.atleast_1d(np.asarray(t, dtype=np.float64))
        idx = np.clip((t_arr * 44100).astype(int), 0, len(audio_data) - 1)
        result = audio_data[idx]
        if result.ndim == 2 and result.shape[0] == 1:
            return result[0]
        return result

    audio_clip = AudioClip(audio_frame, duration=total_duration, fps=44100)
    video = video.with_audio(audio_clip)

    print(f"  Writing to {OUTPUT_PATH} ...")
    video.write_videofile(
        OUTPUT_PATH,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        logger="bar",
        threads=4,
    )
    print(f"Done: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
