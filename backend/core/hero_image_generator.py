"""
hero_image_generator.py — Genera la hero image para el README de MermaOps.

Resultado: MermaOps_Hero.png (2400x1260px, fondo oscuro con mockups)

Uso:
    python -m backend.core.hero_image_generator
"""
from __future__ import annotations
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── Dimensiones ──────────────────────────────────────────────────────────────
W, H = 2400, 1260

# ── Paleta ───────────────────────────────────────────────────────────────────
BG          = (8, 12, 22)
BG2         = (13, 20, 36)
BG3         = (18, 28, 50)
GREEN_DARK  = (4, 80, 60)
GREEN_MID   = (6, 148, 100)
NEON        = (0, 230, 140)
NEON2       = (0, 255, 170)
WHITE       = (255, 255, 255)
OFF_WHITE   = (210, 225, 240)
GREY        = (130, 155, 185)
GREY2       = (70, 90, 115)
RED         = (220, 55, 55)
AMBER       = (230, 165, 30)
BLUE        = (50, 120, 245)
PURPLE      = (130, 55, 220)
TEAL        = (20, 190, 165)
PINK        = (220, 60, 140)

# ── Fuentes ──────────────────────────────────────────────────────────────────
_FONT_DIR = r"C:\Windows\Fonts"

def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    try:
        return ImageFont.truetype(f"{_FONT_DIR}\\{name}", size)
    except Exception:
        return ImageFont.load_default()

def _font_mono(size: int) -> ImageFont.FreeTypeFont:
    for name in ["consola.ttf", "cour.ttf", "lucon.ttf"]:
        try:
            return ImageFont.truetype(f"{_FONT_DIR}\\{name}", size)
        except Exception:
            continue
    return ImageFont.load_default()


# ── Helpers ───────────────────────────────────────────────────────────────────

def rrect(draw: ImageDraw.Draw, xy, radius: int, fill=None, outline=None, width=2):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

def circle(draw: ImageDraw.Draw, cx, cy, r, fill):
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)

def gradient_rect(img: Image.Image, x, y, w, h, c1, c2, vertical=True):
    """Degradado lineal pintado pixel a pixel en un sub-imagen."""
    grad = Image.new("RGB", (1 if vertical else w, h if vertical else 1))
    px = grad.load()
    steps = h if vertical else w
    for i in range(steps):
        t = i / max(steps - 1, 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        if vertical:
            px[0, i] = (r, g, b)
        else:
            px[i, 0] = (r, g, b)
    grad = grad.resize((w, h), Image.BILINEAR)
    img.paste(grad, (x, y))

def dot_grid(draw: ImageDraw.Draw, x, y, w, h, step, r, color):
    xi = x
    while xi < x + w:
        yi = y
        while yi < y + h:
            draw.ellipse((xi - r, yi - r, xi + r, yi + r), fill=color)
            yi += step
        xi += step

def glow_circle(img: Image.Image, cx, cy, r, color, alpha=80):
    """Circulo con efecto de brillo."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(4, 0, -1):
        ri = r + i * 8
        a = alpha // (i + 1)
        d.ellipse((cx - ri, cy - ri, cx + ri, cy + ri), fill=(*color, a))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*color, 200))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))

def text_centered(draw, text, x, y, w, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text((x + (w - tw) // 2, y), text, font=font, fill=fill)

def text_right(draw, text, rx, y, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text((rx - tw, y), text, font=font, fill=fill)


# ── Construccion de la imagen ─────────────────────────────────────────────────

def build() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ================================================================ FONDO ==
    # Dot grid sutil
    dot_grid(draw, 0, 0, W, H, 38, 1, (16, 26, 46))

    # Degradado lateral izquierdo
    gradient_rect(img, 0, 0, 420, H, (4, 55, 38), BG, vertical=False)

    # Anillos decorativos fondo (izquierda)
    for r in [280, 340, 400, 460]:
        draw.ellipse((60 - r, H // 2 - r, 60 + r, H // 2 + r),
                     outline=(*GREEN_DARK, 255), width=1)

    # Linea vertical separadora izquierda
    draw.rectangle((418, 0, 422, H), fill=NEON)

    # ============================================================= CABECERA ==
    # Banda top
    gradient_rect(img, 0, 0, W, 110, (4, 60, 44), BG, vertical=True)
    draw.rectangle((0, 108, W, 112), fill=NEON)

    # Logo MermaOps
    draw.text((44, 18), "MermaOps", font=_font(62, bold=True), fill=WHITE)

    # Punto neon bajo logo
    circle(draw, 44 + 4, 92, 5, NEON)
    draw.line((44, 96, 380, 96), fill=(*NEON, 180), width=2)

    # Subtitulo cabecera
    draw.text((44, 60), "Sistema multi-agente de IA para reduccion de merma alimentaria",
              font=_font(22), fill=(*GREEN_MID, 255))

    # Badges tecnologias (derecha de cabecera)
    badges = [
        ("Claude Opus 4.7", NEON, GREEN_DARK),
        ("FastAPI", BLUE, (10, 30, 80)),
        ("Flutter", PURPLE, (40, 15, 80)),
        ("Supabase", TEAL, (5, 50, 50)),
        ("Telegram Bot", GREEN_MID, GREEN_DARK),
    ]
    bx = W - 60
    for label, fg, bg in reversed(badges):
        bbox = draw.textbbox((0, 0), label, font=_font(20, bold=True))
        bw = bbox[2] - bbox[0] + 28
        bx -= bw + 10
        rrect(draw, (bx, 28, bx + bw, 78), radius=8, fill=bg, outline=fg, width=2)
        draw.text((bx + 14, 37), label, font=_font(20, bold=True), fill=fg)

    # =========================================================== PANEL IZQ ==
    # (azul oscuro — columna izquierda con stats)
    PANEL_LEFT_X = 0
    PANEL_LEFT_W = 418

    draw.text((26, 136), "Por que MermaOps", font=_font(28, bold=True), fill=NEON)
    draw.line((26, 172, 370, 172), fill=(*NEON, 80), width=1)

    stats = [
        ("10 kg",    "por habitante/anio\nde desperdicio en Espana", RED),
        ("2-5%",     "ingresos perdidos\npor merma en supermercados", AMBER),
        ("1/3",      "de toda la comida\nse desperdicia en el mundo", RED),
        ("0 EUR",    "coste extra con\nMermaOps activo", NEON),
    ]
    for i, (val, lbl, col) in enumerate(stats):
        sy = 190 + i * 250
        # caja
        rrect(draw, (18, sy, 400, sy + 220), radius=12, fill=BG2)
        draw.rectangle((18, sy, 26, sy + 220), fill=col)
        # valor
        draw.text((44, sy + 20), val, font=_font(64, bold=True), fill=col)
        # label
        for li, line in enumerate(lbl.split("\n")):
            draw.text((44, sy + 110 + li * 38), line, font=_font(22), fill=OFF_WHITE)

    # ============================================================ APP MOCKUP ==
    # Smartphone simulado (columna central-izquierda)
    PHONE_X, PHONE_Y = 448, 130
    PHONE_W, PHONE_H = 380, 1060

    # Cuerpo del telefono
    rrect(draw, (PHONE_X, PHONE_Y, PHONE_X + PHONE_W, PHONE_Y + PHONE_H),
          radius=36, fill=(20, 30, 50), outline=(40, 60, 90), width=3)

    # Notch
    rrect(draw, (PHONE_X + 140, PHONE_Y + 12, PHONE_X + 240, PHONE_Y + 36),
          radius=12, fill=BG)
    circle(draw, PHONE_X + 230, PHONE_Y + 24, 8, (30, 40, 60))

    # Pantalla interior
    screen_x = PHONE_X + 12
    screen_y = PHONE_Y + 44
    screen_w = PHONE_W - 24
    screen_h = PHONE_H - 56

    draw.rectangle((screen_x, screen_y, screen_x + screen_w, screen_y + screen_h),
                   fill=(10, 16, 30))

    # Status bar
    draw.text((screen_x + 14, screen_y + 8), "09:31", font=_font(20, bold=True), fill=WHITE)
    text_right(draw, "●●●", screen_x + screen_w - 10, screen_y + 8, _font(20), GREY)

    # Header app
    draw.rectangle((screen_x, screen_y + 36, screen_x + screen_w, screen_y + 100), fill=GREEN_DARK)
    draw.text((screen_x + 16, screen_y + 50), "MermaOps", font=_font(28, bold=True), fill=WHITE)
    draw.text((screen_x + 16, screen_y + 78), "Super Martinez", font=_font(18), fill=(*NEON, 200))

    # Semaforo KPI
    semy = screen_y + 116
    semvals = [("ALERTA", RED, "Semaforo"), ("3", RED, "Criticos"),
               ("5", AMBER, "Altos"), ("4", BLUE, "Acciones")]
    for i, (v, c, l) in enumerate(semvals):
        kx = screen_x + 8 + i * (screen_w // 4)
        kw = screen_w // 4 - 6
        rrect(draw, (kx, semy, kx + kw, semy + 78), radius=8, fill=BG3)
        draw.rectangle((kx, semy, kx + kw, semy + 4), fill=c)
        draw.text((kx + kw // 2 - 10, semy + 10), v, font=_font(20, bold=True), fill=c)
        draw.text((kx + 4, semy + 54), l, font=_font(14), fill=GREY)

    # Lista de acciones
    acty = semy + 96
    draw.text((screen_x + 14, acty), "Acciones pendientes", font=_font(20, bold=True), fill=OFF_WHITE)
    acty += 34

    actions = [
        ("Merluza fresca", "Pasillo 4  ·  MANIANA", "Donar", RED),
        ("Yogures Danone", "Pasillo 2  ·  2 dias", "Rebajar", AMBER),
        ("Pan integral", "Pasillo 1  ·  HOY", "Retirar", RED),
        ("Fresas 500g", "Pasillo 3  ·  3 dias", "Revisar", BLUE),
        ("Pechuga pollo", "Pasillo 5  ·  1 dia", "Donar", AMBER),
    ]
    for name, sub, action, col in actions:
        rrect(draw, (screen_x + 8, acty, screen_x + screen_w - 8, acty + 64),
              radius=8, fill=BG2)
        draw.rectangle((screen_x + 8, acty, screen_x + 12, acty + 64), fill=col)
        draw.text((screen_x + 22, acty + 8), name, font=_font(18, bold=True), fill=WHITE)
        draw.text((screen_x + 22, acty + 34), sub, font=_font(15), fill=GREY)
        # badge accion
        bbox = draw.textbbox((0, 0), action, font=_font(14, bold=True))
        bw = bbox[2] - bbox[0] + 16
        rrect(draw, (screen_x + screen_w - bw - 18, acty + 18,
                     screen_x + screen_w - 18, acty + 46),
              radius=6, fill=col)
        draw.text((screen_x + screen_w - bw - 10, acty + 22),
                  action, font=_font(14, bold=True), fill=WHITE)
        acty += 76

    # Nav bar inferior
    nav_y = screen_y + screen_h - 72
    draw.rectangle((screen_x, nav_y, screen_x + screen_w, screen_y + screen_h), fill=BG2)
    nav_items = [("Dashboard", NEON), ("Scan", GREY), ("Acciones", GREY),
                 ("Informes", GREY), ("Agentes", GREY)]
    for i, (lbl, col) in enumerate(nav_items):
        nx = screen_x + 4 + i * (screen_w // 5)
        nw = screen_w // 5 - 4
        circle(draw, nx + nw // 2, nav_y + 20, 16, BG3 if col == GREY else GREEN_DARK)
        draw.text((nx + nw // 2 - 14, nav_y + 42), lbl[:5], font=_font(13), fill=col)

    # Indicador home
    circle(draw, PHONE_X + PHONE_W // 2, PHONE_Y + PHONE_H - 14, 20, (30, 45, 70))

    # ======================================================= TELEGRAM MOCKUP ==
    TG_X, TG_Y = 860, 130
    TG_W, TG_H = 500, 1060

    # Ventana Telegram
    rrect(draw, (TG_X, TG_Y, TG_X + TG_W, TG_Y + TG_H),
          radius=20, fill=(15, 20, 32))
    rrect(draw, (TG_X, TG_Y, TG_X + TG_W, TG_Y + TG_H),
          radius=20, fill=None, outline=(30, 45, 70), width=2)

    # Header Telegram
    draw.rectangle((TG_X, TG_Y, TG_X + TG_W, TG_Y + 80), fill=(18, 30, 55))
    draw.line((TG_X, TG_Y + 80, TG_X + TG_W, TG_Y + 80), fill=(30, 45, 75), width=1)

    # Avatar Chuwi en header
    circle(draw, TG_X + 45, TG_Y + 40, 26, NEON)
    circle(draw, TG_X + 45, TG_Y + 40, 22, GREEN_DARK)
    draw.text((TG_X + 34, TG_Y + 26), "C", font=_font(28, bold=True), fill=NEON)

    draw.text((TG_X + 82, TG_Y + 15), "Chuwi", font=_font(24, bold=True), fill=WHITE)
    circle(draw, TG_X + 82 + 12, TG_Y + 58, 6, NEON)
    draw.text((TG_X + 104, TG_Y + 50), "en linea", font=_font(18), fill=NEON)

    # Mensajes del chat
    def tg_bubble(text_lines, bx, by, bw, bg, is_user=False, accent=None):
        line_h = 36
        ph = 20
        total_h = len(text_lines) * line_h + ph * 2
        rx = bx if not is_user else TG_X + TG_W - bx - bw
        rrect(draw, (rx, by, rx + bw, by + total_h), radius=14, fill=bg)
        if accent:
            draw.rectangle((rx, by, rx + 4, by + total_h), fill=accent)
        for li, (line, col, bold) in enumerate(text_lines):
            f = _font(18, bold=bold)
            draw.text((rx + (8 if accent else 14), by + ph + li * line_h), line, font=f, fill=col)
        return by + total_h + 12

    cy = TG_Y + 96

    # Sistema: kuine detectó
    draw.text((TG_X + TG_W // 2 - 90, cy), "Kuine detecto nuevo CRITICO",
              font=_font(16), fill=GREY2)
    cy += 32

    # Burbuja de Chuwi (alerta)
    cy = tg_bubble([
        ("ALERTA CRITICA", RED, True),
        ("Merluza fresca — Pasillo 4", WHITE, True),
        ("Caduca MANIANA | 6 uds | 48 EUR", OFF_WHITE, False),
        ("", GREY, False),
        ("Kuine recomienda:", NEON, True),
        ("Donar hoy antes de las 17h", GREEN_MID, False),
        ("Banco de Alimentos Caritas", GREY, False),
    ], 14, cy, 420, (14, 28, 22), accent=RED)

    # Timestamp
    text_right(draw, "08:47 ✓✓", TG_X + TG_W - 14, cy - 26, _font(16), GREY2)

    # Botones de accion
    buttons = [("Donar", GREEN_MID), ("Rebajar 50%", AMBER), ("Retirar", (80, 25, 25))]
    bx_start = TG_X + 14
    for btn, col in buttons:
        bbox = draw.textbbox((0, 0), btn, font=_font(18, bold=True))
        bw2 = bbox[2] - bbox[0] + 28
        rrect(draw, (bx_start, cy, bx_start + bw2, cy + 44), radius=10, fill=col)
        draw.text((bx_start + 14, cy + 10), btn, font=_font(18, bold=True), fill=WHITE)
        bx_start += bw2 + 10
    cy += 58

    # Respuesta usuario
    cy = tg_bubble([
        ("Donado, gracias!", WHITE, False),
    ], 14, cy, 210, (22, 50, 38), is_user=True)

    # Respuesta Chuwi
    cy = tg_bubble([
        ("Perfecto! Registro creado:", WHITE, True),
        ("Ahorro: 48 EUR", NEON, True),
        ("CO2 evitado: 0.6 kg", GREEN_MID, False),
        ("Deduccion fiscal: 16.8 EUR", AMBER, False),
    ], 14, cy, 340, (10, 28, 20), accent=NEON)

    # Separador
    draw.line((TG_X + 20, cy + 8, TG_X + TG_W - 20, cy + 8), fill=GREY2, width=1)
    draw.text((TG_X + TG_W // 2 - 70, cy + 16), "— mas tarde —",
              font=_font(16), fill=GREY2)
    cy += 44

    # Burbuja /informe
    cy = tg_bubble([
        ("/informe", NEON, True),
    ], 14, cy, 150, (22, 50, 38), is_user=True)

    cy = tg_bubble([
        ("Generando el brief de hoy...", WHITE, False),
        ("", GREY, False),
        ("PDF adjunto (34 KB)", NEON, True),
        ("Brief_20260519.pdf", BLUE, False),
    ], 14, cy, 340, (10, 28, 20), accent=BLUE)

    # Cuadro PDF simulado
    rrect(draw, (TG_X + 14, cy, TG_X + 350, cy + 70), radius=10, fill=BG3)
    draw.rectangle((TG_X + 14, cy, TG_X + 58, cy + 70), fill=RED)
    draw.text((TG_X + 20, cy + 18), "PDF", font=_font(24, bold=True), fill=WHITE)
    draw.text((TG_X + 68, cy + 10), "Brief_20260519.pdf", font=_font(20, bold=True), fill=WHITE)
    draw.text((TG_X + 68, cy + 42), "34 KB  ·  Generado por Kuine", font=_font(17), fill=GREY)
    cy += 80

    # Input bar
    draw.rectangle((TG_X + 8, TG_Y + TG_H - 72, TG_X + TG_W - 8, TG_Y + TG_H - 12),
                   fill=BG3)
    draw.text((TG_X + 24, TG_Y + TG_H - 57), "Escribe un mensaje...",
              font=_font(20), fill=GREY2)
    circle(draw, TG_X + TG_W - 36, TG_Y + TG_H - 42, 22, NEON)
    draw.text((TG_X + TG_W - 48, TG_Y + TG_H - 54), ">", font=_font(24, bold=True), fill=WHITE)

    # ======================================================= AGENTES PANEL ==
    AG_X, AG_Y = 1390, 130
    AG_W, AG_H = 570, 1060

    rrect(draw, (AG_X, AG_Y, AG_X + AG_W, AG_Y + AG_H), radius=20, fill=BG2)
    rrect(draw, (AG_X, AG_Y, AG_X + AG_W, AG_Y + AG_H),
          radius=20, fill=None, outline=(30, 50, 80), width=2)

    draw.text((AG_X + 24, AG_Y + 22), "Sistema multi-agente",
              font=_font(28, bold=True), fill=WHITE)
    draw.text((AG_X + 24, AG_Y + 56), "12 agentes activos  ·  Kuine orquesta",
              font=_font(19), fill=GREY)
    draw.line((AG_X + 16, AG_Y + 88, AG_X + AG_W - 16, AG_Y + 88), fill=(*NEON, 80), width=1)

    # Hub Kuine visual
    hub_cx = AG_X + AG_W // 2
    hub_cy = AG_Y + 320

    # Anillos
    for r, col in [(95, (0, 40, 28)), (110, (0, 30, 20)), (125, (0, 20, 14))]:
        draw.ellipse((hub_cx - r, hub_cy - r, hub_cx + r, hub_cy + r),
                     outline=col, width=1)

    # Hexagono Kuine
    hex_pts = []
    for i in range(6):
        a = math.radians(60 * i - 30)
        hex_pts.append((hub_cx + 58 * math.cos(a), hub_cy + 58 * math.sin(a)))
    draw.polygon(hex_pts, fill=GREEN_DARK, outline=NEON, width=3)

    draw.text((hub_cx - 44, hub_cy - 22), "KUINE", font=_font(30, bold=True), fill=WHITE)
    draw.text((hub_cx - 42, hub_cy + 12), "Opus 4.7", font=_font(18), fill=NEON)

    # Agentes en orbita
    agents = [
        ("Chuwi",     GREEN_MID, 90),
        ("Evaluador", BLUE,      140),
        ("Validador", BLUE,      190),
        ("Consenso",  BLUE,      240),
        ("Predictor", PURPLE,    290),
        ("Vision",    PURPLE,    340),
        ("Precio",    AMBER,     30),
        ("Stock",     AMBER,     0),
        ("Notif.",    RED,       310),
        ("Reporter",  TEAL,      50),
    ]
    r_orb = 155
    for name, col, deg in agents:
        a = math.radians(deg)
        ax = int(hub_cx + r_orb * math.cos(a))
        ay = int(hub_cy + r_orb * math.sin(a))

        # linea conexion
        inner_x = int(hub_cx + 60 * math.cos(a))
        inner_y = int(hub_cy + 60 * math.sin(a))
        draw.line((inner_x, inner_y, ax - int(24 * math.cos(a)), ay - int(24 * math.sin(a))),
                  fill=(*col, 120), width=2)

        # nodo agente
        circle(draw, ax, ay, 30, BG3)
        circle(draw, ax, ay, 30, None)  # borde
        draw.ellipse((ax - 30, ay - 30, ax + 30, ay + 30), outline=col, width=2)

        bbox = draw.textbbox((0, 0), name, font=_font(14, bold=True))
        tw = bbox[2] - bbox[0]
        draw.text((ax - tw // 2, ay - 12), name, font=_font(14, bold=True), fill=col)

    # Metricas bajo el hub
    metrics_y = AG_Y + 550
    draw.line((AG_X + 16, metrics_y, AG_X + AG_W - 16, metrics_y), fill=(*NEON, 60), width=1)
    draw.text((AG_X + 24, metrics_y + 12), "Evaluacion cuantitativa",
              font=_font(22, bold=True), fill=NEON)

    mets = [
        ("800/800", "Tests en verde", NEON),
        ("100%",    "Robustez advers.", GREEN_MID),
        ("+83pp",   "vs. baseline", AMBER),
        ("< 1s",    "Tiempo total", BLUE),
    ]
    for i, (v, l, c) in enumerate(mets):
        mx = AG_X + 16 + i * (AG_W // 4)
        mw = AG_W // 4 - 8
        rrect(draw, (mx, metrics_y + 50, mx + mw, metrics_y + 148), radius=10, fill=BG3)
        draw.rectangle((mx, metrics_y + 50, mx + mw, metrics_y + 56), fill=c)
        text_centered(draw, v, mx, metrics_y + 68, mw, _font(28, bold=True), c)
        text_centered(draw, l, mx, metrics_y + 108, mw, _font(16), GREY)

    # Linea de tiempo scheduler
    sched_y = metrics_y + 170
    draw.text((AG_X + 24, sched_y), "Scheduler automatico", font=_font(22, bold=True), fill=WHITE)

    sched_jobs = [
        ("07:30", "Brief diario", NEON),
        ("12:00", "Check merma", AMBER),
        ("20:00", "Cierre tienda", BLUE),
        ("30min", "Chuwi proactivo", GREEN_MID),
        ("Lunes", "Inf. semanal", PURPLE),
    ]
    for i, (time, label, col) in enumerate(sched_jobs):
        jx = AG_X + 16 + i * (AG_W // 5)
        jw = AG_W // 5 - 6
        circle(draw, jx + jw // 2, sched_y + 60, 10, col)
        text_centered(draw, time, jx, sched_y + 80, jw, _font(15, bold=True), col)
        text_centered(draw, label, jx, sched_y + 104, jw, _font(13), GREY)

    # Linea conectando puntos
    for i in range(len(sched_jobs) - 1):
        jx1 = AG_X + 16 + i * (AG_W // 5) + (AG_W // 5) // 2
        jx2 = AG_X + 16 + (i + 1) * (AG_W // 5) + (AG_W // 5) // 2
        draw.line((jx1, sched_y + 60, jx2, sched_y + 60), fill=GREY2, width=2)

    # Stack tech (abajo)
    stack_y = sched_y + 145
    draw.line((AG_X + 16, stack_y, AG_X + AG_W - 16, stack_y), fill=(*NEON, 60), width=1)
    draw.text((AG_X + 24, stack_y + 12), "Stack tecnico", font=_font(22, bold=True), fill=WHITE)

    tech_items = [
        ("Claude API", NEON), ("FastAPI 8001", BLUE), ("Supabase", TEAL),
        ("Flutter", PURPLE), ("Pytest 800/800", GREEN_MID), ("python-tb-bot", AMBER),
    ]
    for i, (tech, col) in enumerate(tech_items):
        tx = AG_X + 16 + (i % 3) * (AG_W // 3)
        ty = stack_y + 50 + (i // 3) * 58
        tw2 = AG_W // 3 - 10
        rrect(draw, (tx, ty, tx + tw2, ty + 44), radius=8, fill=BG3)
        draw.rectangle((tx, ty, tx + 4, ty + 44), fill=col)
        draw.text((tx + 14, ty + 10), tech, font=_font(18, bold=True), fill=WHITE)

    # ===================================================== PANEL DERECHO ==
    RIGHT_X = 1990
    RIGHT_W = W - RIGHT_X - 20

    draw.text((RIGHT_X, 136), "Por que elegir\nMermaOps", font=_font(36, bold=True), fill=WHITE)
    draw.line((RIGHT_X, 248, RIGHT_X + RIGHT_W, 248), fill=(*NEON, 100), width=2)

    points = [
        ("Sistema operativo de IA",
         "No un chatbot. 12 agentes colaborando en tiempo real con datos reales.",
         NEON),
        ("Chuwi avisa sin que le preguntes",
         "Monitoriza la tienda cada 30 min y envia alertas proactivas por Telegram.",
         GREEN_MID),
        ("PDFs en un comando",
         "/informe genera el brief del dia con datos reales y lo envia al chat.",
         BLUE),
        ("Impacto ESG medible",
         "Registra CO2 evitado y calcula deduccion fiscal automaticamente.",
         TEAL),
        ("Evaluacion adversarial",
         "23 ataques de prompt injection bloqueados. 100% de robustez.",
         AMBER),
        ("Demo lista en 5 minutos",
         "make seed && make advance N=1 && make start. Listo.",
         PURPLE),
    ]
    for i, (title, desc, col) in enumerate(points):
        py = 268 + i * 155
        circle(draw, RIGHT_X + 12, py + 20, 12, col)
        draw.text((RIGHT_X + 34, py + 6), title, font=_font(22, bold=True), fill=col)
        for li, line in enumerate(desc.split(". ")):
            if line:
                draw.text((RIGHT_X + 34, py + 40 + li * 30), line + ("." if not line.endswith(".") else ""),
                          font=_font(18), fill=GREY)

    # ============================================================= FOOTER ==
    draw.rectangle((0, H - 70, W, H), fill=BG2)
    draw.line((0, H - 70, W, H - 70), fill=(*NEON, 120), width=2)

    footer_items = [
        ("github.com/alvaroferrer1/Tfm", NEON),
        ("@ChuwiMermaOpsBot", GREEN_MID),
        ("800/800 tests", BLUE),
        ("MermaOps · IA multi-agente", GREY),
        ("TFM  Alvaro Ferrer  2026", GREY2),
    ]
    spacing = W // len(footer_items)
    for i, (text, col) in enumerate(footer_items):
        text_centered(draw, text, i * spacing, H - 48, spacing, _font(18, bold=(col != GREY and col != GREY2)), col)

    return img


def generate_hero(output_path: str | None = None) -> bytes:
    img = build()

    if output_path:
        img.save(output_path, "PNG", optimize=True)
        size_kb = Path(output_path).stat().st_size // 1024
        print(f"Hero image: {output_path}  ({W}x{H}px, {size_kb} KB)")

    import io
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


if __name__ == "__main__":
    out = Path(__file__).parent.parent.parent / "MermaOps_Hero.png"
    generate_hero(str(out))
