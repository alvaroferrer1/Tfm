"""
gen_video.py — Genera el vídeo de presentación de MermaOps.

Produce: docs/MermaOps_Video_Presentacion.mp4  (2 min, 1920×1080, 30fps)
Con música de fondo generada (sine wave ambient, no copyright).

Uso:
    python scripts/gen_video.py
    make video
"""
from __future__ import annotations
import os, sys, math, struct, wave, tempfile
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent.parent
OUT  = ROOT / "docs" / "MermaOps_Video_Presentacion.mp4"

W, H = 1920, 1080
FPS  = 30

# ── Paleta ───────────────────────────────────────────────────────────────────
BG    = (15, 23, 42)       # #0F172A
GREEN = (16, 185, 129)     # #10B981
GLOW  = (6,  78,  59)      # fondo verde oscuro
WHITE = (255, 255, 255)
GRAY  = (156, 163, 175)    # #9CA3AF
LGRAY = (243, 244, 246)
DARK  = (17, 24, 39)
RED   = (239, 68, 68)
ORANGE= (249, 115, 22)
YLLOW = (234, 179, 8)
BLUE  = (59, 130, 246)


def _font(size: int, bold: bool = False):
    for name in (
        "arialbd.ttf" if bold else "arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _text_center(draw, text, y, size, color=WHITE, bold=False):
    f = _font(size, bold)
    bbox = draw.textbbox((0, 0), text, font=f)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, y), text, fill=color, font=f)


def _text_left(draw, text, x, y, size, color=WHITE, bold=False):
    draw.text((x, y), text, fill=color, font=_font(size, bold))


def _rect(draw, x, y, w, h, color, radius=12):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=radius, fill=color)


def _pill(draw, x, y, w, h, color, text, tsize=18, tcol=WHITE):
    _rect(draw, x, y, w, h, color, radius=h//2)
    f = _font(tsize, bold=True)
    bbox = draw.textbbox((0, 0), text, font=f)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((x + (w - tw)//2, y + (h - th)//2 - 2), text, fill=tcol, font=f)


def _progress_bar(draw, progress: float):
    bh = 6
    _rect(draw, 0, H - bh, W, bh, (30, 41, 59), radius=0)
    if progress > 0:
        _rect(draw, 0, H - bh, int(W * progress), bh, GREEN, radius=0)


def _base(progress: float = 0) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    # Subtle grid
    for xi in range(0, W, 80):
        draw.line([(xi, 0), (xi, H)], fill=(20, 32, 52), width=1)
    for yi in range(0, H, 80):
        draw.line([(0, yi), (W, yi)], fill=(20, 32, 52), width=1)
    _progress_bar(draw, progress)
    return img, draw


def _alpha_blend(img: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 1.0:
        return img
    overlay = Image.new("RGB", (W, H), BG)
    return Image.blend(img, overlay, 1.0 - alpha)


# ── Generador de música ambient ──────────────────────────────────────────────
def _gen_music(duration_s: float, outpath: str):
    sr = 44100
    n  = int(sr * duration_s)
    t  = np.linspace(0, duration_s, n, endpoint=False)

    # Acorde Am suave: A2 + C3 + E3 + A3 con envolvente lenta
    freqs   = [110.0, 130.81, 164.81, 220.0, 261.63, 329.63]
    weights = [0.35,  0.20,   0.25,   0.25,  0.15,   0.20]
    wave_arr = np.zeros(n)
    for f, w in zip(freqs, weights):
        wave_arr += w * np.sin(2 * math.pi * f * t)

    # LFO tremolo suave a 0.12 Hz
    lfo = 0.75 + 0.25 * np.sin(2 * math.pi * 0.12 * t)
    wave_arr *= lfo

    # Fade in/out 3s
    fade = int(sr * 3)
    wave_arr[:fade] *= np.linspace(0, 1, fade)
    wave_arr[-fade:] *= np.linspace(1, 0, fade)

    # Normalizar y convertir a int16
    peak = np.max(np.abs(wave_arr)) or 1
    pcm  = (wave_arr / peak * 28000).astype(np.int16)

    with wave.open(outpath, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


# ── Slides ────────────────────────────────────────────────────────────────────

def slide_01(t: float, dur: float) -> Image.Image:
    """Title."""
    a = min(1.0, t / 0.8)
    img, draw = _base(t / dur)

    # Green glow circle
    r = int(300 + 20 * math.sin(t * 1.5))
    cx, cy = W // 2, H // 2 - 80
    for ri in range(r, 0, -20):
        alpha = int(40 * (ri / r))
        draw.ellipse([cx-ri, cy-ri, cx+ri, cy+ri],
                     fill=tuple(max(0, c - 200 + alpha) for c in GLOW))

    _pill(draw, W//2-120, 160, 240, 36, (6, 78, 59), "MÁSTER IA GENERATIVA 2026", 14, GREEN)
    _text_center(draw, "MermaOps", H//2 - 120, 96, WHITE, bold=True)
    _text_center(draw, "Sistema Multi-Agente de IA", H//2 + 10, 32, GREEN)
    _text_center(draw, "para Reducción de Merma Alimentaria", H//2 + 52, 32, GREEN)
    _text_center(draw, "en Supermercados Españoles", H//2 + 94, 28, GRAY)
    _text_center(draw, "Álvaro Ferrer Muro  ·  EVOLVE Madrid 2026", H - 120, 20, GRAY)
    return _alpha_blend(img, a)


def slide_02(t: float, dur: float) -> Image.Image:
    """El problema."""
    a = min(1.0, t / 0.6)
    img, draw = _base(t / dur)
    _text_center(draw, "El Problema", 80, 52, WHITE, bold=True)
    draw.line([(W//2 - 200, 152), (W//2 + 200, 152)], fill=GREEN, width=3)

    stats = [
        ("10,4 kg",  "por persona y año\nse desperdician en España", RED),
        ("2–5%",     "de ingresos anuales\nperdidos por supermercado", ORANGE),
        (">20.000€", "coste de soluciones\nexistentes (Winnow, Orbisk)", YLLOW),
    ]
    for i, (val, label, col) in enumerate(stats):
        x = 200 + i * 510
        _rect(draw, x, 200, 460, 300, (20, 30, 48), radius=16)
        draw.rounded_rectangle([x, 200, x+460, 200+300], radius=16,
                                outline=col, width=2)
        _text_center_in(draw, val,   x, 200, 460, 130, 56, col, bold=True)
        _text_center_in(draw, label, x, 340, 460, 100, 18, GRAY)

    _text_center(draw, "La gestión actual: Excel desconectado · Inspección manual · Sin datos reales",
                 650, 20, GRAY)
    return _alpha_blend(img, a)


def _text_center_in(draw, text, bx, by, bw, bh, size, color, bold=False):
    """Center text within a bounding box."""
    lines = text.split("\n")
    f = _font(size, bold)
    total_h = sum(draw.textbbox((0,0), l, font=f)[3] - draw.textbbox((0,0), l, font=f)[1]
                  for l in lines) + (len(lines)-1) * 6
    y = by + (bh - total_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=f)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((bx + (bw - tw) // 2, y), line, fill=color, font=f)
        y += th + 6


def slide_03(t: float, dur: float) -> Image.Image:
    """La solución."""
    a = min(1.0, t / 0.6)
    img, draw = _base(t / dur)
    _text_center(draw, "La Solución", 80, 52, WHITE, bold=True)
    draw.line([(W//2 - 200, 152), (W//2 + 200, 152)], fill=GREEN, width=3)

    _pill(draw, W//2-80, 185, 160, 42, GREEN, "0,80 €/mes", 22, DARK)
    _text_center(draw, "Sin hardware adicional  ·  Sin instalación  ·  Sin formación", 260, 24, GRAY)

    channels = [
        ("Telegram", "@ChuwiMermaOpsBot", "Agente conversacional\nstreaming en tiempo real\nmonitoreo 24/7"),
        ("Flutter",  "App Web + Móvil",   "Dashboard KPIs\nGestión de acciones\nPanel de agentes"),
    ]
    for i, (title, sub, desc) in enumerate(channels):
        x = 280 + i * 720
        _rect(draw, x, 320, 640, 380, (20, 30, 48), radius=16)
        draw.rounded_rectangle([x, 320, x+640, 320+380], radius=16, outline=GREEN, width=2)
        _text_center_in(draw, title, x, 320, 640, 80,  36, GREEN, bold=True)
        _text_center_in(draw, sub,   x, 400, 640, 50,  18, GRAY)
        _text_center_in(draw, desc,  x, 460, 640, 180, 20, WHITE)

    _text_center(draw, "\"El encargado ya tiene Telegram. Sin apps nuevas. Sin fricción.\"",
                 780, 22, GREEN)
    return _alpha_blend(img, a)


def slide_04(t: float, dur: float) -> Image.Image:
    """12 agentes."""
    a = min(1.0, t / 0.6)
    img, draw = _base(t / dur)
    _text_center(draw, "Arquitectura — 12 Agentes Especializados", 70, 44, WHITE, bold=True)
    draw.line([(W//2 - 280, 130), (W//2 + 280, 130)], fill=GREEN, width=3)

    # Kuine top
    show_kuine = t > 0.5
    if show_kuine:
        _rect(draw, W//2-200, 155, 400, 70, GREEN, radius=12)
        _text_center_in(draw, "KUINE", W//2-200, 155, 400, 35, 28, DARK, bold=True)
        _text_center_in(draw, "Opus 4.7  ·  Orquestador  ·  20 iter  ·  16 tools",
                        W//2-200, 190, 400, 35, 14, DARK)

    agents = [
        ("Evaluador",  "Sonnet 4.6", "Score 0–100\next. thinking", GREEN),
        ("ForkMerge",  "3×Sonnet",   "Fork-merge\ncasos críticos", BLUE),
        ("Consenso",   "3×Sonnet",   "Regla 2/3\nparalelo", (139, 92, 246)),
        ("Validador",  "Sonnet 4.6", "23 ataques\nadversariales", RED),
        ("Chuwi",      "Sonnet 4.6", "Telegram\nstreaming", GREEN),
        ("Predictor",  "Haiku 4.5",  "7 días\nOpen-Meteo", YLLOW),
        ("Visión",     "Haiku 4.5",  "Fotos\nbase64", ORANGE),
        ("Precio",     "Heurístico", "0 tokens\ndescuentos", GRAY),
    ]
    cols = 4
    for i, (name, model, role, col) in enumerate(agents):
        progress = (t - 0.5) / (dur - 0.5)
        if progress < i / len(agents):
            continue
        row, col_i = divmod(i, cols)
        x = 80 + col_i * 450
        y = 280 + row * 200
        _rect(draw, x, y, 400, 160, (20, 30, 48), radius=10)
        draw.rounded_rectangle([x, y, x+400, y+160], radius=10, outline=col, width=2)
        _text_center_in(draw, name,  x, y,     400, 55, 22, col,  bold=True)
        _text_center_in(draw, model, x, y+55,  400, 35, 14, GRAY)
        _text_center_in(draw, role,  x, y+90,  400, 60, 16, WHITE)

    return _alpha_blend(img, a)


def slide_05(t: float, dur: float) -> Image.Image:
    """Extended thinking + score bar."""
    a = min(1.0, t / 0.6)
    img, draw = _base(t / dur)
    _text_center(draw, "Extended Thinking Adaptativo", 80, 48, WHITE, bold=True)
    draw.line([(W//2 - 250, 145), (W//2 + 250, 145)], fill=GREEN, width=3)

    _text_center(draw, "El Evaluador razona antes de decidir — solo cuando hace falta", 185, 24, GRAY)

    # Score bar animada
    score = min(77, int(77 * min(1.0, (t - 0.3) / (dur * 0.6))))
    bar_x, bar_y = 300, 280
    bar_w, bar_h = W - 600, 60

    # Fondo
    _rect(draw, bar_x, bar_y, bar_w, bar_h, (30, 41, 59), radius=30)

    # Zonas coloreadas
    zones = [(25, (34, 197, 94)), (40, YLLOW), (25, ORANGE), (10, RED)]
    cx = bar_x
    for pct, col in zones:
        zw = int(bar_w * pct / 100)
        draw.rounded_rectangle([cx, bar_y, cx+zw, bar_y+bar_h], radius=0, fill=col)
        cx += zw

    # Cursor
    cursor_x = bar_x + int(bar_w * score / 100)
    draw.ellipse([cursor_x-18, bar_y-18, cursor_x+18, bar_y+bar_h+18],
                 fill=WHITE, outline=DARK, width=3)
    _text_center_in(draw, str(score), cursor_x-18, bar_y-18, 36, bar_h+36, 18, DARK, bold=True)

    labels = [("0", bar_x), ("BAJO", bar_x + bar_w*12//100),
              ("MEDIO", bar_x + bar_w*45//100), ("ALTO", bar_x + bar_w*70//100),
              ("CRÍTICO", bar_x + bar_w*90//100), ("100", bar_x + bar_w - 10)]
    for lbl, lx in labels:
        _text_left(draw, lbl, lx, bar_y + bar_h + 20, 16, GRAY)

    _text_center(draw, "Thinking budget dinámico: máximo en zona 65–90 (ambigüedad)",
                 420, 22, GRAY)
    _text_center(draw, "Sin thinking en casos obvios  →  ahorro del 60% en tokens", 460, 22, GRAY)

    rows = [
        ("Score < 30 (BAJO)",    "Sin thinking",       "0 tokens extra",  "#22C55E"),
        ("Score 30–64 (MEDIO)",  "Sin thinking",       "0 tokens extra",  "#EAB308"),
        ("Score 65–89 (ALTO)",   "Thinking 4.000 tok", "Razonamiento profundo", "#F97316"),
        ("Score 90+ (CRÍTICO)",  "Thinking 8.000 tok", "Máximo análisis",  "#EF4444"),
    ]
    for i, (rng, think, result, col) in enumerate(rows):
        y = 540 + i * 80
        _rect(draw, 200, y, 1520, 65, (20, 30, 48), radius=8)
        _text_left(draw, rng,    220, y+20, 18, HexColor_to_rgb(col))
        _text_left(draw, think,  680, y+20, 18, WHITE)
        _text_left(draw, result, 1100, y+20, 18, GRAY)
    return _alpha_blend(img, a)


def HexColor_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def slide_06(t: float, dur: float) -> Image.Image:
    """Validador adversarial."""
    a = min(1.0, t / 0.6)
    img, draw = _base(t / dur)
    _text_center(draw, "Validador — Seguridad Adversarial", 80, 48, WHITE, bold=True)
    draw.line([(W//2 - 250, 145), (W//2 + 250, 145)], fill=RED, width=3)

    _pill(draw, W//2-140, 180, 280, 50, RED, "23/23 ataques bloqueados", 20, WHITE)

    attacks = [
        "Prompt injection / manipulación del LLM",
        "Precio por debajo del coste (venta a pérdida)",
        "Fecha de caducidad falsificada en el input",
        "Entidad de donación no verificada o inventada",
        "Violación de FEFO (First Expired First Out)",
        "Bypass de confirmación humana",
    ]
    for i, atk in enumerate(attacks):
        progress = (t - 0.3) / (dur * 0.7)
        if progress < i / len(attacks):
            continue
        y = 290 + i * 95
        _rect(draw, 200, y, 1520, 72, (30, 20, 20), radius=10)
        draw.rounded_rectangle([200, y, 1720, y+72], radius=10, outline=(100, 30, 30), width=1)
        # Check mark
        _rect(draw, 210, y+15, 42, 42, (34, 197, 94), radius=21)
        _text_left(draw, "✓", 222, y+18, 22, DARK, bold=True)
        _text_left(draw, atk, 280, y+22, 20, WHITE)

    _text_center(draw, "El Validador verifica ANTES de ejecutar cualquier acción en el mundo real",
                 940, 22, GRAY)
    return _alpha_blend(img, a)


def slide_07(t: float, dur: float) -> Image.Image:
    """Telegram Chuwi."""
    a = min(1.0, t / 0.6)
    img, draw = _base(t / dur)
    _text_center(draw, "Chuwi — Agente Conversacional en Telegram", 80, 44, WHITE, bold=True)
    draw.line([(W//2 - 280, 142), (W//2 + 280, 142)], fill=GREEN, width=3)

    # Telegram mock
    mx, my, mw, mh = W//2 - 380, 175, 760, 560
    _rect(draw, mx, my, mw, mh, (17, 27, 39), radius=20)
    draw.rounded_rectangle([mx, my, mx+mw, my+mh], radius=20,
                            outline=(40, 60, 80), width=2)

    # Header
    _rect(draw, mx, my, mw, 65, (22, 35, 52), radius=20)
    _text_left(draw, "@ChuwiMermaOpsBot", mx+80, my+20, 20, WHITE, bold=True)
    _text_left(draw, "en linea", mx+80, my+44, 14, GREEN)

    # Mensajes
    msgs = [
        (True,  "¿Qué productos son críticos ahora?",         0.3, 0.0),
        (False, "🔴 Yogur Danone x4  —  REBAJA HOY\n"
                "   Caducidad: 2 días  |  Score: 87/100\n"
                "   Precio actual 1,89€  →  Recomiendo 0,95€", 0.5, 0.3),
        (True,  "¿Cuánto ahorramos esta semana?",              0.75, 0.55),
        (False, "Esta semana: 483€ de merma evitada\n"
                "4 donaciones registradas (69,40€ deducción)\n"
                "ROI vs coste sistema: >500:1",                1.0, 0.78),
    ]
    y_off = 100
    for is_user, text, show_at, _ in msgs:
        if t / dur < show_at:
            break
        lines = text.split("\n")
        max_w  = int(mw * 0.65)
        bh     = 30 + len(lines) * 28
        bx     = mx + mw - max_w - 20 if is_user else mx + 20
        by     = my + y_off
        bcol   = (36, 117, 221) if is_user else (30, 45, 65)
        tcol   = WHITE
        _rect(draw, bx, by, max_w, bh, bcol, radius=14)
        for li, line in enumerate(lines):
            _text_left(draw, line, bx+12, by+12+li*26, 16, tcol)
        y_off += bh + 16

    _text_center(draw, "Streaming progresivo real  ·  Clasificación de intent 0 tokens  ·  Monitoreo cada 30 min",
                 800, 20, GRAY)
    return _alpha_blend(img, a)


def slide_08(t: float, dur: float) -> Image.Image:
    """Métricas reales."""
    a = min(1.0, t / 0.6)
    img, draw = _base(t / dur)
    _text_center(draw, "Datos Reales — Verificables en Supabase", 80, 48, WHITE, bold=True)
    draw.line([(W//2 - 260, 145), (W//2 + 260, 145)], fill=GREEN, width=3)

    prog = min(1.0, max(0.0, (t - 0.4) / (dur * 0.6)))
    metrics = [
        (774,   "Tests automatizados\n1,98s sin API real",   GREEN,  "#10B981"),
        (100,   "% Precisión\n+83pp vs. baseline 16,7%",    GREEN,  "#10B981"),
        (23,    "Ataques bloqueados\n23/23 adversarial",    RED,    "#EF4444"),
        (45,    "Acciones completadas\ndatos reales BD",    BLUE,   "#3B82F6"),
        (483,   "€ Merma identificada\nvalor real Supabase",ORANGE, "#F97316"),
        (7,     "Briefs generados\npor Kuine autónomo",     (139,92,246), "#8B5CF6"),
    ]
    for i, (val, label, col, hx) in enumerate(metrics):
        row, ci = divmod(i, 3)
        x = 150 + ci * 560
        y = 200 + row * 290
        _rect(draw, x, y, 500, 240, (20, 30, 48), radius=16)
        draw.rounded_rectangle([x, y, x+500, y+240], radius=16, outline=col, width=2)
        shown = int(val * prog)
        suffix = "%" if val == 100 else ("€" if val == 483 else "")
        _text_center_in(draw, f"{shown}{suffix}", x, y+10, 500, 130, 64, col, bold=True)
        _text_center_in(draw, label, x, y+140, 500, 90, 18, GRAY)

    return _alpha_blend(img, a)


def slide_09(t: float, dur: float) -> Image.Image:
    """Comparativa."""
    a = min(1.0, t / 0.6)
    img, draw = _base(t / dur)
    _text_center(draw, "Comparativa con Soluciones Existentes", 80, 48, WHITE, bold=True)
    draw.line([(W//2 - 260, 145), (W//2 + 260, 145)], fill=GREEN, width=3)

    headers = ["Criterio", "MermaOps", "Winnow V2", "Baseline"]
    col_w   = [500, 380, 380, 280]
    header_colors = [BG, GREEN, (30, 50, 80), (40, 40, 40)]
    rows_data = [
        ["Coste/mes",   "0,80 €",          ">300 €",       "~120 €"],
        ["Hardware",    "Ninguno",          "Báscula+cam",  "Ninguno"],
        ["Precisión",   "100% (tests)",     "N/D público",  "16,7%"],
        ["Autonomía",   "Sí (24/7)",        "Parcial",      "No"],
        ["CSRD 2026",   "Incorporado",      "No",           "No"],
        ["Multi-agente","12 agentes",       "No",           "No"],
    ]

    # Headers
    hx = 80
    for hi, (hdr, cw, hcol) in enumerate(zip(headers, col_w, header_colors)):
        bcol = hcol if hi == 1 else (25, 35, 55)
        _rect(draw, hx, 200, cw - 8, 60, bcol, radius=6)
        _text_center_in(draw, hdr, hx, 200, cw-8, 60, 20, WHITE, bold=True)
        hx += cw

    for ri, row in enumerate(rows_data):
        rx = 80
        for ci, (cell, cw) in enumerate(zip(row, col_w)):
            y = 275 + ri * 90
            bcol = (16, 40, 30) if ci == 1 else ((22, 32, 50) if ri % 2 == 0 else (18, 26, 42))
            tcol = GREEN if ci == 1 else (WHITE if ci == 0 else GRAY)
            _rect(draw, rx, y, cw - 8, 72, bcol, radius=6)
            _text_center_in(draw, cell, rx, y, cw-8, 72, 18, tcol, bold=(ci==1))
            rx += cw

    return _alpha_blend(img, a)


def slide_10(t: float, dur: float) -> Image.Image:
    """Tests terminal."""
    a = min(1.0, t / 0.6)
    img, draw = _base(t / dur)
    _text_center(draw, "Calidad — 774 Tests Automatizados", 80, 48, WHITE, bold=True)
    draw.line([(W//2 - 240, 145), (W//2 + 240, 145)], fill=GREEN, width=3)

    # Terminal window
    tx, ty, tw, th = 300, 185, 1320, 580
    _rect(draw, tx, ty, tw, th, (10, 15, 25), radius=14)
    draw.rounded_rectangle([tx, ty, tx+tw, ty+th], radius=14,
                            outline=(40, 60, 80), width=2)
    # Traffic lights
    for xi, col in [(tx+20, (239,68,68)), (tx+50, (234,179,8)), (tx+80, (34,197,94))]:
        draw.ellipse([xi, ty+18, xi+22, ty+40], fill=col)

    # Terminal text — animated
    lines = [
        ("$ python -m pytest backend/tests/ -q", WHITE, 0.0),
        ("", WHITE, 0.2),
        ("backend/tests/test_consensus_rule.py ............ [  5%]", GRAY, 0.25),
        ("backend/tests/test_evaluator.py ................. [ 17%]", GRAY, 0.30),
        ("backend/tests/test_validator.py ................. [ 23%]", GRAY, 0.35),
        ("backend/tests/test_chuwi_agent.py .............. [ 31%]", GRAY, 0.40),
        ("backend/tests/test_supervisor_unit.py .......... [ 62%]", GRAY, 0.50),
        ("backend/tests/test_database_functions.py ....... [ 87%]", GRAY, 0.62),
        ("backend/tests/test_api_endpoints.py ........... [100%]", GRAY, 0.72),
        ("", WHITE, 0.80),
        ("====== 774 passed in 1.98s ======", GREEN, 0.85),
    ]
    for li, (line_text, col, show_at) in enumerate(lines):
        if t / dur < show_at:
            break
        _text_left(draw, line_text, tx+24, ty+62+li*42, 18,
                   col if line_text else WHITE,
                   bold=("774 passed" in line_text))

    # Stats below
    stats2 = [("29", "archivos de test"), ("77", "módulos Python"),
              ("15.675", "líneas de código"), ("2,0s", "tiempo de ejecución")]
    for i, (v, l) in enumerate(stats2):
        x = 300 + i * 340
        _text_center_in(draw, v, x, 810, 300, 60, 36, GREEN, bold=True)
        _text_center_in(draw, l, x, 865, 300, 40, 16, GRAY)
    return _alpha_blend(img, a)


def slide_11(t: float, dur: float) -> Image.Image:
    """Right-sizing."""
    a = min(1.0, t / 0.6)
    img, draw = _base(t / dur)
    _text_center(draw, "Right-Sizing — El Modelo Correcto para Cada Tarea", 80, 44, WHITE, bold=True)
    draw.line([(W//2 - 300, 142), (W//2 + 300, 142)], fill=GREEN, width=3)

    tiers = [
        ("Opus 4.7",     "Orquestación compleja\n20 iter · 16 tools · Adaptive thinking",
         "15 $/M tokens", (234,179,8), 1),
        ("Sonnet 4.6",   "Razonamiento avanzado\nEvaluador · Consenso · Chuwi · Validador",
         "3 $/M tokens",  BLUE,      7),
        ("Haiku 4.5",    "Tareas simples y rápidas\nPredictor · Visión",
         "0,80 $/M tokens", GREEN,   2),
        ("Heurístico",   "Cálculos deterministas\nPrecio · Stock · 0 llamadas API",
         "0 $ (sin LLM)", GRAY,     2),
    ]
    for i, (model, role, cost, col, agents_n) in enumerate(tiers):
        y = 190 + i * 175
        width = int((W - 400) * (0.25 + 0.2 * (3 - i) / 3))
        _rect(draw, 200, y, width, 145, (20, 30, 48), radius=10)
        draw.rounded_rectangle([200, y, 200+width, y+145], radius=10, outline=col, width=2)
        _text_left(draw, model, 225, y+18, 26, col, bold=True)
        for li, line in enumerate(role.split("\n")):
            _text_left(draw, line, 225, y+55+li*28, 17, WHITE)
        _pill(draw, 225, y+108, 200, 28, (20, 40, 30), cost, 14, GREEN)
        _pill(draw, 445, y+108, 140, 28, (20, 30, 50),
              f"{agents_n} agente{'s' if agents_n>1 else ''}", 14, BLUE)

    _text_center(draw, "Ahorro estimado ~70% vs. usar Opus en todos los agentes",
                 910, 22, GREEN)
    return _alpha_blend(img, a)


def slide_12(t: float, dur: float) -> Image.Image:
    """Cierre."""
    a = min(1.0, t / 0.6)
    # Fade out en los últimos 2s
    if t > dur - 2.0:
        a = max(0.0, (dur - t) / 2.0)

    img, draw = _base(min(1.0, t / dur))
    cx = W // 2

    _text_center(draw, "MermaOps no es un prototipo de laboratorio.", 200, 36, GRAY)
    _text_center(draw, "Es un sistema operativo para la merma alimentaria:", 255, 36, WHITE)

    pillars = [("PERCIBE", "Datos reales\nde Supabase\nen tiempo real"),
               ("RAZONA",  "12 agentes Claude\norquestados por Kuine\nextended thinking"),
               ("ACTÚA",   "Telegram + Flutter\nconfirmación humana\ntrazabilidad total")]
    for i, (title, desc) in enumerate(pillars):
        x = 180 + i * 540
        _rect(draw, x, 340, 480, 320, (20, 30, 48), radius=16)
        draw.rounded_rectangle([x, 340, x+480, 340+320], radius=16, outline=GREEN, width=2)
        _text_center_in(draw, title, x, 340, 480, 80, 32, GREEN, bold=True)
        _text_center_in(draw, desc,  x, 420, 480, 200, 20, WHITE)

    _text_center(draw, "@ChuwiMermaOpsBot  ·  FastAPI :8001  ·  Flutter Web",
                 730, 20, GRAY)
    _text_center(draw, "Álvaro Ferrer Muro  ·  Máster IA Generativa & Innovation  ·  EVOLVE Madrid 2026",
                 780, 18, GRAY)

    _pill(draw, cx-120, 840, 240, 50, GREEN, "MermaOps 2026", 24, DARK)

    return _alpha_blend(img, a)


# ── Render engine ────────────────────────────────────────────────────────────
SLIDES = [
    (slide_01, 15),
    (slide_02, 10),
    (slide_03, 10),
    (slide_04, 15),
    (slide_05, 12),
    (slide_06, 10),
    (slide_07, 12),
    (slide_08, 12),
    (slide_09, 10),
    (slide_10, 12),
    (slide_11, 10),
    (slide_12, 12),
]
TOTAL_S = sum(d for _, d in SLIDES)


def make_frame(t: float) -> np.ndarray:
    elapsed = 0
    for slide_fn, dur in SLIDES:
        if t < elapsed + dur:
            local_t = t - elapsed
            img = slide_fn(local_t, dur)
            return np.array(img)
        elapsed += dur
    return np.array(slide_12(SLIDES[-1][1], SLIDES[-1][1]))


if __name__ == "__main__":
    print(f"\nGenerando video MermaOps ({TOTAL_S}s, {W}x{H}, {FPS}fps)...")
    print(f"  Destino: {OUT}\n")

    # Música ambient
    music_path = str(ROOT / "docs" / "_music_temp.wav")
    print("  Generando musica ambient...")
    _gen_music(TOTAL_S + 2, music_path)

    from moviepy import VideoClip, AudioFileClip, CompositeAudioClip
    from moviepy.audio.AudioClip import AudioArrayClip

    print("  Renderizando frames (puede tardar 2-3 min)...")
    clip = VideoClip(make_frame, duration=TOTAL_S)
    clip = clip.with_fps(FPS)

    audio = AudioFileClip(music_path).subclipped(0, TOTAL_S)
    audio = audio.with_effects([
        __import__("moviepy.audio.fx", fromlist=["AudioFadeIn"]).AudioFadeIn(2),
        __import__("moviepy.audio.fx", fromlist=["AudioFadeOut"]).AudioFadeOut(3),
    ])
    clip = clip.with_audio(audio)

    clip.write_videofile(
        str(OUT), fps=FPS, codec="libx264", audio_codec="aac",
        bitrate="4000k", logger="bar",
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )

    # Limpieza
    try: os.remove(music_path)
    except: pass

    print(f"\n  Video listo: {OUT}")
    print(f"  Duracion: {TOTAL_S}s  |  Resolucion: {W}x{H}  |  FPS: {FPS}")
