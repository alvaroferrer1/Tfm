"""
gen_video_master.py — The definitive MermaOps video.

Output: docs/MermaOps_Master.mp4  (1920x1080, 30fps, ~2min)

Visual quality level:
  - Radial glow backgrounds (like Apple/Google keynotes)
  - Particle field (floating dots)
  - Glowing text on key numbers
  - Motion blur on transitions
  - Ken Burns on Agentes image
  - Real Telegram conversation with typewriter
  - Terminal window with real Kuine decision
  - Metric counter cascade with glow
  - Cinematic piano + pad music (Am → F → C → G)

Uso: python scripts/gen_video_master.py
"""
from __future__ import annotations
import sys, os, math, wave, time as _time
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).parent.parent
AGENTS_IMG = ROOT / "Agentes MermaOps.png"
OUT = ROOT / "docs" / "MermaOps_Master.mp4"

W, H = 1920, 1080
FPS  = 30
SR   = 44100

# ── Palette ────────────────────────────────────────────────────────────────
BLACK   = (0,   0,   0)
WHITE   = (255, 255, 255)
GREEN   = (16,  185, 129)
GLIGHT  = (52,  211, 153)
GDARK   = (6,   78,  59)
GRAY1   = (229, 231, 235)
GRAY2   = (156, 163, 175)
GRAY3   = (75,  85,  99)
GRAY4   = (30,  40,  55)
RED     = (239, 68,  68)
ORANGE  = (249, 115, 22)
GOLD    = (234, 179, 8)
BLUE    = (96,  165, 250)
PURPLE  = (139, 92,  246)

# ── Random seed for consistent particles ──────────────────────────────────
rng = np.random.default_rng(42)
N_PARTICLES = 80
PX = rng.uniform(0, W, N_PARTICLES)
PY = rng.uniform(0, H, N_PARTICLES)
PS = rng.uniform(1.5, 4.0, N_PARTICLES)   # size
PV = rng.uniform(6, 18,  N_PARTICLES)     # speed
PA = rng.uniform(0, 2*math.pi, N_PARTICLES)  # angle


# ── Easing ─────────────────────────────────────────────────────────────────
def eoc(t): t=max(0.,min(1.,t)); return 1-(1-t)**3
def eio(t): t=max(0.,min(1.,t)); return t*t*(3-2*t)
def lerp(a,b,t): return a+(b-a)*max(0.,min(1.,t))
def clamp(v,a,b): return max(a,min(b,v))


# ── Font ────────────────────────────────────────────────────────────────────
_FC = {}
def font(size, bold=False):
    k=(size,bold)
    if k not in _FC:
        for n in (["arialbd.ttf","Arial Bold.ttf","DejaVuSans-Bold.ttf","LiberationSans-Bold.ttf"] if bold
                  else ["arial.ttf","Arial.ttf","DejaVuSans.ttf","LiberationSans-Regular.ttf"]):
            try: _FC[k]=ImageFont.truetype(n,size); break
            except: pass
        if k not in _FC: _FC[k]=ImageFont.load_default()
    return _FC[k]

def tw(draw,text,f): bb=draw.textbbox((0,0),text,font=f); return bb[2]-bb[0]
def th(draw,text,f): bb=draw.textbbox((0,0),text,font=f); return bb[3]-bb[1]


# ── Core drawing ────────────────────────────────────────────────────────────
def base_frame() -> Image.Image:
    return Image.new("RGBA", (W, H), (0,0,0,255))

def draw_particles(img: Image.Image, t: float, alpha: float = 0.4):
    """Floating particle field."""
    overlay = Image.new("RGBA", (W, H), (0,0,0,0))
    d = ImageDraw.Draw(overlay)
    for i in range(N_PARTICLES):
        x = (PX[i] + math.cos(PA[i]) * PV[i] * t) % W
        y = (PY[i] + math.sin(PA[i]) * PV[i] * t) % H
        pulse = 0.4 + 0.6 * math.sin(t * 0.8 + i * 0.3)
        a = int(60 * alpha * pulse)
        s = PS[i]
        col = (*GREEN, a)
        d.ellipse([x-s, y-s, x+s, y+s], fill=col)
    return Image.alpha_composite(img, overlay)

def radial_glow(img: Image.Image, cx: int, cy: int,
                radius: int, color: tuple, intensity: float = 0.6):
    """Soft radial glow at position."""
    glow = Image.new("RGBA", (W, H), (0,0,0,0))
    d = ImageDraw.Draw(glow)
    steps = 8
    for i in range(steps, 0, -1):
        r = int(radius * i / steps)
        a = int(255 * intensity * (1 - i/steps)**1.5)
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(*color, a))
    # Blur for soft glow
    glow = glow.filter(ImageFilter.GaussianBlur(radius // 4))
    return Image.alpha_composite(img, glow)

def text_glow(img: Image.Image, draw: ImageDraw.ImageDraw,
              text: str, x: int, y: int, f,
              color: tuple, glow_color: tuple, glow_radius: int = 20, alpha: float = 1.0):
    """Text with soft glow behind it."""
    if alpha <= 0: return img
    # Glow layer
    glow_img = Image.new("RGBA", (W, H), (0,0,0,0))
    gd = ImageDraw.Draw(glow_img)
    gd.text((x, y), text, fill=(*glow_color, int(200*alpha)), font=f)
    glow_img = glow_img.filter(ImageFilter.GaussianBlur(glow_radius))
    img = Image.alpha_composite(img, glow_img)
    # Actual text
    draw2 = ImageDraw.Draw(img)
    c = (*color, int(255*alpha))
    draw2.text((x, y), text, fill=c, font=f)
    return img

def center_text_glow(img, text, y, size, color, glow_color,
                     bold=False, glow_r=24, alpha=1.0):
    f = font(size, bold)
    dummy = ImageDraw.Draw(img)
    x = (W - tw(dummy, text, f)) // 2
    return text_glow(img, dummy, text, x, y, f, color, glow_color, glow_r, alpha)

def center_text(img, draw, text, y, size, color=WHITE, bold=False, alpha=1.0, float_off=0):
    if alpha <= 0: return
    f = font(size, bold)
    x = (W - tw(draw, text, f)) // 2
    c = tuple(int(ci * alpha) for ci in color)
    draw.text((x, y + float_off), text, fill=c, font=f)

def left_text(draw, text, x, y, size, color=WHITE, bold=False, alpha=1.0):
    if alpha <= 0: return
    f = font(size, bold)
    c = tuple(int(ci * alpha) for ci in color)
    draw.text((x, y), text, fill=c, font=f)

def slide_line(draw, y, progress, color=GREEN, margin=280, h=3):
    """Green line slides in from center."""
    a = eoc(progress)
    full_w = W - margin * 2
    x0 = W // 2 - int(full_w * a / 2)
    x1 = W // 2 + int(full_w * a / 2)
    if x1 > x0:
        draw.rectangle([x0, y, x1, y + h], fill=color)

def float_y(y_base, t_reveal, range_px=24):
    return y_base + int(range_px * (1 - eoc(t_reveal)))

def fade_alpha(t_start, t, speed=0.7, t_end=None, fade_out_speed=0.5):
    a_in = clamp((t - t_start) / speed, 0, 1)
    a_out = 1.0
    if t_end is not None:
        a_out = clamp(1 - (t - t_end) / fade_out_speed, 0, 1)
    return eoc(a_in) * a_out

def apply_fade_to_black(img, alpha):
    if alpha >= 1.0: return img
    black = Image.new("RGBA", (W, H), (0,0,0,255))
    return Image.blend(black.convert("RGB"), img.convert("RGB"), max(0,min(1,alpha))).convert("RGBA")


# ══════════════════════════════════════════════════════════════════════════
# SLIDES
# ══════════════════════════════════════════════════════════════════════════

def s_intro(t, dur):
    """Pure black. MermaOps name appears with green glow. Tagline. Green line."""
    img = base_frame()
    img = draw_particles(img, t, alpha=0.25)
    img = radial_glow(img, W//2, H//2, 500, GREEN, 0.08 + 0.04*math.sin(t))

    a_title = fade_alpha(0.3, t, 0.9)
    if a_title > 0:
        img = center_text_glow(img, "MermaOps", H//2 - 95,
                                96, WHITE, GREEN, bold=True, glow_r=40, alpha=a_title)

    d = ImageDraw.Draw(img)
    a_line = fade_alpha(1.2, t, 0.6)
    slide_line(d, H//2 + 40, a_line)

    a_sub = fade_alpha(1.9, t, 0.7)
    center_text(img, d, "Sistema Multi-Agente de IA para Reduccion de Merma Alimentaria",
                H//2 + 72, 26, GRAY2, bold=False, alpha=a_sub,
                float_off=float_y(0, clamp((t-1.9)/0.7,0,1)))

    a_badge = fade_alpha(2.7, t, 0.6)
    center_text(img, d, "EVOLVE Madrid 2026  ·  Alvaro Ferrer Muro",
                H//2 + 120, 19, GRAY3, alpha=a_badge)

    fade = fade_alpha(0, t, 0.4)
    return apply_fade_to_black(img, fade)


def s_problem(t, dur):
    """The problem. Big 2-5% with red glow."""
    img = base_frame()
    img = draw_particles(img, t, 0.15)

    d = ImageDraw.Draw(img)
    a0 = fade_alpha(0.2, t, 0.6)
    center_text(img, d, "El problema.", H//2 - 280, 28, GRAY3, alpha=a0,
                float_off=float_y(0, clamp((t-0.2)/0.6,0,1)))

    a1 = fade_alpha(0.8, t, 0.8)
    if a1 > 0:
        img = radial_glow(img, W//2, H//2 - 60, 350, RED, 0.18 * a1)
        img = center_text_glow(img, "2 - 5%", H//2 - 160,
                                168, WHITE, RED, bold=True, glow_r=50, alpha=a1)

    d = ImageDraw.Draw(img)
    a2 = fade_alpha(2.0, t, 0.7)
    center_text(img, d, "de los ingresos del supermercado", H//2 + 70,
                32, GRAY1, alpha=a2, float_off=float_y(0, clamp((t-2.0)/0.7,0,1)))
    a3 = fade_alpha(2.8, t, 0.7)
    center_text(img, d, "se pierde en merma alimentaria cada ano.", H//2 + 118,
                30, GRAY2, alpha=a3, float_off=float_y(0, clamp((t-2.8)/0.7,0,1)))
    a4 = fade_alpha(3.6, t, 0.6)
    center_text(img, d, "15.000 - 40.000 euros anuales por tienda.", H//2 + 182,
                24, RED, alpha=a4, float_off=float_y(0, clamp((t-3.6)/0.6,0,1)))

    fade = fade_alpha(0, t, 0.35)
    return apply_fade_to_black(img, fade)


def s_winnow(t, dur):
    """Competitors. Strike them out one by one."""
    img = base_frame()
    img = draw_particles(img, t, 0.12)
    d = ImageDraw.Draw(img)

    a0 = fade_alpha(0.2, t, 0.5)
    center_text(img, d, "Las soluciones existentes...", H//2 - 320, 30, GRAY3, alpha=a0)

    items = [
        ("Winnow V2",      "Mas de 20.000 euros  +  hardware especializado  +  instalacion",  RED,    0.8),
        ("Orbisk",         "Mas de 15.000 euros  +  camara IA  +  servidor dedicado",         ORANGE, 1.6),
        ("Excel / papel",  "Sin datos reales  ·  Sin IA  ·  Sin autonomia",                   GRAY3,  2.4),
    ]
    for i, (name, desc, col, start) in enumerate(items):
        a = fade_alpha(start, t, 0.55)
        y = H//2 - 170 + i * 130
        fy = float_y(0, clamp((t-start)/0.55,0,1))
        left_text(d, name, 200, y + fy, 36, GRAY1, bold=True, alpha=a)
        left_text(d, desc, 200, y + 50 + fy, 20, GRAY3, alpha=a)
        # Red X
        if a > 0.3:
            xc = tuple(int(c * a) for c in col)
            d.rectangle([165, y+fy+8, 185, y+fy+28], fill=xc)
            d.rectangle([165, y+fy+8, 185, y+fy+28], fill=xc)
            # small X mark
            d.line([165, y+8+fy, 185, y+28+fy], fill=xc, width=3)
            d.line([185, y+8+fy, 165, y+28+fy], fill=xc, width=3)

    a_end = fade_alpha(3.4, t, 0.7)
    if a_end > 0:
        # Highlight box
        box_y = H//2 + 180
        box_a = int(255 * a_end)
        overlay = Image.new("RGBA", (W, H), (0,0,0,0))
        od = ImageDraw.Draw(overlay)
        od.rounded_rectangle([200, box_y, W-200, box_y+64], radius=12,
                              fill=(6,78,59,int(120*a_end)),
                              outline=(*GREEN, int(200*a_end)), width=2)
        img = Image.alpha_composite(img, overlay)
        d2 = ImageDraw.Draw(img)
        center_text(img, d2, "El 95% de supermercados no puede permitirselo.",
                    box_y + 18, 24, GREEN, alpha=a_end)

    fade = fade_alpha(0, t, 0.35)
    return apply_fade_to_black(img, fade)


def s_reveal(t, dur):
    """MermaOps solution reveal. Green glow explosion."""
    img = base_frame()

    # Growing radial glow
    glow_r = int(lerp(100, 600, clamp((t-0.3)/1.2, 0, 1)))
    glow_i = lerp(0, 0.35, clamp((t-0.3)/1.2, 0, 1))
    img = radial_glow(img, W//2, H//2, glow_r, GREEN, glow_i)
    img = draw_particles(img, t, 0.3 * clamp(t/1.0, 0, 1))

    a_name = fade_alpha(0.3, t, 0.9)
    if a_name > 0:
        img = center_text_glow(img, "MermaOps", H//2 - 180,
                                104, GREEN, GLIGHT, bold=True, glow_r=60, alpha=a_name)

    d = ImageDraw.Draw(img)
    a_line = fade_alpha(1.3, t, 0.6)
    slide_line(d, H//2 - 48, a_line)

    a_price = fade_alpha(1.9, t, 0.9)
    if a_price > 0:
        img = center_text_glow(img, "0,80 EUR / mes", H//2 - 15,
                                88, WHITE, GREEN, bold=True, glow_r=30, alpha=a_price)

    d2 = ImageDraw.Draw(img)
    a_sub = fade_alpha(2.8, t, 0.7)
    center_text(img, d2, "Sin hardware  ·  Sin instalacion  ·  Sin formacion",
                H//2 + 105, 26, GRAY2, alpha=a_sub,
                float_off=float_y(0, clamp((t-2.8)/0.7,0,1)))

    a_badge = fade_alpha(3.5, t, 0.6)
    if a_badge > 0:
        badges = [("Telegram", BLUE), ("Flutter App", PURPLE), ("24/7 Autonomo", GREEN)]
        total_w = 3 * 200 + 2 * 20
        sx = (W - total_w) // 2
        overlay = Image.new("RGBA", (W, H), (0,0,0,0))
        od = ImageDraw.Draw(overlay)
        for bi, (btext, bcol) in enumerate(badges):
            bx = sx + bi * 220
            by = H//2 + 160
            od.rounded_rectangle([bx, by, bx+200, by+44], radius=22,
                                  fill=(*GRAY4, int(200*a_badge)),
                                  outline=(*bcol, int(180*a_badge)), width=2)
            bf = font(17, True)
            btw = tw(od, btext, bf)
            od.text((bx + (200-btw)//2, by+13), btext,
                    fill=(*bcol, int(220*a_badge)), font=bf)
        img = Image.alpha_composite(img, overlay)

    fade = fade_alpha(0, t, 0.35)
    return apply_fade_to_black(img, fade)


def s_telegram(t, dur):
    """Real Telegram conversation. Phone mockup. Typewriter."""
    img = base_frame()
    img = draw_particles(img, t, 0.10)
    d = ImageDraw.Draw(img)

    a_title = fade_alpha(0.2, t, 0.5)
    center_text(img, d, "El encargado ya tiene Telegram.", H//2 - 430,
                28, GRAY3, alpha=a_title)
    center_text(img, d, "Sin apps nuevas. Zero friccion.", H//2 - 390,
                28, GRAY3, alpha=a_title)

    # Phone frame
    pw, ph = 540, 660
    px_f = W//2 - pw//2
    py_f = H//2 - ph//2 - 20
    a_phone = fade_alpha(0.5, t, 0.5)
    if a_phone > 0:
        overlay = Image.new("RGBA", (W, H), (0,0,0,0))
        od = ImageDraw.Draw(overlay)
        # Shadow
        od.rounded_rectangle([px_f+8, py_f+8, px_f+pw+8, py_f+ph+8],
                              radius=32, fill=(0,0,0,int(100*a_phone)))
        # Body
        od.rounded_rectangle([px_f, py_f, px_f+pw, py_f+ph],
                              radius=32, fill=(18,22,30,int(240*a_phone)),
                              outline=(50,60,80,int(200*a_phone)), width=2)
        # Header bar
        od.rounded_rectangle([px_f+2, py_f+2, px_f+pw-2, py_f+76],
                              radius=30, fill=(25,32,44,int(240*a_phone)))
        od.text((px_f+60, py_f+20), "@ChuwiMermaOpsBot",
                fill=(255,255,255,int(200*a_phone)), font=font(17,True))
        od.text((px_f+60, py_f+46), "en linea",
                fill=(*GREEN, int(180*a_phone)), font=font(13))
        # Green dot
        od.ellipse([px_f+40, py_f+47, px_f+54, py_f+61],
                   fill=(*GREEN, int(200*a_phone)))
        img = Image.alpha_composite(img, overlay)

    # User bubble
    a_user = fade_alpha(1.2, t, 0.45)
    if a_user > 0:
        ov2 = Image.new("RGBA", (W, H), (0,0,0,0))
        od2 = ImageDraw.Draw(ov2)
        bw, bh = 330, 52
        bx = px_f + pw - bw - 18
        by = py_f + 95
        od2.rounded_rectangle([bx, by, bx+bw, by+bh], radius=14,
                               fill=(36,117,221,int(220*a_user)))
        od2.text((bx+14, by+15), "Que hay critico ahora mismo?",
                 fill=(255,255,255,int(220*a_user)), font=font(16))
        img = Image.alpha_composite(img, ov2)

    # Typing dots t=1.8..2.7
    if 1.8 < t < 2.7:
        for di in range(3):
            phase = (t-1.8)*3.5 - di*0.4
            dot_a = max(0.0, math.sin(phase*math.pi))
            dx = px_f + 24 + di * 22
            dy = py_f + 175
            ov3 = Image.new("RGBA", (W,H),(0,0,0,0))
            od3 = ImageDraw.Draw(ov3)
            od3.ellipse([dx, dy, dx+14, dy+14],
                        fill=(*GRAY2, int(180*dot_a)))
            img = Image.alpha_composite(img, ov3)

    # Bot response typewriter
    full_msg = ("Yogur Danone x4  --  REBAJAR HOY\n"
                "Pasillo 2  |  Score: 87/100\n"
                "Precio actual 1,60E  -->  1,30E\n"
                "(-19%  ·  Margen 50%  ·  FEFO OK)")
    if t > 2.7:
        cps = 28
        chars = int((t-2.7)*cps)
        displayed = full_msg[:chars]
        lines = displayed.split("\n")
        bx = px_f + 14
        by = py_f + 168
        full_lines = full_msg.split("\n")
        total_h = len(full_lines)*30 + 24
        ov4 = Image.new("RGBA", (W,H),(0,0,0,0))
        od4 = ImageDraw.Draw(ov4)
        od4.rounded_rectangle([bx, by, bx+pw-28, by+total_h],
                               radius=14, fill=(22,32,44,230))
        for li, line in enumerate(lines):
            col = (*GREEN, 220) if li==0 else ((200,200,200,200) if li<=1 else (100,120,100,180))
            od4.text((bx+14, by+12+li*30), line, fill=col,
                     font=font(15, li==0))
        img = Image.alpha_composite(img, ov4)
        # Attribution
        if chars >= len(full_msg):
            d3 = ImageDraw.Draw(img)
            left_text(d3, "Kuine  ·  extended thinking  ·  6s  ·  Validador OK",
                      px_f+14, py_f+520, 13, GRAY3, alpha=1.0)

    fade = fade_alpha(0, t, 0.35)
    return apply_fade_to_black(img, fade)


def s_kuine_terminal(t, dur):
    """Terminal. Real Kuine decision. Green glow."""
    img = base_frame()
    img = draw_particles(img, t, 0.12)
    img = radial_glow(img, W//2, H//2, 600, GDARK, 0.20)

    d = ImageDraw.Draw(img)
    a_title = fade_alpha(0.2, t, 0.5)
    if a_title > 0:
        img = center_text_glow(img, "Kuine.", H//2 - 430,
                                40, WHITE, GREEN, bold=True, glow_r=20, alpha=a_title)
        d2 = ImageDraw.Draw(img)
        center_text(img, d2, "Inteligencia real. Datos reales.", H//2 - 380,
                    22, GRAY3, alpha=a_title)

    # Terminal box
    tx, ty, tw_t, th_t = 180, H//2 - 350, W-360, 600
    a_box = fade_alpha(0.5, t, 0.4)
    if a_box > 0:
        ov = Image.new("RGBA", (W,H),(0,0,0,0))
        od = ImageDraw.Draw(ov)
        od.rounded_rectangle([tx, ty, tx+tw_t, ty+th_t], radius=16,
                              fill=(6,10,6,int(240*a_box)),
                              outline=(*GREEN, int(120*a_box)), width=2)
        # Traffic lights
        for xi, col in [(tx+22,RED),(tx+52,GOLD),(tx+82,GREEN)]:
            od.ellipse([xi, ty+18, xi+20, ty+38], fill=(*col, int(200*a_box)))
        img = Image.alpha_composite(img, ov)

    # Terminal lines with stagger
    lines = [
        ("$ BRIEF 04/06/2026  ·  Super Martinez", GRAY3, 0.8,  False),
        ("",                                       WHITE,  0,    False),
        ("Analizando inventario: 7 lotes activos", GRAY3, 1.2,  False),
        ("Score heuristico: 72  |  Threshold: 65", GRAY3, 1.5,  False),
        ("Extended thinking: ACTIVADO (budget 4000t)", GRAY3, 1.8, False),
        ("",                                       WHITE,  0,    False),
        ("DECISION KUINE:",                        WHITE,  2.2,  True),
        ("  REBAJAR -19%  -->  1,30E  (antes 1,60E)", GREEN, 2.6, True),
        ("  Cluster 3 lotes · 12 packs al frente", GLIGHT, 3.0, False),
        ("  Margen 50% garantizado · Coste 0,65E", GLIGHT, 3.4, False),
        ("  FEFO verificado · Cadena frio max 4C", GRAY3, 3.8, False),
        ("",                                       WHITE,  0,    False),
        ("Validador: PASS  ·  Consenso: 3/3  ·  Confianza: 94%", GRAY3, 4.3, False),
    ]
    for li, (ltext, col, start, bold) in enumerate(lines):
        if not ltext or t < start:
            continue
        a = clamp((t-start)/0.3, 0, 1)
        c = tuple(int(ci*a) for ci in col)
        d2 = ImageDraw.Draw(img)
        d2.text((tx+26, ty+56+li*38), ltext, fill=c, font=font(17, bold))

    # Glow on REBAJAR line
    if t > 2.6:
        glo_a = clamp((t-2.6)/0.5, 0, 1)
        img = radial_glow(img, tx+400, ty+56+7*38+10, 180, GREEN, 0.25*glo_a)

    fade = fade_alpha(0, t, 0.35)
    return apply_fade_to_black(img, fade)


def s_agents(t, dur):
    """Ken Burns on Agentes MermaOps.png."""
    img = base_frame()
    img = draw_particles(img, t, 0.10)
    d = ImageDraw.Draw(img)

    a_title = fade_alpha(0.2, t, 0.5)
    center_text(img, d, "12 agentes. Un sistema.", 60, 36, GRAY3,
                alpha=a_title, float_off=float_y(0, clamp((t-0.2)/0.5,0,1)))

    try:
        ag = Image.open(AGENTS_IMG).convert("RGB")
        ag_w, ag_h = ag.size

        target_h = H - 130
        target_w = int(target_h * ag_w / ag_h)

        zoom_prog = eio(clamp((t-0.4)/(dur-1.2), 0, 1))
        scale = lerp(0.88, 1.18, zoom_prog)
        pan_x = lerp(0.0, 0.05, zoom_prog)
        pan_y = lerp(0.0, 0.12, zoom_prog)

        zoomed_w = int(target_w * scale)
        zoomed_h = int(target_h * scale)
        resized = ag.resize((target_w, target_h), Image.LANCZOS)
        zoomed  = resized.resize((zoomed_w, zoomed_h), Image.LANCZOS)

        cx = int((zoomed_w - target_w) * pan_x)
        cy = int((zoomed_h - target_h) * pan_y)
        cropped = zoomed.crop([cx, cy, cx+target_w, cy+target_h])

        xoff = (W - target_w) // 2
        yoff = 110

        img_copy = img.copy().convert("RGBA")
        tmp = Image.new("RGBA", (W,H),(0,0,0,0))
        tmp.paste(cropped.convert("RGBA"), (xoff, yoff))

        img_a = clamp((t-0.3)/0.8, 0, 1)
        img = Image.alpha_composite(img.convert("RGBA"), tmp if img_a >= 1.0
                                    else Image.new("RGBA",(W,H),(0,0,0,0)).__class__.blend(
                                        Image.new("RGBA",(W,H),(0,0,0,0)), tmp, img_a))

        # Gradient top/bottom
        ov2 = Image.new("RGBA",(W,H),(0,0,0,0))
        for yi in range(120):
            a = int(255*(1-yi/120))
            ov2.paste((0,0,0,a), (0,yi,W,yi+1))
        for yi in range(50):
            a = int(255*(1-(50-yi)/50))
            ov2.paste((0,0,0,a), (0,H-50+yi,W,H-50+yi+1))
        img = Image.alpha_composite(img.convert("RGBA"), ov2)

    except Exception as e:
        ImageDraw.Draw(img).text((W//2-100, H//2), f"[img error: {e}]",
                                 fill=RED, font=font(20))

    fade = fade_alpha(0, t, 0.35)
    return apply_fade_to_black(img, fade)


def s_metrics(t, dur):
    """Big number cascade. One at a time. Green glow."""
    img = base_frame()
    img = draw_particles(img, t, 0.15)
    d = ImageDraw.Draw(img)

    metrics = [
        ("774",  "tests automatizados  ·  100% pass  ·  1,98s", WHITE,  GREEN,  0.3),
        ("100%", "de precision  ·  +83 puntos vs baseline",      GREEN,  GLIGHT, 2.5),
        ("23/23","ataques adversariales bloqueados",              WHITE,  GREEN,  4.7),
        ("483E", "de merma identificada  ·  datos reales",       GREEN,  GLIGHT, 6.9),
    ]

    current_i = sum(1 for _,_,_,_,start in metrics if t >= start) - 1
    if current_i < 0: current_i = 0

    for i, (val, sub, col, gcol, start) in enumerate(metrics):
        next_s = metrics[i+1][4] if i+1 < len(metrics) else dur
        local = t - start
        a_in  = eoc(clamp(local/0.65, 0, 1))
        a_out = eoc(clamp(1-(t-next_s+0.7)/0.7, 0, 1)) if t > next_s-0.7 else 1.0
        alpha = a_in * a_out
        if t < start or alpha < 0.01:
            continue

        # Glow on current
        img = radial_glow(img, W//2, H//2 - 50, 400, gcol,
                          0.30 * alpha * (0.8 + 0.2*math.sin(t*2)))

        # Big number
        f_big = font(172, True)
        dummy = ImageDraw.Draw(img)
        x = (W - tw(dummy, val, f_big)) // 2
        y = H//2 - 145 + float_y(0, clamp(local/0.65, 0, 1))
        img = text_glow(img, dummy, val, x, y, f_big,
                        col, gcol, glow_radius=50, alpha=alpha)

        # Subtitle
        d2 = ImageDraw.Draw(img)
        f_sub = font(27)
        x_sub = (W - tw(d2, sub, f_sub)) // 2
        y_sub = H//2 + 80 + float_y(0, clamp(local/0.7, 0, 1))
        c_sub = tuple(int(ci*alpha) for ci in GRAY2)
        d2.text((x_sub, y_sub), sub, fill=c_sub, font=f_sub)

    fade = fade_alpha(0, t, 0.35)
    return apply_fade_to_black(img, fade)


def s_compare(t, dur):
    """Comparison table. MermaOps highlighted."""
    img = base_frame()
    img = draw_particles(img, t, 0.10)
    d = ImageDraw.Draw(img)

    a_title = fade_alpha(0.2, t, 0.5)
    if a_title > 0:
        img = center_text_glow(img, "MermaOps", H//2 - 430,
                                36, GREEN, GREEN, bold=True, glow_r=15, alpha=a_title)
        d2 = ImageDraw.Draw(img)
        center_text(img, d2, "frente a las soluciones existentes", H//2 - 380,
                    24, GRAY3, alpha=a_title)

    headers = ["", "MermaOps", "Winnow V2", "Baseline"]
    col_x   = [180, 560, 1050, 1500]
    col_w   = [360, 470, 430, 380]

    rows = [
        ("Coste/mes",   "0,80 EUR",     ">300 EUR",    "~120 EUR"),
        ("Hardware",    "Ninguno",       "Bascula+cam",  "Ninguno"),
        ("Precision",   "100%",          "N/D",          "16,7%"),
        ("Autonomia",   "Si  (24/7)",    "Parcial",      "No"),
        ("Multi-agente","12 agentes",    "No",           "No"),
        ("CSRD 2026",   "Incorporado",   "No",           "No"),
    ]

    # Header row
    a_h = fade_alpha(0.6, t, 0.5)
    ov_h = Image.new("RGBA",(W,H),(0,0,0,0))
    ohd = ImageDraw.Draw(ov_h)
    for ci, (hdr, cx, cw) in enumerate(zip(headers, col_x, col_w)):
        if ci == 0: continue
        bg = (*GREEN, int(60*a_h)) if ci==1 else (*(40,50,65), int(80*a_h))
        ohd.rounded_rectangle([cx, H//2-370, cx+cw, H//2-330], radius=6, fill=bg)
        fc = (*GREEN,int(220*a_h)) if ci==1 else (*GRAY2,int(200*a_h))
        f_h = font(18, True)
        ohd.text((cx+(cw-tw(ohd,hdr,f_h))//2, H//2-363), hdr, fill=fc, font=f_h)
    img = Image.alpha_composite(img, ov_h)

    # Data rows
    for ri, (label, *vals) in enumerate(rows):
        a_r = fade_alpha(0.9 + ri*0.22, t, 0.45)
        ov_r = Image.new("RGBA",(W,H),(0,0,0,0))
        ord_ = ImageDraw.Draw(ov_r)
        row_y = H//2 - 310 + ri * 96

        for ci, (val, cx, cw) in enumerate(zip([label]+vals, col_x, col_w)):
            if ci == 0:
                ord_.text((cx+8, row_y+12), val,
                           fill=(*GRAY2, int(200*a_r)), font=font(17))
                continue
            bg = (*GDARK, int(50*a_r)) if ci==1 else (*(18,24,36), int(40*a_r))
            ord_.rounded_rectangle([cx+4, row_y, cx+cw-4, row_y+72],
                                    radius=6, fill=bg)
            tc = (*GREEN, int(220*a_r)) if ci==1 else (*GRAY3, int(160*a_r))
            if ci == 1: tc = (*GREEN, int(220*a_r))
            elif ci == 2 and val not in ("N/D","Parcial","No","Bascula+cam"): tc = (*GRAY2,int(180*a_r))
            else: tc = (*GRAY3, int(160*a_r))
            f_v = font(17, ci==1)
            ord_.text((cx+(cw-tw(ord_,val,f_v))//2, row_y+26), val, fill=tc, font=f_v)
        img = Image.alpha_composite(img, ov_r)

    fade = fade_alpha(0, t, 0.35)
    return apply_fade_to_black(img, fade)


def s_close(t, dur):
    """Final close. Black. MermaOps. Fade out."""
    img = base_frame()
    fade_out = max(0.0, 1.0 - (t-(dur-2.0))/2.0) if t > dur-2.0 else 1.0
    img = draw_particles(img, t, 0.20 * fade_out)

    glow_pulse = 0.15 + 0.08*math.sin(t*1.2)
    img = radial_glow(img, W//2, H//2, int(300+40*math.sin(t*0.8)), GREEN,
                      glow_pulse * fade_out)

    a_name = eoc(clamp(t/0.9, 0, 1)) * fade_out
    if a_name > 0:
        img = center_text_glow(img, "MermaOps", H//2 - 100,
                                104, GREEN, GLIGHT, bold=True, glow_r=60,
                                alpha=a_name)

    d = ImageDraw.Draw(img)
    a_line = eoc(clamp((t-0.8)/0.6, 0, 1)) * fade_out
    slide_line(d, H//2 + 28, a_line)

    texts = [
        ("@ChuwiMermaOpsBot", H//2+64,  26, GRAY2, 1.4),
        ("0,80 EUR/mes  ·  12 agentes  ·  774 tests  ·  100% precision",
                             H//2+110, 18, GRAY3, 2.2),
        ("Alvaro Ferrer Muro  ·  EVOLVE Madrid 2026",
                             H//2+150, 17, GRAY3, 2.9),
    ]
    for text, y, size, col, start in texts:
        a = eoc(clamp((t-start)/0.6,0,1)) * fade_out
        center_text(img, d, text, y, size, col, alpha=a,
                    float_off=float_y(0, clamp((t-start)/0.6,0,1)))

    return apply_fade_to_black(img, fade_out)


# ══════════════════════════════════════════════════════════════════════════
# MUSIC — cinematic Am progression with piano-like attack
# ══════════════════════════════════════════════════════════════════════════
def gen_music(duration_s, path):
    n   = int(SR * duration_s)
    t   = np.linspace(0, duration_s, n, endpoint=False)
    sig = np.zeros(n, dtype=np.float64)

    # Bass (A1=55Hz, E2=82Hz alternating)
    bass_freq = np.where(t % 16 < 8, 55.0, 82.41)
    sig += 0.22 * np.sin(2*np.pi*bass_freq*t)
    sig += 0.08 * np.sin(2*np.pi*bass_freq*2*t)  # octave

    # Chord progression: Am(8s) - F(8s) - C(8s) - G(8s) looping
    chord_notes = {
        "Am": [220.0, 261.63, 329.63, 440.0],
        "F":  [174.61, 220.0, 261.63, 349.23],
        "C":  [261.63, 329.63, 392.0, 523.25],
        "G":  [196.0, 246.94, 293.66, 392.0],
    }
    progression = ["Am","F","C","G"]
    chord_dur = 8.0

    for ci in range(int(duration_s // chord_dur) + 2):
        chord = progression[ci % 4]
        t0 = ci * chord_dur
        t1 = min(t0 + chord_dur, duration_s)
        i0, i1 = int(t0*SR), int(t1*SR)
        if i0 >= n: break
        i1 = min(i1, n)
        chunk = i1 - i0
        tc = np.arange(chunk) / SR

        # ADSR per chord
        att = int(0.08*SR); dec = int(0.4*SR); rel = int(2.5*SR)
        env = np.ones(chunk)
        env[:min(att,chunk)] = np.linspace(0,1,min(att,chunk))
        if att < chunk:
            end_dec = min(att+dec, chunk)
            env[att:end_dec] = np.linspace(1, 0.65, end_dec-att)
        if chunk > rel:
            env[-rel:] *= np.linspace(1, 0, rel)

        pad = np.zeros(chunk)
        for freq in chord_notes[chord]:
            pad += 0.14 * np.sin(2*np.pi*freq*tc)
            pad += 0.05 * np.sin(2*np.pi*freq*2*tc) * 0.5  # 2nd harmonic
            pad += 0.025 * np.sin(2*np.pi*freq*1.004*tc)    # slight detune
        sig[i0:i1] += pad * env

    # Piano-ish melody: arpeggiate Am scale
    melody_notes = [440.0, 523.25, 587.33, 659.25, 783.99, 880.0,
                    659.25, 523.25, 440.0, 392.0, 349.23, 329.63]
    note_dur = 0.75
    for ni, mfreq in enumerate(melody_notes * (int(duration_s//(len(melody_notes)*note_dur))+2)):
        mt0 = ni * note_dur
        if mt0 >= duration_s: break
        mt1 = min(mt0 + note_dur, duration_s)
        mi0, mi1 = int(mt0*SR), int(mt1*SR)
        if mi0 >= n: break
        mc = mi1 - mi0
        tc_m = np.arange(mc)/SR
        # Piano-like: fast attack, exponential decay
        env_m = np.exp(-tc_m * 4.0)
        env_m[:int(0.012*SR)] = np.linspace(0, 1, int(0.012*SR))
        sig[mi0:mi1] += 0.07 * np.sin(2*np.pi*mfreq*tc_m) * env_m

    # Slow LFO breath
    lfo = 0.82 + 0.18 * np.sin(2*np.pi*0.07*t)
    sig *= lfo

    # Shimmer overtone
    sig += 0.025 * np.sin(2*np.pi*2093.0*t) * (0.5+0.5*np.sin(2*np.pi*0.3*t))

    # Fade in/out
    fi, fo = int(3.5*SR), int(5.0*SR)
    sig[:fi] *= np.linspace(0,1,fi)
    sig[-fo:] *= np.linspace(1,0,fo)

    # Normalise
    peak = np.max(np.abs(sig)) or 1.0
    pcm = (sig / peak * 27000).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ══════════════════════════════════════════════════════════════════════════
# SCHEDULE
# ══════════════════════════════════════════════════════════════════════════
SLIDES = [
    (s_intro,          8),
    (s_problem,        9),
    (s_winnow,         9),
    (s_reveal,         9),
    (s_telegram,      12),
    (s_kuine_terminal,11),
    (s_agents,        10),
    (s_metrics,       13),
    (s_compare,       10),
    (s_close,         10),
]
TOTAL = sum(d for _, d in SLIDES)
_ST = []
_s = 0.0
for _, d in SLIDES:
    _ST.append(_s); _s += d


def make_frame(t):
    idx = max(i for i,s in enumerate(_ST) if t >= s)
    fn, dur = SLIDES[idx]
    local_t = t - _ST[idx]
    return np.array(fn(local_t, dur).convert("RGB"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"\nMermaOps Master Video — {W}x{H} {FPS}fps {TOTAL}s")
    print(f"  Output: {OUT}\n")

    mpath = str(ROOT/"docs"/"_m.wav")
    print("  [1/3] Generando musica cinematica (piano + pad Am-F-C-G)...")
    gen_music(TOTAL+3, mpath)
    print("        OK\n")

    from moviepy import VideoClip, AudioFileClip
    print("  [2/3] Renderizando...")
    clip = VideoClip(make_frame, duration=TOTAL).with_fps(FPS)

    print("  [3/3] Codificando video (calidad alta)...")
    audio = AudioFileClip(mpath).subclipped(0, TOTAL)
    clip = clip.with_audio(audio)
    clip.write_videofile(
        str(OUT), fps=FPS, codec="libx264", audio_codec="aac",
        bitrate="6000k", logger="bar",
        ffmpeg_params=["-pix_fmt","yuv420p","-crf","16","-preset","slow"],
    )
    try: os.remove(mpath)
    except: pass

    sz = OUT.stat().st_size/1_048_576
    print(f"\n  Listo: {OUT}")
    print(f"  Duracion: {TOTAL}s · Tamano: {sz:.1f}MB")
