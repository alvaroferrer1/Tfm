"""
gen_explainer_video.py — Technical explainer video for MermaOps TFM
Output: docs/MermaOps_Explainer.mp4
Resolution: 1920x1080, 24fps, ~2 min
"""
import sys
import os
import math
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(BASE_DIR, "docs", "MermaOps_Explainer.mp4")
AGENTS_IMAGE = os.path.join(BASE_DIR, "Agentes MermaOps.png")
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

W, H = 1920, 1080
FPS  = 24

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
NAVY    = (15, 23, 42)    # #0F172A
WHITE   = (255, 255, 255)
GREEN   = (16, 185, 129)  # #10B981
LGRAY   = (200, 200, 210)
GRAY    = (100, 110, 130)
GOLD    = (234, 179, 8)
BLUE    = (59, 130, 246)
DBLUE   = (30, 58, 138)
BLACK   = (0, 0, 0)
DARK_CARD = (22, 35, 60)

# ---------------------------------------------------------------------------
# PIL helpers
# ---------------------------------------------------------------------------
from PIL import Image, ImageDraw, ImageFont

def get_font(size, bold=False):
    candidates_bold    = ["arialbd.ttf", "C:/Windows/Fonts/arialbd.ttf",
                          "C:/Windows/Fonts/calibrib.ttf"]
    candidates_regular = ["arial.ttf", "C:/Windows/Fonts/arial.ttf",
                          "C:/Windows/Fonts/calibri.ttf"]
    for path in (candidates_bold if bold else candidates_regular):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()

def text_center(d, text, y, font, color=WHITE, w=W, x_offset=0):
    bb = d.textbbox((0, 0), text, font=font)
    tw = bb[2] - bb[0]
    x  = x_offset + (w - tw) // 2
    d.text((x, y), text, font=font, fill=color)

def blend_np(a, b, t):
    return (np.array(a) * (1-t) + np.array(b) * t).astype(np.uint8)

# ---------------------------------------------------------------------------
# moviepy
# ---------------------------------------------------------------------------
from moviepy import VideoClip, ImageClip, concatenate_videoclips, AudioClip
from moviepy.video.fx import FadeIn, FadeOut

# ---------------------------------------------------------------------------
# Ambient audio
# ---------------------------------------------------------------------------
def make_audio(duration, fps=44100):
    t = np.linspace(0, duration, int(fps * duration), endpoint=False)
    # D minor chord
    freqs = [146.83, 174.61, 220.0, 293.66]  # D3 F3 A3 D4
    wave  = sum(0.12 * np.sin(2 * np.pi * f * t) for f in freqs)
    lfo   = 0.5 + 0.5 * np.sin(2 * np.pi * 0.2 * t)
    wave  = wave * lfo
    stereo = np.stack([wave, wave], axis=1).astype(np.float32)
    return stereo

# ---------------------------------------------------------------------------
# Slide 1: Title [0-8s]
# ---------------------------------------------------------------------------
def slide_title(duration=8.0):
    font_t = get_font(60, bold=True)
    font_s = get_font(24)

    def make(t):
        img = Image.new("RGB", (W, H), NAVY)
        d   = ImageDraw.Draw(img)

        a1 = min(t / 1.5, 1.0)
        a2 = min(max(t - 1.5, 0) / 1.0, 1.0)

        def w(a): return (int(255*a),)*3
        def g(a): return (int(16*a), int(185*a), int(129*a))

        text_center(d, "Como funciona MermaOps", H//2 - 60, font_t, color=w(a1))

        # Green separator
        lw = int(500 * min(max(t-0.8,0)/0.8, 1.0))
        lx = (W - 500)//2
        if lw > 0:
            d.rectangle([lx, H//2 + 8, lx+lw, H//2 + 12], fill=g(1.0))

        text_center(d, "Arquitectura multi-agente · 12 agentes especializados · Claude API",
                    H//2 + 30, font_s, color=g(a2))

        return np.array(img)

    return VideoClip(make, duration=duration)

# ---------------------------------------------------------------------------
# Slide 2: Decision Flow [8-20s]
# ---------------------------------------------------------------------------
def slide_decision_flow(duration=12.0):
    font_box  = get_font(24, bold=True)
    font_title= get_font(36, bold=True)

    steps = ["Input", "Chuwi", "Kuine", "Evaluador", "Accion"]

    def make(t):
        img = Image.new("RGB", (W, H), NAVY)
        d   = ImageDraw.Draw(img)

        a_title = min(t / 0.8, 1.0)
        def wt(a): return (int(255*a),)*3

        text_center(d, "El flujo de una decision", H//4 - 20, font_title,
                    color=wt(a_title))

        total_w = 900
        box_w, box_h = 140, 60
        gap = (total_w - len(steps)*box_w) // (len(steps)-1)
        start_x = (W - total_w) // 2
        cy = H // 2

        for i, step in enumerate(steps):
            delay = 0.5 + i * 0.8
            alpha = min(max(t - delay, 0) / 0.6, 1.0)
            if alpha <= 0:
                continue

            bx = start_x + i * (box_w + gap)
            by = cy - box_h // 2

            green_a = (int(16*alpha), int(185*alpha), int(129*alpha))
            text_a   = (int(255*alpha),)*3

            d.rounded_rectangle([bx, by, bx+box_w, by+box_h],
                                 radius=8, outline=green_a, width=2,
                                 fill=DARK_CARD)
            text_center(d, step, by + 18, font_box, color=text_a,
                        w=box_w, x_offset=bx)

            # Arrow
            if i < len(steps) - 1:
                ax_start = bx + box_w + 4
                ax_end   = bx + box_w + gap - 4
                amid = (by + by + box_h) // 2
                arr_a = min(max(t - delay - 0.3, 0) / 0.4, 1.0)
                if arr_a > 0:
                    ca = (int(16*arr_a), int(185*arr_a), int(129*arr_a))
                    d.line([ax_start, amid, ax_end, amid], fill=ca, width=2)
                    # Arrowhead
                    d.polygon([ax_end, amid,
                               ax_end-10, amid-6,
                               ax_end-10, amid+6], fill=ca)

        return np.array(img)

    return VideoClip(make, duration=duration)

# ---------------------------------------------------------------------------
# Slide 3: Model right-sizing [20-35s]
# ---------------------------------------------------------------------------
def slide_model_sizing(duration=15.0):
    font_title = get_font(36, bold=True)
    font_col   = get_font(26, bold=True)
    font_sub   = get_font(20)
    font_cost  = get_font(18)

    cols = [
        ("OPUS 4.7",   GOLD,  "Orquestacion compleja",  "15 USD / M tokens",  0.6),
        ("SONNET 4.6", BLUE,  "Razonamiento avanzado",  "3 USD / M tokens",   1.4),
        ("HAIKU 4.5",  GREEN, "Tareas simples",          "0.25 USD / M tokens",2.2),
    ]

    def make(t):
        img = Image.new("RGB", (W, H), NAVY)
        d   = ImageDraw.Draw(img)

        at = min(t / 0.8, 1.0)
        text_center(d, "Right-sizing de modelos", H//4 - 20, font_title,
                    color=(int(255*at),)*3)

        col_w = 340
        gap   = 60
        total = len(cols)*col_w + (len(cols)-1)*gap
        sx    = (W - total) // 2
        cy    = H // 2 - 60

        for i, (name, color, desc, cost, delay) in enumerate(cols):
            alpha = min(max(t - delay, 0) / 0.8, 1.0)
            if alpha <= 0:
                continue

            bx = sx + i*(col_w + gap)
            bh = 220

            ca  = tuple(int(c*alpha) for c in color)
            wa  = (int(255*alpha),)*3
            ga  = (int(180*alpha),)*3

            d.rounded_rectangle([bx, cy, bx+col_w, cy+bh],
                                 radius=12,
                                 fill=DARK_CARD,
                                 outline=ca, width=2)
            text_center(d, name, cy + 20, font_col, color=ca,
                        w=col_w, x_offset=bx)
            text_center(d, desc, cy + 80, font_sub, color=wa,
                        w=col_w, x_offset=bx)
            text_center(d, cost, cy + 140, font_cost, color=ga,
                        w=col_w, x_offset=bx)

        return np.array(img)

    return VideoClip(make, duration=duration)

# ---------------------------------------------------------------------------
# Slide 4: Agents architecture image [35-55s]
# ---------------------------------------------------------------------------
def slide_agents_image(duration=20.0):
    font_cap = get_font(20)
    font_label = get_font(26, bold=True)

    # Load the agents image
    try:
        agents_img = Image.open(AGENTS_IMAGE).convert("RGB")
        img_w, img_h = agents_img.size
    except Exception as e:
        print(f"  Warning: could not load agents image: {e}")
        agents_img = None
        img_w, img_h = W, H

    def make(t):
        base = Image.new("RGB", (W, H), NAVY)
        d    = ImageDraw.Draw(base)

        a_title = min(t / 0.8, 1.0)
        text_center(d, "Arquitectura de Agentes",
                    30, font_label, color=(int(255*a_title),)*3)

        if agents_img is None:
            text_center(d, "[Agentes MermaOps.png]", H//2, font_cap, color=GRAY)
            return np.array(base)

        # Phases:
        # 0-4s: show full image
        # 4-9s: zoom into top (Kuine)
        # 9-14s: zoom into middle (Evaluador/Consenso)
        # 14-19s: zoom into bottom (Haiku models)
        phase = min(int(t / 5), 3)
        phase_t = (t % 5.0) / 5.0

        display_h = H - 120
        display_w = W - 80
        ax = 40
        ay = 80

        if phase == 0 or t < 1.0:
            # Full image, fit
            ratio = min(display_w / img_w, display_h / img_h)
            nw, nh = int(img_w * ratio), int(img_h * ratio)
            resized = agents_img.resize((nw, nh), Image.LANCZOS)
            ox = ax + (display_w - nw) // 2
            oy = ay + (display_h - nh) // 2
            alpha = min(t / 1.0, 1.0)
            blend = Image.blend(Image.new("RGB", (nw, nh), NAVY),
                                resized, alpha)
            base.paste(blend, (ox, oy))

        else:
            # Zoom crops
            crop_regions = [
                (0,   0,   img_w, img_h // 3),        # top: Kuine
                (0,   img_h//3, img_w, 2*img_h//3),   # mid: Evaluador
                (0,   2*img_h//3, img_w, img_h),       # bot: Haiku
            ]
            zoom_labels = [
                "Kuine — Orquestador (Opus 4.7)",
                "Evaluador + Consenso (Sonnet 4.6)",
                "Predictor + Vision (Haiku 4.5)",
            ]
            cr = crop_regions[min(phase - 1, 2)]
            zoomed = agents_img.crop(cr)
            rw, rh = zoomed.size
            ratio = min(display_w / rw, display_h / rh)
            nw, nh = int(rw * ratio), int(rh * ratio)
            zoomed = zoomed.resize((nw, nh), Image.LANCZOS)
            ox = ax + (display_w - nw) // 2
            oy = ay + (display_h - nh) // 2
            base.paste(zoomed, (ox, oy))

            label = zoom_labels[min(phase - 1, 2)]
            text_center(d, label, ay + nh + 10, font_cap,
                        color=GREEN)

        return np.array(base)

    return VideoClip(make, duration=duration)

# ---------------------------------------------------------------------------
# Slide 5: Extended Thinking score bar [55-75s]
# ---------------------------------------------------------------------------
def slide_extended_thinking(duration=20.0):
    font_title = get_font(36, bold=True)
    font_score = get_font(80, bold=True)
    font_lbl   = get_font(20)
    font_sub   = get_font(24)

    def make(t):
        img = Image.new("RGB", (W, H), NAVY)
        d   = ImageDraw.Draw(img)

        at = min(t / 0.8, 1.0)
        text_center(d, "Extended Thinking", H//5, font_title,
                    color=(int(255*at),)*3)

        # Score bar
        bar_w, bar_h = 900, 40
        bx = (W - bar_w) // 2
        by = H // 2 - 40

        # Background bar
        d.rounded_rectangle([bx, by, bx+bar_w, by+bar_h],
                             radius=bar_h//2, fill=(30, 40, 60))

        # Zones
        zones = [
            (0,   40,  (16, 185, 129)),   # green 0-40
            (40,  65,  (234, 179, 8)),    # yellow 40-65
            (65,  90,  (59, 130, 246)),   # blue 65-90: thinking active
            (90,  100, (239, 68, 68)),    # red 90-100: consensus
        ]
        for z_start, z_end, col in zones:
            zx1 = bx + int(z_start / 100 * bar_w)
            zx2 = bx + int(z_end / 100 * bar_w)
            d.rounded_rectangle([zx1, by, zx2, by+bar_h],
                                 radius=bar_h//2 if z_start == 0 or z_end == 100 else 0,
                                 fill=col)

        # Animated fill overlay (shows actual score)
        target_score = 87
        anim_score = min(int(target_score * max(t - 1.0, 0) / 2.0), target_score)
        fill_w = int(anim_score / 100 * bar_w)
        if fill_w > 0:
            d.rounded_rectangle([bx, by, bx+fill_w, by+bar_h],
                                 radius=bar_h//2, fill=(16, 185, 129))

        # Zone labels
        zone_labels = [("Basico", 20), ("Validacion", 52),
                       ("Thinking activo", 77), ("Consenso", 95)]
        for lbl, pct in zone_labels:
            lx = bx + int(pct/100 * bar_w)
            d.text((lx - 30, by + bar_h + 10), lbl,
                   font=font_lbl, fill=LGRAY)

        # Current score display
        score_display = min(int(anim_score), 87)
        if t > 1.0:
            sa = min((t - 1.0) / 0.5, 1.0)
            text_center(d, str(score_display), H//2 + 80, font_score,
                        color=(int(16*sa), int(185*sa), int(129*sa)))

        text_center(d, "Yogur Danone x4 — Score: 87/100 — Extended thinking activado",
                    H//2 + 200, font_sub, color=GRAY)

        return np.array(img)

    return VideoClip(make, duration=duration)

# ---------------------------------------------------------------------------
# Slide 6: Adversarial validator [75-95s]
# ---------------------------------------------------------------------------
def slide_adversarial(duration=20.0):
    font_title = get_font(36, bold=True)
    font_item  = get_font(22)
    font_big   = get_font(26, bold=True)

    attacks = [
        "Injection por precio negativo",
        "Bypass de autorizacion con rol falso",
        "Manipulacion de fechas de caducidad",
        "Overflow en calculo de descuentos",
        "Suplantacion de origen de datos",
        "Escalado de privilegios via prompt",
        "... + 17 ataques adicionales",
    ]

    def make(t):
        img = Image.new("RGB", (W, H), NAVY)
        d   = ImageDraw.Draw(img)

        at = min(t / 0.8, 1.0)
        text_center(d, "Validador Adversarial", H//5, font_title,
                    color=(int(255*at),)*3)

        sx = W//2 - 380
        sy = H//3

        for i, atk in enumerate(attacks):
            delay = 0.5 + i * 0.5
            alpha = min(max(t - delay, 0) / 0.5, 1.0)
            if alpha <= 0:
                continue

            y = sy + i * 52
            ca = (int(16*alpha), int(185*alpha), int(129*alpha))
            wa = (int(255*alpha),)*3

            # checkmark
            d.ellipse([sx, y+4, sx+28, y+32], fill=ca)
            d.text((sx+6, y+6), "v", font=font_item, fill=WHITE)

            d.text((sx+44, y+6), atk, font=font_item, fill=wa)

        # Result
        res_a = min(max(t - 4.0, 0) / 0.8, 1.0)
        if res_a > 0:
            ra = (int(239*res_a), int(68*res_a), int(68*res_a))
            ga = (int(16*res_a), int(185*res_a), int(129*res_a))
            text_center(d, "23/23 ataques bloqueados — 100%",
                        H - 160, font_big, color=ga)

        return np.array(img)

    return VideoClip(make, duration=duration)

# ---------------------------------------------------------------------------
# Slide 7: Real results [95-110s]
# ---------------------------------------------------------------------------
def slide_results(duration=15.0):
    font_title = get_font(36, bold=True)
    font_val   = get_font(44, bold=True)
    font_lbl   = get_font(18)

    cards = [
        ("774",      "tests automatizados",           WHITE, 0.3),
        ("100%",     "precision en decisiones",        GREEN, 0.8),
        ("483 EUR",  "merma identificada",             GREEN, 1.3),
        ("69 EUR",   "donado a banco de alimentos",    BLUE,  1.8),
        ("0,03 EUR", "coste por brief",                GOLD,  2.3),
        ("0,80 EUR", "coste mensual total",            GREEN, 2.8),
    ]

    def make(t):
        img = Image.new("RGB", (W, H), NAVY)
        d   = ImageDraw.Draw(img)

        at = min(t / 0.8, 1.0)
        text_center(d, "Resultados reales", H//6, font_title,
                    color=(int(255*at),)*3)

        cols = 3
        card_w, card_h = 400, 160
        gap_x, gap_y   = 60, 40
        total_w = cols * card_w + (cols-1) * gap_x
        total_h = 2  * card_h + gap_y
        sx = (W - total_w) // 2
        sy = H//4

        for i, (val, lbl, color, delay) in enumerate(cards):
            alpha = min(max(t - delay, 0) / 0.6, 1.0)
            if alpha <= 0:
                continue

            row, col = divmod(i, cols)
            bx = sx + col * (card_w + gap_x)
            by = sy + row * (card_h + gap_y)

            ca = tuple(int(c*alpha) for c in color)
            wa = (int(255*alpha),)*3
            ga = (int(160*alpha),)*3

            d.rounded_rectangle([bx, by, bx+card_w, by+card_h],
                                 radius=12, fill=DARK_CARD,
                                 outline=ca, width=2)
            text_center(d, val,  by + 30, font_val, color=ca,
                        w=card_w, x_offset=bx)
            text_center(d, lbl,  by + 110, font_lbl, color=ga,
                        w=card_w, x_offset=bx)

        return np.array(img)

    return VideoClip(make, duration=duration)

# ---------------------------------------------------------------------------
# Slide 8: Next steps + close [110-120s]
# ---------------------------------------------------------------------------
def slide_nextsteps(duration=10.0):
    font_title = get_font(36, bold=True)
    font_item  = get_font(26)
    font_close = get_font(48, bold=True)

    items = [
        ("Agente Comprador",  0.5),
        ("Multi-tienda",      1.3),
        ("Fine-tuning",       2.1),
    ]

    def make(t):
        img = Image.new("RGB", (W, H), NAVY)
        d   = ImageDraw.Draw(img)

        fade_out = 1.0
        if t > duration - 2.0:
            fade_out = max(0.0, 1.0 - (t - (duration - 2.0)) / 2.0)

        def w(a): return tuple(int(c*a*fade_out) for c in (255,255,255))
        def g(a): return (int(16*a*fade_out), int(185*a*fade_out), int(129*a*fade_out))

        at = min(t / 0.8, 1.0)
        text_center(d, "Proximos pasos", H//4, font_title, color=w(at))

        for i, (item, delay) in enumerate(items):
            alpha = min(max(t - delay, 0) / 0.6, 1.0)
            if alpha <= 0:
                continue
            y = H//3 + i*70
            text_center(d, f"→  {item}", y, font_item, color=g(alpha))

        a_close = min(max(t - 3.5, 0) / 0.8, 1.0)
        if a_close > 0:
            text_center(d, "MermaOps", H - 160, font_close, color=w(a_close))

        return np.array(img)

    return VideoClip(make, duration=duration)

# ---------------------------------------------------------------------------
# Assemble
# ---------------------------------------------------------------------------
def main():
    print("Building MermaOps Explainer video...")

    clips = [
        slide_title(8.0),
        slide_decision_flow(12.0),
        slide_model_sizing(15.0),
        slide_agents_image(20.0),
        slide_extended_thinking(20.0),
        slide_adversarial(20.0),
        slide_results(15.0),
        slide_nextsteps(10.0),
    ]

    total = sum(c.duration for c in clips)
    print(f"  Total duration: {total:.1f}s")

    video = concatenate_videoclips(clips, method="compose")

    print("  Generating audio...")
    audio_data = make_audio(total)
    def audio_frame(t):
        t_arr = np.atleast_1d(np.asarray(t, dtype=np.float64))
        idx = np.clip((t_arr * 44100).astype(int), 0, len(audio_data) - 1)
        result = audio_data[idx]
        if result.ndim == 2 and result.shape[0] == 1:
            return result[0]
        return result

    audio = AudioClip(audio_frame, duration=total, fps=44100)
    video = video.with_audio(audio)

    print(f"  Writing {OUTPUT_PATH} ...")
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
