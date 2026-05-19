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
        self.panel(x, y, w, h, bg, radius=h / 2)
        filled = max(h, w * pct / 100)
        self.panel(x, y, filled, h, color, radius=h / 2)

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
    d.fill(_BG)
    d.dot_grid(0, 0, W, H, step=9, size=0.5, color=(15, 25, 45))

    # Panel izquierdo con degradado
    d.gradient_panel(0, 0, 115, H, _G1, _BG, steps=18)
    d.vbar(115, H, 2.5, color=_NEON)

    # Anillos decorativos centrados en panel izquierdo
    d.ring(58, 105, 42, 0.6, (0, 80, 55))
    d.ring(58, 105, 55, 0.3, (0, 60, 40))
    d.ring(58, 105, 68, 0.2, (0, 45, 30))

    # Logo / nombre
    d.set_font("Helvetica", "B", 48)
    d.set_text_color(*_WHITE)
    d.set_xy(0, 28)
    d.cell(115, 26, "MermaOps", align="C")

    # Punto verde bajo nombre
    d.circle(58, 60, 1.8, _NEON)

    d.set_font("Helvetica", "", 11)
    d.set_text_color(*_G3)
    d.set_xy(0, 64)
    d.multi_cell(115, 6.5, "Sistema multi-agente de IA\npara reduccion de merma\nalimentaria", align="C")

    # Tags tech
    tags = ["Claude Opus 4.7", "FastAPI", "Flutter", "Supabase", "11 agentes"]
    ty = 112
    for tag in tags:
        tw = d.badge(tag, 10, ty, bg=(2, 40, 28), fg=_NEON, size=8)
        ty += 14

    # ---- Derecha -----------------------------------------------------------
    # Titulo del trabajo
    d.label("Trabajo Fin de Master  |  Master en IA Generativa & Innovation", 128, 22, 160, 8)

    d.set_font("Helvetica", "B", 30)
    d.set_text_color(*_WHITE)
    d.set_xy(128, 34)
    d.multi_cell(162, 16, "Inteligencia Artificial\naplicada a la reduccion\nde merma en supermercados", align="L")

    d.hbar(96, 1, _NEON, 128, 162)

    d.sub("Presentado por:", 128, 102, 160, 9, _GREY)
    d.set_font("Helvetica", "B", 16)
    d.set_text_color(*_WHITE)
    d.set_xy(128, 112)
    d.cell(160, 9, "Alvaro Ferrer Margalef")

    d.sub(date.today().strftime("%B %Y"), 128, 124, 160, 10, _GREY)

    # Powered by
    d.label("Powered by Anthropic Claude API", 128, H - 22, 160, 7, _GREY2, False)
    d.label("github.com/alvaroferrer1/Tfm", 128, H - 15, 160, 7, _GREY2, False)

    # Metricas rapidas abajo-derecha
    kpis = [("11", "Agentes"), ("323", "Tests"), ("100%", "Robustez")]
    for i, (v, l) in enumerate(kpis):
        bx = 207 + i * 30
        d.set_font("Helvetica", "B", 18)
        d.set_text_color(*_NEON)
        d.set_xy(bx, 148)
        d.cell(28, 10, _t(v), align="C")
        d.set_font("Helvetica", "", 7)
        d.set_text_color(*_GREY)
        d.set_xy(bx, 159)
        d.cell(28, 5, _t(l), align="C")


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
        "11 agentes de IA trabajando en paralelo 24/7 sin supervision",
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

    d.panel(0, 0, W, 18, _BG2)
    d.hbar(18, 1.5, _NEON)
    d.label("Arquitectura multi-agente — Hub & Spoke", 12, 5, 200, 8, _NEON)

    d.heading("11 agentes. Un cerebro central.", 12, 22, 200, 22, _WHITE)

    # ---- Hub Kuine ---------------------------------------------------------
    cx, cy = 148, 126
    # anillos decorativos
    d.ring(cx, cy, 52, 0.3, (0, 50, 35))
    d.ring(cx, cy, 38, 0.4, (0, 65, 48))

    # Hexagono central Kuine
    d.hex_shape(cx, cy, 22, _G1)
    d.hex_shape(cx, cy, 22, _NEON, "D")

    d.set_draw_color(*_NEON)
    d.set_line_width(0.8)

    d.set_font("Helvetica", "B", 13)
    d.set_text_color(*_WHITE)
    d.set_xy(cx - 18, cy - 8)
    d.cell(36, 7, "KUINE", align="C")
    d.set_font("Helvetica", "", 6.5)
    d.set_text_color(*_NEON)
    d.set_xy(cx - 18, cy + 1)
    d.cell(36, 5, "Opus 4.7", align="C")
    d.set_xy(cx - 18, cy + 7)
    d.cell(36, 5, "25 tools", align="C")

    # ---- Agentes alrededor -------------------------------------------------
    agents = [
        ("Chuwi",      "Sonnet 4.6", "Telegram", _G3,     90),
        ("Evaluador",  "Sonnet 4.6", "Score",     _BLUE,   140),
        ("Validador",  "Sonnet 4.6", "100%",      _BLUE,   190),
        ("Consenso",   "Son. x3",    ">=90",      _BLUE,   240),
        ("Predictor",  "Haiku 4.5",  "Tiempo",    _PURPLE, 290),
        ("Vision",     "claude-3-5", "Fotos",     _PURPLE, 340),
        ("Precio",     "Haiku 4.5",  "EUR",       _AMBER,  30),
        ("Stock",      "Haiku 4.5",  "Repos.",    _AMBER,  0),
        ("Notificador","Sonnet 4.6", "Alertas",   _RED,    310),
        ("Reportero",  "Sonnet 4.6", "Briefs",    _TEAL,   50),
    ]

    r_orbit = 70
    for name, model, role, col, deg in agents:
        a = math.radians(deg)
        ax = cx + r_orbit * math.cos(a)
        ay = cy + r_orbit * math.sin(a)

        # linea de conexion
        # punto en borde del hexagono central (radio 22)
        inner_x = cx + 22 * math.cos(a)
        inner_y = cy + 22 * math.sin(a)
        # punto en borde de la caja agente (radio aprox 10)
        outer_x = ax - 10 * math.cos(a)
        outer_y = ay - 10 * math.sin(a)
        d.set_draw_color(*col)
        d.set_line_width(0.5)
        d.line(inner_x, inner_y, outer_x, outer_y)

        # caja del agente
        bw, bh = 38, 20
        bx = ax - bw / 2
        by = ay - bh / 2
        d.panel(bx, by, bw, bh, _BG2, radius=1)
        d.panel(bx, by, bw, 2, col)

        d.set_font("Helvetica", "B", 7.5)
        d.set_text_color(*_WHITE)
        d.set_xy(bx + 1, by + 4)
        d.cell(bw - 2, 5, _t(name), align="C")

        d.set_font("Helvetica", "", 5.5)
        d.set_text_color(*_GREY)
        d.set_xy(bx + 1, by + 10)
        d.cell(bw - 2, 4, _t(model), align="C")

        d.set_font("Helvetica", "B", 5.5)
        d.set_text_color(*col)
        d.set_xy(bx + 1, by + 14)
        d.cell(bw - 2, 4, _t(role), align="C")

    # Leyenda colores
    legend = [("Sonnet 4.6", _BLUE), ("Haiku 4.5", _AMBER), ("Opus 4.7", _NEON),
              ("Multimodal", _PURPLE), ("Especial", _RED)]
    for i, (lbl, col) in enumerate(legend):
        lx = 238 + (i % 3) * 18
        ly = 178 + (i // 3) * 10
        d.circle(lx + 2, ly + 3, 2, col)
        d.set_font("Helvetica", "", 6)
        d.set_text_color(*_GREY)
        d.set_xy(lx + 6, ly)
        d.cell(30, 6, _t(lbl))

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

    d.panel(0, 0, W, 18, _BG2)
    d.hbar(18, 1.5, _NEON)
    d.label("Resultados cuantitativos", 12, 5, 200, 8, _NEON)

    d.heading("Numeros que no dejan\nlugar a dudas.", 12, 24, 190, 26, _WHITE)

    # ---- Grid 2x2 de KPIs grandes ------------------------------------------
    metrics = [
        {
            "value": "323/323", "unit": "", "label": "Tests automatizados\nen < 1 segundo",
            "sub": "Pytest, sin conexion real a Supabase", "color": _NEON, "pct": 100,
        },
        {
            "value": "100%", "unit": "", "label": "Robustez adversarial\n23 ataques neutralizados",
            "sub": "Prompt injection, jailbreak, confusion de idiomas...", "color": _G3, "pct": 100,
        },
        {
            "value": "+83pp", "unit": "", "label": "Mejora sobre baseline\naleatorio (16.7%)",
            "sub": "El sistema clasifica el 100% de casos correctamente", "color": _AMBER, "pct": 83,
        },
        {
            "value": "90.2%", "unit": "", "label": "Mejora multi-agente\nvs agente unico",
            "sub": "Patron Hub & Spoke con validacion y consenso", "color": _BLUE, "pct": 90,
        },
    ]

    for i, m in enumerate(metrics):
        col_i = i % 2
        row_i = i // 2
        bx = 14 + col_i * 140
        by = 76 + row_i * 64
        bw, bh = 132, 56

        d.panel(bx, by, bw, bh, _BG2, radius=2)
        d.panel(bx, by, bw, 2.5, m["color"])

        # valor principal
        vsize = 32 if len(_t(m["value"])) <= 5 else 24
        d.set_font("Helvetica", "B", vsize)
        d.set_text_color(*m["color"])
        d.set_xy(bx + 6, by + 6)
        d.cell(bw - 12, vsize * 0.6, _t(m["value"] + m["unit"]))

        # label
        d.set_font("Helvetica", "B", 9)
        d.set_text_color(*_WHITE)
        d.set_xy(bx + 6, by + 30)
        d.multi_cell(bw - 12, 5.5, _t(m["label"]))

        # sub
        d.set_font("Helvetica", "", 7)
        d.set_text_color(*_GREY)
        d.set_xy(bx + 6, by + 46)
        d.multi_cell(bw - 12, 4, _t(m["sub"]))

        # barra de progreso
        d.progress_bar(bx + 6, by + bh - 6, bw - 12, 3, m["pct"], m["color"], (20, 32, 52))

    # Panel derecho
    d.panel(292, 76, 3, 130, _NEON)
    d.ring(290, 168, 25, 0.4, (0, 60, 40))

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
                ("Claude Opus 4.7",     "Orquestador Kuine — 25 tools"),
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
                ("Pytest",              "323 tests, mocks de Supabase"),
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
    d.fill(_BG)

    # Fondo con patron de circulos concentricos
    for r in [30, 55, 80, 105, 130, 155]:
        d.ring(W / 2, H / 2, r, 0.25, (0, 40 + r // 4, 30))

    # Degradado central
    d.gradient_panel(50, 20, 197, 170, (3, 35, 25), _BG, steps=20)

    # Marco neon
    d.set_draw_color(*_NEON)
    d.set_line_width(1)
    d.rect(40, 18, 217, 174, "D")

    # Linea superior de color
    d.hbar(18, 3, _NEON, 40, 217)

    # Titulo
    d.set_font("Helvetica", "B", 56)
    d.set_text_color(*_WHITE)
    d.set_xy(40, 26)
    d.cell(217, 30, "MermaOps", align="C")

    d.set_font("Helvetica", "", 14)
    d.set_text_color(*_NEON)
    d.set_xy(40, 60)
    d.cell(217, 9, "La IA que hace que los supermercados desperdicien menos", align="C")

    d.hbar(75, 0.8, _G2, 60, 177)

    # Bullets resumen
    bullets = [
        "11 agentes activos  |  Kuine orquesta, Chuwi ejecuta",
        "323 tests en verde  |  listo para produccion real",
        "100% robustez adversarial  |  23 ataques neutralizados",
        "Stack completo: Claude API + FastAPI + Flutter + Supabase",
    ]
    for i, b in enumerate(bullets):
        d.circle(62, 86 + i * 15, 2.5, _NEON)
        d.set_font("Helvetica", "", 11)
        d.set_text_color(*_OFF_WHITE)
        d.set_xy(70, 82 + i * 15)
        d.cell(177, 8, _t(b), align="C")

    # Cierre
    d.hbar(150, 0.8, _G2, 60, 177)
    d.set_font("Helvetica", "B", 20)
    d.set_text_color(*_NEON)
    d.set_xy(40, 154)
    d.cell(217, 12, "Gracias. Preguntas.", align="C")

    d.set_font("Helvetica", "", 9)
    d.set_text_color(*_GREY)
    d.set_xy(40, 168)
    d.cell(217, 7, "github.com/alvaroferrer1/Tfm  |  @ChuwiMermaOpsBot  |  Alvaro Ferrer", align="C")

    # Puntos decorativos en esquinas
    for px, py in [(42, 20), (255, 20), (42, 190), (255, 190)]:
        d.circle(px, py, 3, _NEON)


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
