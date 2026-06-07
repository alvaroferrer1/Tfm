"""
slides_generator.py -- PDF de presentacion del TFM MermaOps.
10 diapositivas A4 apaisado con diseno oscuro profesional.

Uso:
    python -m backend.core.slides_generator
"""
from __future__ import annotations
import io
import math
import unicodedata
from datetime import date
from pathlib import Path

from fpdf import FPDF, XPos, YPos

W, H = 297, 210   # A4 landscape mm

# -- Paleta ------------------------------------------------------------------
_BG          = (8, 12, 22)
_BG2         = (13, 20, 36)
_G1          = (2, 60, 44)
_G2          = (4, 100, 72)
_G3          = (6, 148, 100)
_NEON        = (0, 230, 140)
_NEON2       = (0, 255, 160)
_WHITE       = (255, 255, 255)
_OFF_WHITE   = (220, 230, 240)
_GREY        = (140, 160, 185)
_GREY2       = (80, 100, 125)
_RED         = (225, 55, 55)
_RED2        = (180, 30, 30)
_AMBER       = (230, 165, 30)
_BLUE        = (45, 115, 240)
_BLUE2       = (20, 80, 200)
_PURPLE      = (130, 55, 225)
_TEAL        = (20, 185, 165)


# -- Helpers texto -----------------------------------------------------------
def _t(text: str) -> str:
    """ASCII-safe para Helvetica."""
    text = str(text)
    for src, dst in [
        ("€", "EUR"), ("°", "o"), ("·", "-"),
        ("—", "-"), ("–", "-"), ("’", "'"),
        ("“", '"'), ("”", '"'), ("…", "..."),
        ("→", "->"), ("←", "<-"), ("×", "x"),
    ]:
        text = text.replace(src, dst)
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if ord(c) < 128)


# -- Clase base --------------------------------------------------------------
class Deck(FPDF):
    def __init__(self):
        super().__init__(orientation="L", unit="mm", format="A4")
        self.set_auto_page_break(auto=False)
        self.set_margins(0, 0, 0)

    # ---- fondos y geometria ------------------------------------------------

    def fill(self, color=_BG):
        self.set_fill_color(*color)
        self.rect(0, 0, W, H, "F")

    def panel(self, x, y, w, h, color, radius: float = 0):
        self.set_fill_color(*color)
        self.rect(x, y, w, h, "F")

    def hbar(self, y, h=1.5, color=_NEON, x=0, w=W):
        self.set_fill_color(*color)
        self.rect(x, y, w, h, "F")

    def vbar(self, x, h=H, w=1.5, y=0, color=_NEON):
        self.set_fill_color(*color)
        self.rect(x, y, w, h, "F")

    def circle(self, cx, cy, r, color, style="F"):
        self.set_fill_color(*color)
        self.set_draw_color(*color)
        self.ellipse(cx - r, cy - r, r * 2, r * 2, style)

    def ring(self, cx, cy, r, lw, color):
        self.set_draw_color(*color)
        self.set_line_width(lw)
        self.ellipse(cx - r, cy - r, r * 2, r * 2, "D")

    def arc_dots(self, cx, cy, r, n, size, color, start_deg=0, end_deg=360):
        """Puntos distribuidos en arco."""
        self.set_fill_color(*color)
        span = end_deg - start_deg
        for i in range(n):
            a = math.radians(start_deg + span * i / max(n - 1, 1))
            x = cx + r * math.cos(a)
            y = cy + r * math.sin(a)
            self.ellipse(x - size, y - size, size * 2, size * 2, "F")

    def arrow(self, x1, y1, x2, y2, lw=0.4, color=_NEON):
        self.set_draw_color(*color)
        self.set_line_width(lw)
        self.line(x1, y1, x2, y2)
        # punta
        angle = math.atan2(y2 - y1, x2 - x1)
        size = 2.5
        for da in (0.5, -0.5):
            self.line(x2, y2,
                      x2 - size * math.cos(angle - da),
                      y2 - size * math.sin(angle - da))

    def gradient_panel(self, x, y, w, h, c1, c2, steps=12, vertical=False):
        """Simula degradado con franjas."""
        for i in range(steps):
            t = i / steps
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            self.set_fill_color(r, g, b)
            if vertical:
                sh = h / steps
                self.rect(x, y + i * sh, w, sh + 0.5, "F")
            else:
                sw = w / steps
                self.rect(x + i * sw, y, sw + 0.5, h, "F")

    def dot_grid(self, x, y, w, h, step=8, size=0.6, color=_G2):
        self.set_fill_color(*color)
        xi = x
        while xi <= x + w:
            yi = y
            while yi <= y + h:
                self.ellipse(xi - size, yi - size, size * 2, size * 2, "F")
                yi += step
            xi += step

    def hex_shape(self, cx, cy, r, color, style="F"):
        """Hexagono regular."""
        pts = []
        for i in range(6):
            a = math.radians(60 * i - 30)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        self.set_fill_color(*color)
        self.set_draw_color(*color)
        self.polygon(pts, style)

    # ---- tipografia -------------------------------------------------------

    def heading(self, text, x, y, w=W, size=44, color=_WHITE, align="L", bold=True):
        self.set_font("Helvetica", "B" if bold else "", size)
        self.set_text_color(*color)
        self.set_xy(x, y)
        self.multi_cell(w, size * 0.42, _t(text), align=align)
        return self.get_y()

    def sub(self, text, x, y, w=W, size=14, color=_OFF_WHITE, align="L"):
        self.set_font("Helvetica", "", size)
        self.set_text_color(*color)
        self.set_xy(x, y)
        self.multi_cell(w, size * 0.55, _t(text), align=align)
        return self.get_y()

    def label(self, text, x, y, w=100, size=8, color=_NEON, upper=True):
        txt = _t(text).upper() if upper else _t(text)
        self.set_font("Helvetica", "B", size)
        self.set_text_color(*color)
        self.set_xy(x, y)
        self.cell(w, size * 0.9, txt)

    def body(self, text, x, y, w=180, size=10, color=_OFF_WHITE, align="L", line_h=None):
        self.set_font("Helvetica", "", size)
        self.set_text_color(*color)
        self.set_xy(x, y)
        self.multi_cell(w, line_h or size * 0.58, _t(text), align=align)
        return self.get_y()

    def badge(self, text, x, y, bg=_G1, fg=_NEON, size=8, pad=3):
        tw = len(_t(text)) * size * 0.48 + pad * 2
        self.panel(x, y, tw, size * 0.85 + pad * 2, bg, radius=1)
        self.set_font("Helvetica", "B", size)
        self.set_text_color(*fg)
        self.set_xy(x + pad, y + pad * 0.7)
        self.cell(tw - pad * 2, size * 0.85, _t(text))
        return tw + 3

    def progress_bar(self, x, y, w, h, pct, color=_NEON, bg=_BG2):
        self.panel(x, y, w, h, bg)
        filled = max(1, w * pct / 100)
        self.panel(x, y, filled, h, color)

    def big_kpi(self, value, label, x, y, w=60, h=40, vcolor=_NEON, unit=""):
        # caja con borde neon arriba
        self.panel(x, y, w, h, _BG2, radius=2)
        self.panel(x, y, w, 2, vcolor)
        # valor
        vsize = 30 if len(_t(value)) <= 4 else 22
        self.set_font("Helvetica", "B", vsize)
        self.set_text_color(*vcolor)
        self.set_xy(x, y + 5)
        self.cell(w, vsize * 0.6, _t(value) + _t(unit), align="C")
        # etiqueta
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*_GREY)
        self.set_xy(x, y + h - 12)
        self.multi_cell(w, 4.5, _t(label), align="C")

    def slide_footer(self, n, total=10, store="MermaOps TFM  |  Alvaro Ferrer"):
        # linea inferior
        self.hbar(H - 8, 0.4, _G2)
        self.set_font("Helvetica", "", 6.5)
        self.set_text_color(*_GREY2)
        self.set_xy(10, H - 7)
        self.cell(100, 6, _t(store))
        self.set_xy(W - 25, H - 7)
        self.cell(20, 6, f"{n} / {total}", align="R")


# ============================================================  SLIDES  ======


def s01_portada(d: Deck):
    d.add_page()
    # Fondo degradado horizontal profundo
    d.gradient_panel(0, 0, W, H, _BG, (4, 18, 38), steps=24, vertical=False)

    # Grid de puntos muy sutil
    d.dot_grid(0, 0, W, H, step=11, size=0.35, color=(12, 22, 42))

    # Linea neon superior
    d.panel(0, 0, W, 3, _NEON)

    # Anillos decorativos grandes centrados a la izquierda
    for r, w_ring, alpha in [(90, 0.5, 30), (70, 0.7, 45), (50, 1.0, 60), (30, 1.5, 80)]:
        d.ring(70, H // 2, r, w_ring, (0, alpha, int(alpha * 0.7)))

    # Punto central neon
    d.circle(70, H // 2, 5, _NEON)

    # NOMBRE enorme — ocupa toda la anchura
    d.set_font("Helvetica", "B", 80)
    d.set_text_color(*_WHITE)
    d.set_xy(0, 20)
    d.cell(W, 42, "MermaOps", align="C")

    # Tagline centrada
    d.set_font("Helvetica", "", 16)
    d.set_text_color(*_NEON)
    d.set_xy(0, 68)
    d.cell(W, 10, "La IA que hace que los supermercados desperdicien menos.", align="C")

    # Linea separadora
    d.hbar(85, 0.6, _G2, 60, 177)

    # 3 cifras clave centradas — Apple style
    kpis = [
        ("11", "agentes de IA", _NEON),
        ("432", "tests en verde", _G3),
        ("100%", "robustez adversarial", _BLUE),
    ]
    for i, (val, lbl, col) in enumerate(kpis):
        bx = 55 + i * 70
        d.set_font("Helvetica", "B", 42)
        d.set_text_color(*col)
        d.set_xy(bx, 92)
        d.cell(60, 22, _t(val), align="C")
        d.set_font("Helvetica", "", 8)
        d.set_text_color(*_GREY)
        d.set_xy(bx, 116)
        d.cell(60, 5, _t(lbl), align="C")

    # Separador
    d.hbar(128, 0.4, _GREY2, 60, 177)

    # Autor y metadata
    d.set_font("Helvetica", "B", 13)
    d.set_text_color(*_WHITE)
    d.set_xy(0, 134)
    d.cell(W, 8, "Alvaro Ferrer Muro", align="C")

    d.set_font("Helvetica", "", 9)
    d.set_text_color(*_GREY)
    d.set_xy(0, 144)
    d.cell(W, 6, _t(f"Master en IA Generativa & Innovation  |  {date.today().strftime('%B %Y')}"), align="C")

    # Powered by — esquina inferior
    d.set_font("Helvetica", "", 7)
    d.set_text_color(*_GREY2)
    d.set_xy(0, H - 12)
    d.cell(W, 6, "MermaOps  |  FastAPI  |  Flutter  |  Supabase  |  Telegram", align="C")

    # Linea inferior neon
    d.panel(0, H - 3, W, 3, _NEON)


def s02_problema(d: Deck):
    d.add_page()
    d.fill(_BG)
    d.dot_grid(0, 0, W, H, step=10, size=0.45, color=(14, 22, 40))

    # Banda superior
    d.panel(0, 0, W, 18, _BG2)
    d.hbar(18, 1.5, _RED)
    d.label("El problema que nadie ha resuelto bien", 12, 5, 200, 8, _RED)

    # Titulo grande
    d.heading("El desperdicio alimentario\ncuesta dinero, planeta y negocio.", 12, 25, 200, 26, _WHITE)

    # 4 bloques de estadisticas grandes
    stats = [
        ("10 kg",  "por habitante\ny anio en Espana",      _RED,   _RED2),
        ("2-5%",   "de ingresos perdidos\npor merma",       _AMBER, (160, 100, 10)),
        ("1.3B EUR", "perdidos anualmente\nen distribucion", _RED,   _RED2),
        ("1/3",    "de toda la comida\nse desperdicia",     _AMBER, (160, 100, 10)),
    ]
    bw, bh = 64, 72
    for i, (val, lbl, fc, bg) in enumerate(stats):
        bx = 12 + i * 70
        by = 78
        # caja con color de fondo suave
        d.panel(bx, by, bw, bh, bg, radius=2)
        d.panel(bx, by, bw, 3, fc)
        # valor enorme
        vsize = 28 if len(_t(val)) <= 5 else 20
        d.set_font("Helvetica", "B", vsize)
        d.set_text_color(*fc)
        d.set_xy(bx, by + 8)
        d.cell(bw, vsize * 0.55, _t(val), align="C")
        # label
        d.set_font("Helvetica", "", 9)
        d.set_text_color(*_OFF_WHITE)
        d.set_xy(bx, by + 40)
        d.multi_cell(bw, 5.5, _t(lbl), align="C")

    # Texto explicativo
    d.hbar(158, 0.4, _GREY2)
    d.body(
        "Los supermercados gestionan la merma de forma reactiva: revisan caducidades a mano, "
        "toman decisiones sin datos y pierden miles de euros al mes en productos que podrian "
        "haberse vendido con descuento, donado o retirado a tiempo.",
        12, 162, 268, 9, _GREY
    )

    # Panel derecho decorativo
    d.panel(294, 30, 3, 120, _RED)
    d.ring(291, 150, 28, 0.5, (80, 15, 15))

    d.slide_footer(2)


def s03_solucion(d: Deck):
    d.add_page()
    d.fill(_BG)
    d.dot_grid(150, 0, 150, H, step=9, size=0.45, color=(10, 20, 38))

    d.panel(0, 0, W, 18, _BG2)
    d.hbar(18, 1.5, _NEON)
    d.label("La solucion: MermaOps", 12, 5, 200, 8, _NEON)

    # Titulo
    d.heading("No un chatbot. Un sistema\noperativo de IA completo.", 12, 25, 155, 28, _WHITE)

    # Bullets principales
    items = [
        "12 agentes de IA trabajando en paralelo 24/7 sin supervision",
        "Kuine (Opus 4.7) orquesta y toma decisiones: rebajar, donar o retirar",
        "Chuwi avisa por Telegram antes de que nadie lo pida",
        "Vision por computador analiza el estado real del producto en 3 segundos",
        "Genera briefs, informes semanales y mensuales en PDF automaticamente",
    ]
    for i, item in enumerate(items):
        by = 82 + i * 18
        d.circle(16, by + 4, 3, _NEON)
        d.set_font("Helvetica", "", 10.5)
        d.set_text_color(*_OFF_WHITE)
        d.set_xy(23, by)
        d.cell(135, 8, _t(item))

    # Panel comparativa derecha
    d.panel(162, 26, 128, 165, _BG2, radius=2)
    d.panel(162, 26, 128, 3, _NEON)
    d.label("MermaOps vs. competencia", 168, 33, 120, 8)

    rows = [
        ("Winnow Vision",    "Vision",      "Sin agentes",    False),
        ("Too Good To Go",   "Canal venta", "No es IA",       False),
        ("Wasteless",        "Pricing",     "Sin orquestacion", False),
        ("MermaOps",         "Todo",        "IA completa",    True),
    ]
    for i, (name, feat, diff, highlight) in enumerate(rows):
        ry = 44 + i * 34
        bg = (2, 45, 30) if highlight else (16, 26, 44)
        fc_name = _NEON if highlight else _GREY
        d.panel(168, ry, 116, 28, bg, radius=1)
        if highlight:
            d.vbar(168, 28, 2.5, ry, _NEON)
        d.set_font("Helvetica", "B", 10)
        d.set_text_color(*fc_name)
        d.set_xy(174, ry + 5)
        d.cell(60, 6, _t(name))
        d.set_font("Helvetica", "", 8)
        d.set_text_color(*(_GREEN_LIGHT := _G3 if highlight else _GREY))
        d.set_xy(174, ry + 14)
        d.cell(50, 5, _t(feat + "  |  " + diff))

    d.slide_footer(3)


def s04_arquitectura(d: Deck):
    d.add_page()
    d.fill(_BG)

    # Header bar
    d.panel(0, 0, W, 18, _BG2)
    d.hbar(18, 1.5, _NEON)
    d.label("Arquitectura multi-agente — Hub & Spoke", 12, 5, 200, 8, _NEON)

    d.heading("12 agentes. Un cerebro central.", 12, 22, 218, 18, _WHITE)
    d.sub("Kuine (Opus 4.7) en el nucleo  |  4 agentes primarios  |  6 especializados",
          12, 34, 210, 7.5, _GREY)

    # ── Diagram geometry ──────────────────────────────────────────────────────
    cx, cy = 160, 122   # hub center
    r_inner, r_outer = 50, 80

    # Decorative orbit rings (faint concentric)
    d.ring(cx, cy, r_outer + 2, 0.18, (0, 28, 20))
    d.ring(cx, cy, r_outer,     0.30, (0, 44, 34))
    d.ring(cx, cy, r_inner + 1, 0.20, (0, 40, 30))
    d.ring(cx, cy, r_inner,     0.42, (0, 60, 46))
    d.ring(cx, cy, 26,          0.55, (0, 78, 58))

    # ── Hub: Kuine hexagon ────────────────────────────────────────────────────
    d.hex_shape(cx, cy, 22, _G1)
    d.hex_shape(cx, cy, 22, _NEON, "D")

    d.set_font("Helvetica", "B", 13)
    d.set_text_color(*_WHITE)
    d.set_xy(cx - 18, cy - 8)
    d.cell(36, 7, "KUINE", align="C")

    d.set_font("Helvetica", "", 6.5)
    d.set_text_color(*_NEON)
    d.set_xy(cx - 18, cy + 1)
    d.cell(36, 5, "Opus 4.7", align="C")
    d.set_xy(cx - 18, cy + 7)
    d.cell(36, 5, "16 tools", align="C")

    # ── Agents ────────────────────────────────────────────────────────────────
    # Inner ring (r=50): 4 core agents at diagonal positions
    inner_agents = [
        ("Chuwi",     "Sonnet 4.6", "Telegram", _G3,   315),
        ("Evaluador", "Sonnet 4.6", "Score",    _BLUE,  45),
        ("Validador", "Sonnet 4.6", "100%",     _BLUE, 135),
        ("Consenso",  "Son. x3",   ">=90",      _BLUE, 225),
    ]
    # Outer ring (r=80): 6 specialized agents at hexagonal positions
    outer_agents = [
        ("Reportero",  "Sonnet 4.6", "Briefs",  _TEAL,    0),
        ("Notificador","Sonnet 4.6", "Alertas", _RED,     60),
        ("Stock",      "Haiku 4.5",  "Repos.",  _AMBER,  120),
        ("Precio",     "Haiku 4.5",  "EUR",     _AMBER,  180),
        ("Predictor",  "Haiku 4.5",  "Tiempo",  _PURPLE, 240),
        ("Vision",     "claude-3-5", "Fotos",   _PURPLE, 300),
    ]

    bw, bh = 36, 19

    for r_orbit, agents in [(r_inner, inner_agents), (r_outer, outer_agents)]:
        for name, model, role, col, deg in agents:
            a = math.radians(deg)
            ax = cx + r_orbit * math.cos(a)
            ay = cy + r_orbit * math.sin(a)

            # Connection line: hex edge → agent center
            hx = cx + 23 * math.cos(a)
            hy = cy + 23 * math.sin(a)
            d.set_draw_color(*col)
            d.set_line_width(0.4)
            d.line(hx, hy, ax, ay)

            # Agent box
            bx = ax - bw / 2
            by = ay - bh / 2
            d.panel(bx, by, bw, bh, _BG2)
            d.panel(bx, by, bw, 2.5, col)

            d.set_font("Helvetica", "B", 8)
            d.set_text_color(*_WHITE)
            d.set_xy(bx + 1, by + 4.5)
            d.cell(bw - 2, 5, _t(name), align="C")

            d.set_font("Helvetica", "", 5.5)
            d.set_text_color(*_GREY)
            d.set_xy(bx + 1, by + 10)
            d.cell(bw - 2, 4, _t(model), align="C")

            d.set_font("Helvetica", "B", 5.5)
            d.set_text_color(*col)
            d.set_xy(bx + 1, by + 14)
            d.cell(bw - 2, 4, _t(role), align="C")

    # ── Legend (top-right corner, clear of all agent boxes) ───────────────────
    lx = 237
    d.set_font("Helvetica", "B", 6)
    d.set_text_color(*_GREY2)
    d.set_xy(lx, 22)
    d.cell(55, 5, "MODELOS")
    legend = [
        ("Opus 4.7",   _NEON),
        ("Sonnet 4.6", _BLUE),
        ("Haiku 4.5",  _AMBER),
        ("Multimodal", _PURPLE),
        ("Interfaz",   _G3),
    ]
    for i, (lbl, col) in enumerate(legend):
        ly = 28 + i * 9
        d.circle(lx + 2, ly + 3.5, 2, col)
        d.set_font("Helvetica", "", 6.5)
        d.set_text_color(*_GREY)
        d.set_xy(lx + 6, ly + 0.5)
        d.cell(50, 6, _t(lbl))

    d.slide_footer(4)


def s05_chuwi(d: Deck):
    d.add_page()
    d.fill(_BG)
    d.dot_grid(0, 0, 140, H, step=9, size=0.45, color=(12, 20, 38))

    d.panel(0, 0, W, 18, _BG2)
    d.hbar(18, 1.5, _G3)
    d.label("Chuwi - El agente de campo", 12, 5, 200, 8, _G3)

    # Titulo izquierda
    d.heading("No espera preguntas.\nActua solo.", 12, 25, 130, 32, _WHITE)

    d.set_font("Helvetica", "", 11)
    d.set_text_color(*_G3)
    d.set_xy(12, 76)
    d.multi_cell(130, 6.5, "Un bot responde cuando le preguntas.\nChuwi monitoriza y avisa sin que nadie lo pida.")

    feats = [
        ("Streaming",   "Respuesta progresiva en Telegram, letra a letra"),
        ("Vision",      "Analiza fotos de productos: estado + accion en 3s"),
        ("Proactivo",   "Detecta nuevos CRITICOS y avisa solo cada 30min"),
        ("Memoria",     "Recuerda lo que paso ayer para usarlo hoy"),
        ("PDF",         "/informe y /semana generan y envian PDFs al instante"),
    ]
    for i, (title, desc) in enumerate(feats):
        by = 105 + i * 17
        d.panel(12, by, 125, 13, _BG2, radius=1)
        d.panel(12, by, 3, 13, _G3)
        d.set_font("Helvetica", "B", 9)
        d.set_text_color(*_NEON)
        d.set_xy(18, by + 2)
        d.cell(35, 6, _t(title))
        d.set_font("Helvetica", "", 8.5)
        d.set_text_color(*_OFF_WHITE)
        d.set_xy(55, by + 2)
        d.cell(78, 6, _t(desc))

    # ---- Mock Telegram chat derecha ----------------------------------------
    d.panel(152, 20, 137, 175, (6, 10, 18), radius=3)
    d.panel(152, 20, 137, 14, (4, 60, 44), radius=3)

    # Header chat
    d.circle(162, 27, 5, _NEON)
    d.set_font("Helvetica", "B", 8)
    d.set_text_color(*_WHITE)
    d.set_xy(170, 23)
    d.cell(80, 5, "@ChuwiMermaOpsBot")
    d.set_font("Helvetica", "", 6.5)
    d.set_text_color(*_G3)
    d.set_xy(170, 29)
    d.cell(80, 4, "Agente activo - online")

    # Mensaje alerta (burbujas)
    def bubble(text_lines, bx, by, bw, bg, fg=_WHITE, bold_first=False):
        line_h = 5.5
        total_h = len(text_lines) * line_h + 8
        d.panel(bx, by, bw, total_h, bg, radius=2)
        for li, (line, lc) in enumerate(text_lines):
            f = "B" if li == 0 and bold_first else ""
            d.set_font("Helvetica", f, 8)
            d.set_text_color(*lc)
            d.set_xy(bx + 4, by + 4 + li * line_h)
            d.cell(bw - 8, line_h, _t(line))
        return by + total_h + 3

    # Mensaje de Kuine -> Chuwi (sistema)
    d.set_font("Helvetica", "", 6.5)
    d.set_text_color(*_GREY2)
    d.set_xy(152, 38)
    d.cell(137, 5, "Kuine detecto nuevo CRITICO", align="C")

    # Burbuja alerta
    by = bubble([
        ("[ALERTA CRITICA]", _RED),
        ("Merluza fresca - Pasillo 4", _WHITE),
        ("Caduca MANIANA | 6 unidades", _OFF_WHITE),
        ("Valor en riesgo: 48 EUR", _AMBER),
        ("", _GREY),
        ("Kuine recomienda donar hoy", _NEON),
        ("antes de las 17h", _G3),
    ], 158, 46, 124, (14, 30, 22), bold_first=True)

    # Hora
    d.set_font("Helvetica", "", 5.5)
    d.set_text_color(*_GREY2)
    d.set_xy(268, by - 4)
    d.cell(15, 4, "08:47")

    # Botones accion
    buttons = [("Donar", _G3), ("Rebajar 50%", _AMBER), ("Retirar", (60, 30, 30))]
    bx_b = 158
    for btn, bcol in buttons:
        bw_b = 38
        d.panel(bx_b, by + 2, bw_b, 11, bcol, radius=1)
        d.set_font("Helvetica", "B", 7)
        d.set_text_color(*_WHITE)
        d.set_xy(bx_b, by + 4)
        d.cell(bw_b, 7, _t(btn), align="C")
        bx_b += bw_b + 3

    # Respuesta encargado
    by2 = by + 20
    by2 = bubble([
        ("Donado. Gracias Chuwi!", _WHITE),
    ], 198, by2, 82, (20, 45, 30), bold_first=False)

    # Respuesta Chuwi
    bubble([
        ("Perfecto. Registro creado.", _WHITE),
        ("Ahorro: 48 EUR | CO2: 0.6kg", _NEON),
    ], 158, by2 + 2, 110, (8, 30, 20), bold_first=False)

    d.slide_footer(5)


def s06_resultados(d: Deck):
    d.add_page()
    d.fill(_BG)
    d.dot_grid(0, 0, W, H, step=10, size=0.4, color=(12, 20, 38))

    # Header minimal
    d.panel(0, 0, W, 3, _NEON)
    d.set_font("Helvetica", "B", 9)
    d.set_text_color(*_NEON)
    d.set_xy(0, 8)
    d.cell(W, 6, "RESULTADOS CUANTITATIVOS", align="C")

    # Titulo Apple-style — una linea, enorme
    d.set_font("Helvetica", "B", 34)
    d.set_text_color(*_WHITE)
    d.set_xy(0, 22)
    d.cell(W, 18, "Numeros que no dejan lugar a dudas.", align="C")

    d.hbar(44, 0.5, _GREY2, 40, 217)

    # ---- 4 KPIs en fila — NUMEROS GIGANTES estilo Apple --------------------
    metrics = [
        ("432/432", "Tests en verde\nen menos de 2s", _NEON),
        ("100%",    "Robustez vs\n23 ataques", _G3),
        ("+83pp",   "Sobre baseline\naleatorio", _AMBER),
        ("90.2%",   "Multi-agente vs\nagente unico", _BLUE),
    ]

    zone_w = W / 4
    for i, (val, lbl, col) in enumerate(metrics):
        bx = i * zone_w
        # numero principal — enorme
        vsize = 48 if len(_t(val)) <= 4 else 36
        d.set_font("Helvetica", "B", vsize)
        d.set_text_color(*col)
        d.set_xy(bx, 54)
        d.cell(zone_w, vsize * 0.65, _t(val), align="C")
        # separador color
        d.panel(bx + 10, 100, zone_w - 20, 2, col)
        # label
        d.set_font("Helvetica", "", 9)
        d.set_text_color(*_OFF_WHITE)
        d.set_xy(bx, 106)
        d.multi_cell(zone_w, 5.5, _t(lbl), align="C")
        # barra de progreso sutil
        pct = 100 if "100" in val or "432" in val else (90 if "90" in val else 83)
        d.progress_bar(bx + 10, 128, zone_w - 20, 3, pct, col, (18, 28, 48))

    # Separador horizontal
    d.hbar(138, 0.5, _GREY2, 20, 257)

    # Fila de badges de stack — como Apple "compatible with"
    d.set_font("Helvetica", "", 8)
    d.set_text_color(*_GREY)
    d.set_xy(0, 144)
    d.cell(W, 6, "Evaluacion reproducible, sin conexion real a Supabase. Stack completo en produccion.", align="C")

    # Chips de tecnologia
    techs = ["Claude Opus 4.7", "Sonnet 4.6", "Haiku 4.5", "FastAPI", "Flutter", "Supabase", "Pytest"]
    tx = (W - sum(len(t) * 5.5 + 16 for t in techs)) / 2
    for tech in techs:
        tw = d.badge(tech, tx, 156, bg=(14, 28, 50), fg=_GREY, size=7.5)
        tx += tw + 2

    # Linea inferior
    d.panel(0, H - 3, W, 3, _NEON)
    d.slide_footer(6)


def s07_demo(d: Deck):
    d.add_page()
    d.fill(_BG)
    d.dot_grid(0, 60, W, 160, step=10, size=0.4, color=(12, 20, 38))

    d.panel(0, 0, W, 18, _BG2)
    d.hbar(18, 1.5, _BLUE)
    d.label("Demo en vivo  |  5 pasos, 5 minutos", 12, 5, 200, 8, _BLUE)

    d.heading("El sistema funciona en tiempo real.\nNo es una simulacion.", 12, 24, 240, 24, _WHITE)

    # Linea de timeline
    d.hbar(118, 1, _BG2, 30, 250)

    steps = [
        ("1", "make advance N=2",
         "Simula que pasaron 2 dias. Aparecen nuevos productos CRITICOS en el dashboard de Flutter.",
         _NEON),
        ("2", "Telegram: alerta",
         "Chuwi envia un mensaje proactivo sin que nadie lo pida: nuevo CRITICO detectado.",
         _G3),
        ("3", "/estado",
         "Dashboard completo: semaforo, acciones pendientes, valor en riesgo, briefs recientes.",
         _BLUE),
        ("4", "Foto del producto",
         "Chuwi analiza una foto real. Vision + estado + accion recomendada en menos de 3 segundos.",
         _AMBER),
        ("5", "/informe",
         "PDF del brief de hoy generado por Kuine y enviado directamente en el chat de Telegram.",
         _PURPLE),
    ]

    for i, (num, cmd, desc, col) in enumerate(steps):
        bx = 14 + i * 56
        # circulo numerado en linea de tiempo
        d.circle(bx + 22, 118, 9, col)
        d.set_font("Helvetica", "B", 12)
        d.set_text_color(*_WHITE if col != _AMBER else _BG)
        d.set_xy(bx + 12, 113)
        d.cell(20, 10, num, align="C")

        # caja descripcion
        d.panel(bx, 132, 50, 55, _BG2, radius=2)
        d.panel(bx, 132, 50, 2.5, col)

        d.set_font("Helvetica", "B", 8)
        d.set_text_color(*col)
        d.set_xy(bx + 3, 137)
        d.multi_cell(44, 5, _t(cmd))

        d.set_font("Helvetica", "", 7.5)
        d.set_text_color(*_GREY)
        d.set_xy(bx + 3, 148)
        d.multi_cell(44, 4.5, _t(desc))

    # Nota
    d.hbar(192, 0.4, _GREY2)
    d.body("Todos los pasos son reales y ejecutables en el momento de la presentacion. El sistema esta desplegado y funcionando.", 12, 195, 268, 8, _GREY2)

    d.slide_footer(7)


def s08_stack(d: Deck):
    d.add_page()
    d.fill(_BG)

    d.panel(0, 0, W, 18, _BG2)
    d.hbar(18, 1.5, _PURPLE)
    d.label("Stack tecnico", 12, 5, 200, 8, _PURPLE)

    d.heading("Tecnologia de produccion,\nno de laboratorio.", 12, 24, 190, 24, _WHITE)

    cols_data = [
        {
            "title": "IA & Agentes", "color": _NEON,
            "items": [
                ("Claude Opus 4.7",     "Orquestador Kuine — 16 tools"),
                ("Claude Sonnet 4.6",   "7 agentes — reasoning + streaming"),
                ("Claude Haiku 4.5",    "3 agentes — tareas rapidas"),
                ("Extended thinking",   "Decisiones criticas con razonamiento"),
                ("Tool use nativo",     "python-anthropic SDK oficial"),
                ("Vision multimodal",   "claude-3-5-sonnet para fotos"),
            ],
        },
        {
            "title": "Backend", "color": _BLUE,
            "items": [
                ("FastAPI",             "Puerto 8001, async, OpenAPI auto"),
                ("APScheduler",         "Jobs automaticos cada 30 min"),
                ("Supabase",            "PostgreSQL + Auth + Realtime"),
                ("python-telegram-bot", "v22.7, async, streaming"),
                ("fpdf2",               "Generacion de PDFs profesionales"),
                ("Slowapi",             "Rate limiting en endpoints"),
            ],
        },
        {
            "title": "App & QA", "color": _PURPLE,
            "items": [
                ("Flutter 3.x",         "Android, iOS y Web"),
                ("Riverpod",            "Estado reactivo, sin boilerplate"),
                ("Go Router",           "Navegacion declarativa"),
                ("Mobile Scanner",      "Escaneo de codigos de barras"),
                ("Pytest",              "800 tests, mocks de Supabase"),
                ("share_plus",          "Compartir PDFs desde la app"),
            ],
        },
    ]

    for ci, col in enumerate(cols_data):
        cx = 12 + ci * 96
        cw = 89
        d.panel(cx, 64, cw, 130, _BG2, radius=2)
        d.panel(cx, 64, cw, 3, col["color"])

        d.set_font("Helvetica", "B", 11)
        d.set_text_color(*col["color"])
        d.set_xy(cx + 5, 70)
        d.cell(cw - 10, 7, _t(col["title"]))

        d.hbar(79, 0.4, _GREY2, cx + 5, cw - 10)

        for ii, (name, desc) in enumerate(col["items"]):
            iy = 82 + ii * 18
            d.circle(cx + 8, iy + 5, 2, col["color"])
            d.set_font("Helvetica", "B", 8)
            d.set_text_color(*_WHITE)
            d.set_xy(cx + 13, iy + 1)
            d.cell(cw - 18, 5, _t(name))
            d.set_font("Helvetica", "", 7)
            d.set_text_color(*_GREY)
            d.set_xy(cx + 13, iy + 7)
            d.cell(cw - 18, 5, _t(desc))

    # Panel derecho extra
    d.panel(300, 64, 0, 130, _PURPLE)  # decoracion

    d.slide_footer(8)


def s09_esg(d: Deck):
    d.add_page()
    d.fill(_BG)
    d.dot_grid(0, 0, W, H, step=10, size=0.45, color=(10, 20, 35))

    d.panel(0, 0, W, 18, _BG2)
    d.hbar(18, 1.5, _TEAL)
    d.label("Impacto ESG & Social", 12, 5, 200, 8, _TEAL)

    d.heading("Menos merma =\nmenos CO2 + mas dinero.", 12, 25, 200, 28, _WHITE)

    # 4 bloques impacto
    impacts = [
        {
            "icon": "2.5 kg", "icon_lbl": "CO2 evitado\npor kg merma reducida",
            "desc": "Cada kilo de alimento no desperdiciado evita la emision de 2.5 kg de CO2 equivalente segun estudios de la FAO.",
            "color": _TEAL,
        },
        {
            "icon": "35%", "icon_lbl": "Deduccion fiscal\nLey 49/2002",
            "desc": "Las donaciones a bancos de alimentos generan una deduccion fiscal del 35% del valor donado en el impuesto de sociedades.",
            "color": _G3,
        },
        {
            "icon": "Auto", "icon_lbl": "Donacion propuesta\nsin intervencion humana",
            "desc": "Kuine propone donar cuando un producto lleva mas de 6h en estado CRITICO y el stock supera 5 unidades.",
            "color": _NEON,
        },
        {
            "icon": "PDF", "icon_lbl": "Informe ESG\nautomatico semanal",
            "desc": "El sistema genera automaticamente el informe de impacto ambiental con CO2 evitado, valor donado y deduccion calculada.",
            "color": _BLUE,
        },
    ]

    for i, imp in enumerate(impacts):
        bx = 12 + (i % 2) * 142
        by = 80 + (i // 2) * 66
        bw, bh = 132, 58

        d.panel(bx, by, bw, bh, _BG2, radius=2)
        d.panel(bx, by, 3, bh, imp["color"])

        d.set_font("Helvetica", "B", 22)
        d.set_text_color(*imp["color"])
        d.set_xy(bx + 10, by + 6)
        d.cell(50, 13, _t(imp["icon"]))

        d.set_font("Helvetica", "B", 8)
        d.set_text_color(*_WHITE)
        d.set_xy(bx + 10, by + 21)
        d.multi_cell(60, 4.5, _t(imp["icon_lbl"]))

        d.hbar(by + 8, 0.3, _GREY2, bx + 68, bw - 75)
        d.set_font("Helvetica", "", 7.5)
        d.set_text_color(*_GREY)
        d.set_xy(bx + 70, by + 10)
        d.multi_cell(bw - 78, 4.8, _t(imp["desc"]))

    d.slide_footer(9)


def s10_cierre(d: Deck):
    d.add_page()
    # Fondo: degradado oscuro profundo
    d.gradient_panel(0, 0, W, H, (2, 8, 18), _BG, steps=28, vertical=True)

    # Anillos concentricos muy sutiles
    for r, lw, grey in [(100, 0.18, 25), (78, 0.25, 35), (56, 0.35, 48), (34, 0.5, 65), (16, 0.8, 90)]:
        d.ring(W // 2, H // 2, r, lw, (0, grey, int(grey * 0.7)))

    # Punto central neon
    d.circle(W // 2, H // 2, 4, _NEON)

    # Linea neon arriba y abajo
    d.panel(0, 0, W, 3, _NEON)
    d.panel(0, H - 3, W, 3, _NEON)

    # Nombre — ENORME, centrado verticalmente
    d.set_font("Helvetica", "B", 72)
    d.set_text_color(*_WHITE)
    d.set_xy(0, 35)
    d.cell(W, 38, "MermaOps", align="C")

    # Tagline minimalista
    d.set_font("Helvetica", "", 13)
    d.set_text_color(*_NEON)
    d.set_xy(0, 80)
    d.cell(W, 8, "La IA que hace que los supermercados desperdicien menos.", align="C")

    # Tres cifras — Apple "one more thing" stats
    d.hbar(96, 0.4, _GREY2, 50, 197)

    kpis = [("11", "agentes", _NEON), ("432", "tests OK", _G3), ("100%", "robustez", _BLUE)]
    for i, (val, lbl, col) in enumerate(kpis):
        bx = 60 + i * 62
        d.set_font("Helvetica", "B", 30)
        d.set_text_color(*col)
        d.set_xy(bx, 102)
        d.cell(50, 16, _t(val), align="C")
        d.set_font("Helvetica", "", 7.5)
        d.set_text_color(*_GREY)
        d.set_xy(bx, 120)
        d.cell(50, 5, _t(lbl), align="C")

    d.hbar(132, 0.4, _GREY2, 50, 197)

    # Autor centrado
    d.set_font("Helvetica", "B", 11)
    d.set_text_color(*_WHITE)
    d.set_xy(0, 138)
    d.cell(W, 7, "Alvaro Ferrer Muro", align="C")

    d.set_font("Helvetica", "", 7.5)
    d.set_text_color(*_GREY2)
    d.set_xy(0, 147)
    d.cell(W, 6, "github.com/alvaroferrer1/Tfm  |  @ChuwiMermaOpsBot", align="C")

    # "Gracias" final — enorme, centrado en la zona inferior
    d.set_font("Helvetica", "B", 28)
    d.set_text_color(*_NEON)
    d.set_xy(0, 162)
    d.cell(W, 16, "Gracias. Preguntas.", align="C")


# ============================================================  MAIN  =========

def generate_presentation(output_path: str | None = None) -> bytes:
    d = Deck()
    s01_portada(d)
    s02_problema(d)
    s03_solucion(d)
    s04_arquitectura(d)
    s05_chuwi(d)
    s06_resultados(d)
    s07_demo(d)
    s08_stack(d)
    s09_esg(d)
    s10_cierre(d)

    buf = io.BytesIO()
    d.output(buf)
    data = buf.getvalue()

    if output_path:
        Path(output_path).write_bytes(data)
        print(f"PDF generado: {output_path}  ({len(data) // 1024} KB, 10 slides)")

    return data


if __name__ == "__main__":
    out = Path(__file__).parent.parent.parent / "MermaOps_Presentacion_TFM.pdf"
    generate_presentation(str(out))
