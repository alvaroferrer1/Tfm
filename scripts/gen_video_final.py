"""
gen_video_final.py — Apple iPhone launch quality video for MermaOps.

Output: docs/MermaOps_Launch.mp4  (1920x1080, 24fps, ~100s)

Design principles:
  - Pure black (#000000) background always
  - Single element per moment — never cluttered
  - Text floats up 20px on reveal (ease out)
  - Numbers count up with cubic easing
  - Cinematic piano + pad ambient music
  - No stuck frames — every function handles full time range

Uso: python scripts/gen_video_final.py
"""
from __future__ import annotations
import sys, os, math, wave, struct
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).parent.parent
IMG_AGENTS = ROOT / "Agentes MermaOps.png"
OUT = ROOT / "docs" / "MermaOps_Launch.mp4"

W, H = 1920, 1080
FPS  = 24
SR   = 44100   # audio sample rate

# ── Palette ───────────────────────────────────────────────────────────────
BLACK  = (0, 0, 0)
WHITE  = (255, 255, 255)
GREEN  = (16, 185, 129)   # #10B981
GREEN2 = (52, 211, 153)   # lighter
GRAY1  = (229, 231, 235)  # light gray
GRAY2  = (156, 163, 175)  # medium gray
GRAY3  = (75,  85,  99)   # dark gray
RED    = (239, 68,  68)
ORANGE = (249, 115, 22)
GOLD   = (234, 179, 8)
BLUE   = (96,  165, 250)


# ── Easing ────────────────────────────────────────────────────────────────
def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3

def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def ease_out_back(t: float, s: float = 1.5) -> float:
    t = max(0.0, min(1.0, t))
    c1 = s; c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

def lerp(a, b, t): return a + (b - a) * max(0.0, min(1.0, t))


# ── Font helpers ─────────────────────────────────────────────────────────
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = []
    if bold:
        candidates = ["arialbd.ttf","Arial Bold.ttf","DejaVuSans-Bold.ttf",
                      "LiberationSans-Bold.ttf","Helvetica-Bold.ttf"]
    else:
        candidates = ["arial.ttf","Arial.ttf","DejaVuSans.ttf",
                      "LiberationSans-Regular.ttf","Helvetica.ttf"]
    for name in candidates:
        try: return ImageFont.truetype(name, size)
        except: pass
    return ImageFont.load_default()

def text_w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]

def text_h(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[3] - bb[1]

def draw_center(draw: ImageDraw.ImageDraw, text: str, y: int,
                size: int, color=WHITE, bold: bool = False, alpha: float = 1.0):
    if alpha <= 0: return
    f = _font(size, bold)
    tw = text_w(draw, text, f)
    x = (W - tw) // 2
    if alpha < 1.0:
        c = tuple(int(c * alpha) for c in color)
    else:
        c = color
    draw.text((x, y), text, fill=c, font=f)

def draw_left(draw: ImageDraw.ImageDraw, text: str, x: int, y: int,
              size: int, color=WHITE, bold: bool = False, alpha: float = 1.0):
    if alpha <= 0: return
    f = _font(size, bold)
    c = tuple(int(ci * alpha) for ci in color) if alpha < 1.0 else color
    draw.text((x, y), text, fill=c, font=f)


# ── Float-in helper: text appears fading + floating up ───────────────────
def float_reveal(draw, text, y_base, size, color, bold, reveal_t):
    """reveal_t in [0,1]: text fades in and floats up 24px."""
    a = ease_out_cubic(reveal_t)
    y = y_base + int(24 * (1 - a))
    draw_center(draw, text, y, size, color, bold, alpha=a)


# ── Line reveal: thin horizontal line slides in from left ────────────────
def draw_line_reveal(draw, y, reveal_t, color=GREEN, thickness=2, margin=200):
    a = ease_out_cubic(reveal_t)
    w = int((W - margin * 2) * a)
    if w > 0:
        x0 = (W - (W - margin * 2)) // 2
        draw.rectangle([x0, y, x0 + w, y + thickness], fill=color)


# ── Pill badge ────────────────────────────────────────────────────────────
def draw_pill(draw, cx, y, text, size=18, bg=GREEN, fg=BLACK, alpha=1.0):
    f = _font(size, True)
    tw = text_w(draw, text, f)
    pw, ph = tw + 32, size + 18
    x = cx - pw // 2
    bg_a = tuple(int(c * alpha) for c in bg)
    draw.rounded_rectangle([x, y, x + pw, y + ph], radius=ph // 2, fill=bg_a)
    draw.text((x + 16, y + 9), text, fill=tuple(int(c * alpha) for c in fg), font=f)


# ── Base frame: pure black ────────────────────────────────────────────────
def base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BLACK)
    return img, ImageDraw.Draw(img)


# ── Transition: fade from/to black ────────────────────────────────────────
def apply_fade(img: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 1.0: return img
    black = Image.new("RGB", (W, H), BLACK)
    return Image.blend(black, img, max(0.0, min(1.0, alpha)))


# ── Counter animation ────────────────────────────────────────────────────
def animated_number(val: float, t: float, decimals: int = 0) -> str:
    cur = val * ease_out_cubic(t)
    if decimals == 0:
        return str(int(cur))
    return f"{cur:.{decimals}f}"


# ═══════════════════════════════════════════════════════════════════════
# SLIDE FUNCTIONS — each returns PIL Image given local time t in [0, dur]
# ═══════════════════════════════════════════════════════════════════════

def s01_logo(t: float, dur: float) -> Image.Image:
    """Pure black. MermaOps name reveals. Green line slides. Tagline."""
    img, draw = base()
    fade_in = min(1.0, t / 0.6)

    # Logo text — gentle float reveal
    float_reveal(draw, "MermaOps", H // 2 - 70, 96, WHITE, True, min(1.0, t / 0.7))

    # Green line slides after 0.8s
    if t > 0.8:
        draw_line_reveal(draw, H // 2 + 50, (t - 0.8) / 0.6)

    # Tagline after 1.4s
    if t > 1.4:
        float_reveal(draw, "Sistema Multi-Agente de IA para Reducción de Merma", H // 2 + 80,
                     26, GRAY2, False, (t - 1.4) / 0.7)

    # Subtitle after 2.0s
    if t > 2.2:
        float_reveal(draw, "Maximo rendimiento. Minimo coste.", H // 2 + 126,
                     22, GRAY3, False, (t - 2.2) / 0.7)

    return apply_fade(img, fade_in)


def s02_problem(t: float, dur: float) -> Image.Image:
    """The problem. Big stat, dramatic."""
    img, draw = base()
    fade_in = min(1.0, t / 0.5)

    if t > 0.2:
        float_reveal(draw, "El problema.", H // 2 - 200, 28, GRAY3, False,
                     min(1.0, (t - 0.2) / 0.5))

    if t > 0.8:
        pct = animated_number(5, (t - 0.8) / 1.5, 0)
        float_reveal(draw, f"2–5%", H // 2 - 130, 160, WHITE, True,
                     min(1.0, (t - 0.8) / 0.9))

    if t > 2.2:
        float_reveal(draw, "de los ingresos de un supermercado", H // 2 + 70,
                     30, GRAY1, False, min(1.0, (t - 2.2) / 0.6))

    if t > 3.0:
        float_reveal(draw, "se pierde en merma alimentaria cada ano.", H // 2 + 114,
                     30, GRAY2, False, min(1.0, (t - 3.0) / 0.6))

    if t > 3.8:
        float_reveal(draw, "15.000–40.000€ al ano por tienda mediana.",
                     H // 2 + 180, 22, RED, False, min(1.0, (t - 3.8) / 0.6))

    return apply_fade(img, fade_in)


def s03_competitors(t: float, dur: float) -> Image.Image:
    """Existing solutions cost too much."""
    img, draw = base()
    fade_in = min(1.0, t / 0.5)

    if t > 0.2:
        float_reveal(draw, "Las soluciones existentes...", H // 2 - 260,
                     32, GRAY3, False, min(1.0, (t - 0.2) / 0.5))

    items = [
        ("Winnow V2",   ">20.000€ + hardware especializado + instalacion",   0.8),
        ("Orbisk",      ">15.000€ + camara IA + servidor dedicado",           1.6),
        ("Excel manual","120€/mes en tiempo del encargado · sin datos reales", 2.4),
    ]
    for name, desc, start in items:
        if t > start:
            a = min(1.0, (t - start) / 0.6)
            y_base = H // 2 - 130 + items.index((name, desc, start)) * 120
            y = y_base + int(20 * (1 - ease_out_cubic(a)))
            draw_left(draw, name, 200, y, 32, GRAY1, True, a)
            draw_left(draw, desc, 200, y + 44, 22, GRAY3, False, a)

    if t > 3.2:
        a = min(1.0, (t - 3.2) / 0.7)
        float_reveal(draw, "El 95% de supermercados no puede permitirselo.",
                     H // 2 + 200, 26, RED, False, a)

    return apply_fade(img, fade_in)


def s04_solution(t: float, dur: float) -> Image.Image:
    """MermaOps reveal. The price."""
    img, draw = base()
    fade_in = min(1.0, t / 0.5)

    if t > 0.3:
        float_reveal(draw, "MermaOps", H // 2 - 170, 88, GREEN, True,
                     min(1.0, (t - 0.3) / 0.8))

    if t > 1.4:
        draw_line_reveal(draw, H // 2 - 42, min(1.0, (t - 1.4) / 0.5))

    if t > 2.0:
        a = min(1.0, (t - 2.0) / 0.9)
        float_reveal(draw, "0,80 €", H // 2 - 10, 140, WHITE, True, a)

    if t > 3.0:
        float_reveal(draw, "al mes. Sin hardware. Sin instalacion. Sin formacion.",
                     H // 2 + 160, 26, GRAY2, False, min(1.0, (t - 3.0) / 0.7))

    if t > 3.9:
        draw_pill(draw, W // 2, H // 2 + 220, "vs >20.000€ de Winnow",
                  18, GRAY3, GRAY1, min(1.0, (t - 3.9) / 0.5))

    return apply_fade(img, fade_in)


def s05_telegram(t: float, dur: float) -> Image.Image:
    """Telegram conversation. Typewriter bot response."""
    img, draw = base()
    fade_in = min(1.0, t / 0.5)

    if t > 0.2:
        float_reveal(draw, "El encargado ya tiene Telegram.", H // 2 - 420,
                     30, GRAY3, False, min(1.0, (t - 0.2) / 0.5))
        float_reveal(draw, "Sin apps nuevas. Sin formacion.", H // 2 - 378,
                     30, GRAY3, False, min(1.0, (t - 0.2) / 0.6))

    # Phone frame
    px, py, pw, ph = W // 2 - 260, H // 2 - 310, 520, 600
    if t > 0.6:
        fa = min(1.0, (t - 0.6) / 0.5)
        border = tuple(int(c * fa) for c in (40, 44, 52))
        draw.rounded_rectangle([px, py, px + pw, py + ph], radius=36, outline=border, width=3)
        # Header
        hdr_a = tuple(int(c * fa) for c in (22, 27, 34))
        draw.rounded_rectangle([px + 3, py + 3, px + pw - 3, py + 72],
                                radius=34, fill=hdr_a)
        draw_left(draw, "@ChuwiMermaOpsBot", px + 60, py + 20, 18, WHITE, True, fa)
        draw_left(draw, "en linea", px + 60, py + 44, 13,
                  tuple(int(c * fa) for c in GREEN), False, fa)

    # User bubble: appears at t=1.2
    if t > 1.2:
        a = min(1.0, (t - 1.2) / 0.4)
        bx, by, bw, bh = px + pw - 340, py + 95, 310, 52
        bc = tuple(int(c * a) for c in (36, 117, 221))
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=14, fill=bc)
        draw_left(draw, "Que hay critico ahora mismo?", bx + 14, by + 15,
                  16, tuple(int(c * a) for c in WHITE), False, a)

    # Bot typing dots: t=1.8 to 2.6
    if 1.8 < t < 2.6:
        for di in range(3):
            phase = (t - 1.8) * 4 - di * 0.4
            dot_a = max(0.0, math.sin(phase * math.pi))
            dot_x = px + 24 + di * 22
            dot_y = py + 175
            col = tuple(int(c * dot_a) for c in GRAY2)
            draw.ellipse([dot_x, dot_y, dot_x + 12, dot_y + 12], fill=col)

    # Bot response typewriter: starts t=2.6
    full_response = "Yogur Danone x4  -  REBAJAR HOY\nPasillo 2 · Score: 87/100\nPrecio actual 1,60E -> 1,30E\n(-19% · Margen 50% garantizado)"
    if t > 2.6:
        chars_per_sec = 30
        chars_shown = int((t - 2.6) * chars_per_sec)
        displayed = full_response[:chars_shown]
        lines = displayed.split("\n")
        bx, by = px + 14, py + 170
        bh_calc = 24 + len(full_response.split("\n")) * 28
        bw_r = pw - 50
        bc2 = (28, 36, 48)
        draw.rounded_rectangle([bx, by, bx + bw_r, by + bh_calc], radius=14, fill=bc2)
        for li, line in enumerate(lines):
            col = GREEN if li == 0 else WHITE if li <= 1 else GRAY2
            draw_left(draw, line, bx + 14, by + 12 + li * 28, 16, col, li == 0, 1.0)

        # Kuine attribution
        if chars_shown >= len(full_response):
            draw_left(draw, "Kuine · extended thinking · 6s",
                      px + 14, py + 460, 13, GRAY3, False, 1.0)

    return apply_fade(img, fade_in)


def s06_kuine_decision(t: float, dur: float) -> Image.Image:
    """Real Kuine decision from the DB — terminal style."""
    img, draw = base()
    fade_in = min(1.0, t / 0.5)

    if t > 0.2:
        float_reveal(draw, "Kuine. Inteligencia real.", H // 2 - 420,
                     32, GRAY3, False, min(1.0, (t - 0.2) / 0.5))

    # Terminal window
    tx, ty, tw, th_t = 200, H // 2 - 360, W - 400, 580
    if t > 0.5:
        fa = min(1.0, (t - 0.5) / 0.4)
        draw.rounded_rectangle([tx, ty, tx + tw, ty + th_t], radius=16,
                                outline=tuple(int(c * fa) for c in (40, 60, 40)), width=2,
                                fill=tuple(int(c * fa) for c in (8, 12, 8)))
        # Traffic lights
        for xi, col in [(tx + 22, RED), (tx + 52, GOLD), (tx + 82, GREEN)]:
            c = tuple(int(c * fa) for c in col)
            draw.ellipse([xi, ty + 20, xi + 20, ty + 40], fill=c)

    terminal_lines = [
        ("$ BRIEF 04/06/2026 · Super Martinez", GRAY3, 0.7),
        ("", WHITE, 0.0),
        ("ANALISIS: Yogur Danone x4", GRAY2, 1.0),
        ("  Pasillo 2 · Estanteria 3 · Nivel 1", GRAY3, 1.4),
        ("  Score: 87/100  |  Caduca: 4 dias", GRAY2, 1.8),
        ("", WHITE, 0.0),
        ("DECISION KUINE:", WHITE, 2.2),
        ("  REBAJAR -19% ->  1,30E  (antes 1,60E)", GREEN, 2.6),
        ("  Cluster 3 lotes · 12 packs al frente", GREEN2, 3.0),
        ("  Margen 50% garantizado · Coste 0,65E", GREEN2, 3.4),
        ("  FEFO verificado · Cadena frio max 4C", GRAY2, 3.8),
        ("", WHITE, 0.0),
        ("Validador: OK · Consenso 3/3 · Confianza 94%", GRAY3, 4.2),
    ]
    for li, (text, col, start) in enumerate(terminal_lines):
        if not text or t <= start:
            continue
        a = min(1.0, (t - start) / 0.35)
        draw_left(draw, text, tx + 24, ty + 62 + li * 38, 18,
                  tuple(int(c * a) for c in col), "DECISION" in text or "REBAJAR" in text, a)

    return apply_fade(img, fade_in)


def s07_agents(t: float, dur: float) -> Image.Image:
    """The Agentes MermaOps image — slow zoom reveal."""
    img, draw = base()
    fade_in = min(1.0, t / 0.7)

    if t > 0.4:
        float_reveal(draw, "12 agentes especializados.", 60, 36, GRAY3, False,
                     min(1.0, (t - 0.4) / 0.6))

    # Load and display agents image with Ken Burns zoom
    try:
        ag = Image.open(IMG_AGENTS).convert("RGB")
        ag_w, ag_h = ag.size

        # Ken Burns: slow pan from full view to zoom on top section
        zoom_progress = ease_in_out(min(1.0, max(0.0, t - 0.5) / (dur - 1.0)))
        scale = lerp(0.85, 1.15, zoom_progress)
        pan_y = lerp(0.0, 0.15, zoom_progress)  # pan down slightly

        # Scale image
        target_h = H - 140
        target_w = int(target_h * ag_w / ag_h)
        resized = ag.resize((target_w, target_h), Image.LANCZOS)

        # Apply scale (zoom)
        zoomed_w = int(target_w * scale)
        zoomed_h = int(target_h * scale)
        zoomed = resized.resize((zoomed_w, zoomed_h), Image.LANCZOS)

        # Crop to target size centered with pan
        crop_x = (zoomed_w - target_w) // 2
        crop_y = int((zoomed_h - target_h) * pan_y)
        cropped = zoomed.crop([crop_x, crop_y,
                                crop_x + target_w, crop_y + target_h])

        # Composite onto frame
        x_off = (W - target_w) // 2
        y_off = 120
        img_copy = img.copy()
        img_copy.paste(cropped, (x_off, y_off))

        # Fade the image
        img_a = min(1.0, (t - 0.3) / 0.8)
        img = Image.blend(img, img_copy, img_a)
        draw = ImageDraw.Draw(img)

        # Dark gradient at top and bottom for text readability
        for yi in range(130):
            alpha_grad = int(200 * (1 - yi / 130))
            draw.rectangle([0, yi, W, yi + 1],
                           fill=(0, 0, 0, 0) if False else (0, 0, 0))
        for yi in range(60):
            draw.rectangle([0, H - yi - 1, W, H - yi],
                           fill=(0, 0, 0))

    except Exception as e:
        draw_center(draw, f"[imagen no encontrada: {e}]", H // 2, 24, RED)

    return apply_fade(img, fade_in)


def s08_metrics(t: float, dur: float) -> Image.Image:
    """Big number cascade. Apple-style one-by-one."""
    img, draw = base()
    fade_in = min(1.0, t / 0.5)

    stats = [
        ("774",    "tests automatizados · 100% pass · 1,98s",  WHITE, 0.3),
        ("100%",   "precision · +83 puntos vs baseline",       GREEN, 2.2),
        ("23/23",  "ataques adversariales bloqueados",          WHITE, 4.1),
        ("483E",   "de merma identificada",                     GREEN, 6.0),
    ]

    # Show one at a time: big number then subtitle, then fades as next arrives
    current_i = 0
    for i, (val, sub, col, start) in enumerate(stats):
        if t >= start:
            current_i = i

    for i, (val, sub, col, start) in enumerate(stats):
        next_start = stats[i + 1][3] if i + 1 < len(stats) else dur
        visible_duration = next_start - start

        if t < start:
            continue

        local_t = t - start
        # Fade in
        in_a  = min(1.0, local_t / 0.5)
        # Fade out at end (0.5s before next)
        out_t = local_t - (visible_duration - 0.6)
        out_a = max(0.0, 1.0 - out_t / 0.6) if out_t > 0 else 1.0
        alpha = in_a * out_a

        if alpha < 0.01:
            continue

        c = tuple(int(ci * alpha) for ci in col)
        sub_c = tuple(int(ci * alpha) for ci in GRAY2)

        # Big number
        f_big = _font(148, True)
        tw = text_w(draw, val, f_big)
        y_num = H // 2 - 100 + int(20 * (1 - ease_out_cubic(min(1.0, local_t / 0.5))))
        draw.text(((W - tw) // 2, y_num), val, fill=c, font=f_big)

        # Subtitle
        f_sub = _font(28, False)
        tw2 = text_w(draw, sub, f_sub)
        y_sub = y_num + 180 + int(16 * (1 - ease_out_cubic(min(1.0, local_t / 0.6))))
        draw.text(((W - tw2) // 2, y_sub), sub, fill=sub_c, font=f_sub)

    return apply_fade(img, fade_in)


def s09_close(t: float, dur: float) -> Image.Image:
    """Closing. Fade out."""
    img, draw = base()

    fade_in  = min(1.0, t / 0.7)
    # Final fade to black at end
    fade_out = max(0.0, 1.0 - (t - (dur - 2.0)) / 2.0) if t > dur - 2.0 else 1.0
    alpha = fade_in * fade_out

    if t > 0.5:
        a = min(1.0, (t - 0.5) / 0.8) * alpha
        float_reveal(draw, "MermaOps", H // 2 - 80, 88, WHITE, True,
                     min(1.0, (t - 0.5) / 0.8))
        # Manually re-blend for combined alpha
        img2, draw2 = base()
        float_reveal(draw2, "MermaOps", H // 2 - 80, 88, WHITE, True, 1.0)
        img = Image.blend(img, img2, a)
        draw = ImageDraw.Draw(img)

    if t > 1.4:
        a = min(1.0, (t - 1.4) / 0.6) * alpha
        draw_line_reveal(draw, H // 2 + 30, min(1.0, (t - 1.4) / 0.7))
        img2, draw2 = base()
        draw_line_reveal(draw2, H // 2 + 30, 1.0)
        img = Image.blend(img, img2, a)
        draw = ImageDraw.Draw(img)

    for text, y_off, start, col in [
        ("@ChuwiMermaOpsBot", 60, 2.2, GRAY2),
        ("0,80 E/mes · Sin hardware · Kuine · 12 agentes", 110, 3.0, GRAY3),
        ("Alvaro Ferrer Muro · EVOLVE Madrid 2026", 160, 3.8, GRAY3),
    ]:
        if t > start:
            a = min(1.0, (t - start) / 0.6) * fade_out
            y = H // 2 + 30 + y_off + int(16 * (1 - ease_out_cubic(min(1.0, (t - start) / 0.6))))
            f = _font(22 if y_off > 60 else 26)
            tw = text_w(draw, text, f)
            c = tuple(int(ci * a) for ci in col)
            draw.text(((W - tw) // 2, y), text, fill=c, font=f)

    return apply_fade(img, fade_out)


# ═══════════════════════════════════════════════════════════════════════
# MUSIC — Cinematic piano + pad ambient
# ═══════════════════════════════════════════════════════════════════════

def generate_music(duration_s: float, path: str):
    """
    Cinematic ambient music:
    - Bass drone (A1 = 55Hz) + warmth
    - Pad chords: Am - F - C - G progression
    - Subtle piano-like attack (ADSR envelope on each chord hit)
    - Shimmer layer at high frequency
    - Fade in 3s, fade out 4s
    """
    n = int(SR * duration_s)
    t = np.linspace(0, duration_s, n, endpoint=False)
    sig = np.zeros(n)

    # Bass drone
    sig += 0.18 * np.sin(2 * np.pi * 55.0 * t)  # A1

    # Chord progression: Am - F - C - G (each ~8 seconds)
    chord_dur = 8.0
    chords = [
        [220.0, 261.63, 329.63, 440.0],   # Am: A3 C4 E4 A4
        [174.61, 220.0, 261.63, 349.23],  # F: F3 A3 C4 F4
        [261.63, 329.63, 392.0, 523.25],  # C: C4 E4 G4 C5
        [196.0, 246.94, 293.66, 392.0],   # G: G3 B3 D4 G4
    ]

    for ci, chord in enumerate(chords * (int(duration_s // (chord_dur * len(chords))) + 2)):
        t_start = ci * chord_dur
        if t_start >= duration_s:
            break
        t_end = min(t_start + chord_dur, duration_s)
        idx_s = int(t_start * SR)
        idx_e = int(t_end * SR)
        chunk_len = idx_e - idx_s
        if chunk_len <= 0:
            continue

        tc = np.linspace(0, chord_dur, chunk_len, endpoint=False)

        # ADSR envelope: attack 0.1s, decay 0.3s, sustain 0.65, release 2s
        env = np.ones(chunk_len)
        att = int(0.1 * SR)
        dec = int(0.3 * SR)
        rel = int(2.0 * SR)
        for ii in range(min(att, chunk_len)):
            env[ii] = ii / att
        for ii in range(att, min(att + dec, chunk_len)):
            env[ii] = 1.0 - 0.35 * (ii - att) / dec
        for ii in range(max(0, chunk_len - rel), chunk_len):
            env[ii] *= max(0.0, 1.0 - (ii - (chunk_len - rel)) / rel)

        pad = np.zeros(chunk_len)
        for freq in chord:
            # Slight detuning for richness
            pad += 0.18 * np.sin(2 * np.pi * freq * tc)
            pad += 0.06 * np.sin(2 * np.pi * freq * 1.005 * tc)  # detune

        sig[idx_s:idx_e] += pad * env

    # Shimmer: high frequency tremolo
    shimmer = 0.04 * np.sin(2 * np.pi * 2637.0 * t)  # E7
    lfo_fast = 0.5 + 0.5 * np.sin(2 * np.pi * 0.25 * t)
    sig += shimmer * lfo_fast

    # Slow LFO on whole signal
    lfo_slow = 0.80 + 0.20 * np.sin(2 * np.pi * 0.08 * t)
    sig *= lfo_slow

    # Fade in / out
    fade_in_s  = int(3.0 * SR)
    fade_out_s = int(4.0 * SR)
    sig[:fade_in_s] *= np.linspace(0, 1, fade_in_s)
    sig[-fade_out_s:] *= np.linspace(1, 0, fade_out_s)

    # Normalize
    peak = np.max(np.abs(sig)) or 1.0
    pcm = (sig / peak * 26000).astype(np.int16)

    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ═══════════════════════════════════════════════════════════════════════
# SLIDE SCHEDULE
# ═══════════════════════════════════════════════════════════════════════

SLIDES = [
    (s01_logo,        8),
    (s02_problem,     9),
    (s03_competitors, 9),
    (s04_solution,    9),
    (s05_telegram,   12),
    (s06_kuine_decision, 11),
    (s07_agents,     10),
    (s08_metrics,    12),
    (s09_close,       9),
]

TOTAL = sum(d for _, d in SLIDES)

# Precompute cumulative start times
_starts: list[float] = []
_s = 0.0
for _, d in SLIDES:
    _starts.append(_s)
    _s += d


def make_frame(t: float) -> np.ndarray:
    # Find which slide
    idx = 0
    for i, start in enumerate(_starts):
        if t >= start:
            idx = i
    fn, dur = SLIDES[idx]
    local_t = t - _starts[idx]
    img = fn(local_t, dur)
    return np.array(img)


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"\nMermaOps Launch Video")
    print(f"  {W}x{H} · {FPS}fps · {TOTAL}s")
    print(f"  Output: {OUT}\n")

    music_path = str(ROOT / "docs" / "_music_launch.wav")
    print("  [1/3] Generando musica cinematica...")
    generate_music(TOTAL + 2, music_path)
    print("        OK")

    from moviepy import VideoClip, AudioFileClip

    print("  [2/3] Renderizando frames...")
    clip = VideoClip(make_frame, duration=TOTAL).with_fps(FPS)

    print("  [3/3] Codificando video...")
    audio = AudioFileClip(music_path).subclipped(0, TOTAL)
    clip = clip.with_audio(audio)
    clip.write_videofile(
        str(OUT), fps=FPS, codec="libx264", audio_codec="aac",
        bitrate="5000k", logger="bar",
        ffmpeg_params=["-pix_fmt", "yuv420p", "-crf", "18"],
    )

    try: os.remove(music_path)
    except: pass

    size_mb = OUT.stat().st_size / 1_048_576
    print(f"\n  Video listo: {OUT}")
    print(f"  Duracion: {TOTAL}s · Tamano: {size_mb:.1f} MB")
