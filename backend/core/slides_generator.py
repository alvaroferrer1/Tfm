"""
slides_generator.py — Genera las diapositivas del TFM en PDF.

Uso:
    python -m backend.core.slides_generator
    → Crea MermaOps_Presentacion_TFM.pdf en el directorio raíz.
"""
from __future__ import annotations
import io
from datetime import date
from pathlib import Path

import unicodedata
from fpdf import FPDF, XPos, YPos

# ── Paleta ────────────────────────────────────────────────────────────────────
_BG           = (10, 15, 25)       # casi negro azulado
_GREEN_DARK   = (4, 80, 60)
_GREEN_MID    = (6, 148, 100)
_GREEN_LIGHT  = (100, 220, 170)
_ACCENT       = (0, 220, 130)      # verde neón
_WHITE        = (255, 255, 255)
_GREY_LIGHT   = (200, 210, 220)
_GREY_MID     = (130, 145, 165)
_RED          = (220, 60, 60)
_AMBER        = (220, 160, 30)
_BLUE         = (50, 120, 240)
_PURPLE       = (130, 60, 220)

W, H = 297, 210   # A4 apaisado


def _s(text: str) -> str:
    """Limpia texto a ASCII puro para Helvetica."""
    text = str(text)
    for src, dst in [
        ("€", "EUR"), ("°", "o"), ("·", "-"), ("—", "-"), ("–", "-"),
        ("«", '"'), ("»", '"'), ("…", "..."),
    ]:
        text = text.replace(src, dst)
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if ord(c) < 128)


class _Slide(FPDF):
    """PDF apaisado con helpers para diapositivas."""

    def __init__(self):
        super().__init__(orientation="L", unit="mm", format="A4")
        self.set_auto_page_break(auto=False)
        self.set_margins(0, 0, 0)

    # ── Fondos ───────────────────────────────────────────────────────────────

    def bg_dark(self):
        self.set_fill_color(*_BG)
        self.rect(0, 0, W, H, "F")

    def bg_gradient_side(self, left_color=_GREEN_DARK, right_color=_BG):
        """Fondo con panel izquierdo de color."""
        self.set_fill_color(*right_color)
        self.rect(0, 0, W, H, "F")
        self.set_fill_color(*left_color)
        self.rect(0, 0, 100, H, "F")

    def accent_bar(self, y: float, h: float = 1.5, color=_ACCENT):
        self.set_fill_color(*color)
        self.rect(0, y, W, h, "F")

    def top_bar(self, color=_GREEN_DARK, height: float = 16):
        self.set_fill_color(*color)
        self.rect(0, 0, W, height, "F")

    def bottom_bar(self, label: str = "", color=_GREEN_DARK, height: float = 10):
        self.set_fill_color(*color)
        self.rect(0, H - height, W, height, "F")
        if label:
            self.set_font("Helvetica", "", 7)
            self.set_text_color(*_GREY_LIGHT)
            self.set_xy(0, H - height + 1.5)
            self.cell(W, 7, _s(label), align="C")

    # ── Tipografía ────────────────────────────────────────────────────────────

    def h1(self, text: str, x: float, y: float, w: float = 200,
           color=_WHITE, size: int = 38, align: str = "L"):
        self.set_font("Helvetica", "B", size)
        self.set_text_color(*color)
        self.set_xy(x, y)
        self.multi_cell(w, size * 0.45, _s(text), align=align)

    def h2(self, text: str, x: float, y: float, w: float = 180,
           color=_ACCENT, size: int = 20, align: str = "L"):
        self.set_font("Helvetica", "B", size)
        self.set_text_color(*color)
        self.set_xy(x, y)
        self.multi_cell(w, size * 0.55, _s(text), align=align)

    def body(self, text: str, x: float, y: float, w: float = 180,
             color=_GREY_LIGHT, size: int = 11, align: str = "L"):
        self.set_font("Helvetica", "", size)
        self.set_text_color(*color)
        self.set_xy(x, y)
        self.multi_cell(w, size * 0.55, _s(text), align=align)

    def bullet(self, text: str, x: float, y: float, w: float = 160,
               color=_WHITE, dot_color=_ACCENT, size: int = 12):
        self.set_fill_color(*dot_color)
        self.ellipse(x, y + size * 0.18, 2.5, 2.5, "F")
        self.body(text, x + 6, y, w, color, size)

    def tag(self, text: str, x: float, y: float,
            bg=_GREEN_DARK, fg=_ACCENT, size: int = 9):
        w = len(_s(text)) * size * 0.52 + 6
        self.set_fill_color(*bg)
        self.rect(x, y, w, size * 0.9 + 4, "F")
        self.set_font("Helvetica", "B", size)
        self.set_text_color(*fg)
        self.set_xy(x + 3, y + 2)
        self.cell(w - 6, size * 0.9, _s(text))
        return w + 3

    def kpi_box(self, value: str, label: str, x: float, y: float,
                w: float = 55, h: float = 30, val_color=_ACCENT):
        self.set_fill_color(20, 30, 45)
        self.rect(x, y, w, h, "F")
        self.set_fill_color(*val_color)
        self.rect(x, y, w, 1.5, "F")
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(*val_color)
        self.set_xy(x, y + 4)
        self.cell(w, 12, _s(value), align="C")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_GREY_MID)
        self.set_xy(x, y + 18)
        self.cell(w, 8, _s(label), align="C")

    def slide_num(self, n: int, total: int):
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_GREY_MID)
        self.set_xy(W - 20, H - 8)
        self.cell(15, 6, f"{n} / {total}", align="R")


# ── SLIDES ────────────────────────────────────────────────────────────────────

TOTAL = 10


def _slide_portada(pdf: _Slide):
    pdf.add_page()
    pdf.bg_dark()

    # Panel verde izquierdo
    pdf.set_fill_color(*_GREEN_DARK)
    pdf.rect(0, 0, 105, H, "F")

    # Borde neón vertical
    pdf.set_fill_color(*_ACCENT)
    pdf.rect(105, 0, 2, H, "F")

    # Logo / nombre sistema
    pdf.set_font("Helvetica", "B", 52)
    pdf.set_text_color(*_WHITE)
    pdf.set_xy(8, 30)
    pdf.cell(88, 28, "MermaOps", align="C")

    # Subtítulo
    pdf.set_font("Helvetica", "", 13)
    pdf.set_text_color(*_GREEN_LIGHT)
    pdf.set_xy(8, 62)
    pdf.multi_cell(88, 7, "Sistema multi-agente de IA\npara reduccion de merma\nalimentaria", align="C")

    # Tags en panel izquierdo
    tags = ["Claude Opus 4.7", "FastAPI", "Flutter", "Supabase"]
    ty = 100
    for t in tags:
        xo = 12
        pdf.tag(t, xo, ty, bg=(0, 50, 35), fg=_ACCENT, size=9)
        ty += 13

    # Título TFM (derecha)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*_ACCENT)
    pdf.set_xy(115, 28)
    pdf.multi_cell(170, 8, "Trabajo Fin de Master", align="L")

    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*_WHITE)
    pdf.set_xy(115, 40)
    pdf.multi_cell(170, 11,
        "Inteligencia Artificial aplicada a la\nreduccion de merma en supermercados",
        align="L")

    # Línea separadora
    pdf.accent_bar(80, 1, _GREEN_MID)

    # Datos
    pdf.body("Master en IA Generativa & Innovation", 115, 86, 170, _GREY_LIGHT, 11)
    pdf.body("Alvaro Ferrer  |  " + date.today().strftime("%B %Y"), 115, 95, 170, _GREY_MID, 10)

    # Powered by
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*_GREY_MID)
    pdf.set_xy(115, H - 22)
    pdf.cell(170, 6, "Powered by Anthropic Claude API", align="L")

    pdf.slide_num(1, TOTAL)


def _slide_problema(pdf: _Slide):
    pdf.add_page()
    pdf.bg_dark()
    pdf.top_bar(_GREEN_DARK, 14)

    # Cabecera
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_ACCENT)
    pdf.set_xy(12, 3)
    pdf.cell(100, 8, "EL PROBLEMA")

    pdf.h1("El desperdicio alimentario\nes un problema resuelto... mal.", 12, 20, 180, _WHITE, 28)
    pdf.accent_bar(68, 1.5)

    # Estadísticas grandes
    stats = [
        ("10 kg", "por habitante/anio en Espana"),
        ("2-5%", "ingresos perdidos por merma"),
        ("20%", "del total generado en distribucion"),
        ("1/3", "de toda la comida se desperdicia"),
    ]
    for i, (val, lbl) in enumerate(stats):
        pdf.kpi_box(val, lbl, 12 + i * 70, 80, 62, 38, _RED if i < 2 else _AMBER)

    pdf.body(
        "Los supermercados gestionan la merma de forma reactiva: revisan caducidades a mano,\n"
        "toman decisiones sin datos y pierden miles de euros al mes en productos que podrian\n"
        "haberse vendido, rebajado o donado a tiempo.",
        12, 128, 270, _GREY_LIGHT, 11
    )

    pdf.bottom_bar("MermaOps — TFM Alvaro Ferrer", _GREEN_DARK, 10)
    pdf.slide_num(2, TOTAL)


def _slide_solucion(pdf: _Slide):
    pdf.add_page()
    pdf.bg_dark()
    pdf.top_bar(_GREEN_DARK, 14)

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_ACCENT)
    pdf.set_xy(12, 3)
    pdf.cell(100, 8, "LA SOLUCION")

    pdf.h1("MermaOps: el primer sistema\nmulti-agente para merma alimentaria.", 12, 20, 200, _WHITE, 26)
    pdf.accent_bar(66, 1.5)

    bullets = [
        "Sistema de 11 agentes de IA que trabajan en paralelo 24/7, sin supervision humana",
        "Kuine (Opus 4.7) orquesta todos los agentes y toma decisiones de rebajar, donar o retirar",
        "Chuwi es el agente de campo: responde en Telegram, analiza fotos y envia alertas proactivas",
        "Prediccion meteorologica, vision por computador, calculo de precios y generacion de informes PDF",
        "Reduccion de merma medible: el sistema evalua, valida y ejecuta acciones en minutos",
    ]
    for i, b in enumerate(bullets):
        pdf.bullet(b, 12, 76 + i * 22, 265, _WHITE, _ACCENT, 11)

    # Panel derecho con diferencial
    pdf.set_fill_color(15, 25, 40)
    pdf.rect(200, 68, 88, 110, "F")
    pdf.set_fill_color(*_ACCENT)
    pdf.rect(200, 68, 88, 2, "F")
    pdf.h2("vs. competencia", 204, 74, 80, _GREY_MID, 9)
    comps = [
        ("Winnow Vision", "solo vision, sin agentes"),
        ("Too Good To Go", "solo canal venta, no IA"),
        ("Wasteless", "pricing reactivo, sin orquestacion"),
        ("MermaOps", "IA completa, multi-agente, open"),
    ]
    for i, (name, desc) in enumerate(comps):
        col = _ACCENT if name == "MermaOps" else _GREY_MID
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*col)
        pdf.set_xy(204, 90 + i * 20)
        pdf.cell(80, 5, _s(name))
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*_GREY_MID)
        pdf.set_xy(204, 96 + i * 20)
        pdf.cell(80, 5, _s(desc))

    pdf.bottom_bar("MermaOps — TFM Alvaro Ferrer", _GREEN_DARK, 10)
    pdf.slide_num(3, TOTAL)


def _slide_arquitectura(pdf: _Slide):
    pdf.add_page()
    pdf.bg_dark()
    pdf.top_bar(_GREEN_DARK, 14)

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_ACCENT)
    pdf.set_xy(12, 3)
    pdf.cell(100, 8, "ARQUITECTURA")

    pdf.h1("11 agentes. Un cerebro. Cero merma.", 12, 20, 220, _WHITE, 26)
    pdf.accent_bar(55, 1.5)

    # Kuine box (centro)
    pdf.set_fill_color(*_GREEN_DARK)
    pdf.rect(110, 65, 77, 32, "F")
    pdf.set_fill_color(*_ACCENT)
    pdf.rect(110, 65, 77, 2, "F")
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*_WHITE)
    pdf.set_xy(110, 70)
    pdf.cell(77, 8, "KUINE", align="C")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_GREEN_LIGHT)
    pdf.set_xy(110, 80)
    pdf.cell(77, 5, "Orquestador - Claude Opus 4.7", align="C")
    pdf.set_xy(110, 86)
    pdf.cell(77, 5, "25 tools | hasta 20 iteraciones", align="C")

    # Agentes izquierda
    left_agents = [
        ("Evaluador", "Sonnet 4.6", _BLUE),
        ("Validador", "Sonnet 4.6", _BLUE),
        ("Predictor", "Haiku 4.5", _PURPLE),
        ("Vision", "claude-3-5-sonnet", _PURPLE),
        ("Consenso", "Sonnet 4.6 x3", _BLUE),
    ]
    for i, (name, model, col) in enumerate(left_agents):
        bx, by = 12, 62 + i * 22
        pdf.set_fill_color(15, 25, 42)
        pdf.rect(bx, by, 88, 16, "F")
        pdf.set_fill_color(*col)
        pdf.rect(bx, by, 3, 16, "F")
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_WHITE)
        pdf.set_xy(bx + 6, by + 3)
        pdf.cell(60, 5, _s(name))
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_GREY_MID)
        pdf.set_xy(bx + 6, by + 9)
        pdf.cell(60, 5, _s(model))
        # línea hacia Kuine
        cx = bx + 88
        cy = by + 8
        pdf.set_draw_color(*col)
        pdf.set_line_width(0.3)
        pdf.line(cx, cy, 110, 81)

    # Agentes derecha
    right_agents = [
        ("Chuwi", "Sonnet 4.6 — Telegram", _GREEN_MID),
        ("Precio", "Haiku 4.5", _AMBER),
        ("Stock", "Haiku 4.5", _AMBER),
        ("Notificador", "Sonnet 4.6", _RED),
        ("Reportero", "Sonnet 4.6", _BLUE),
    ]
    for i, (name, model, col) in enumerate(right_agents):
        bx, by = 200, 62 + i * 22
        pdf.set_fill_color(15, 25, 42)
        pdf.rect(bx, by, 88, 16, "F")
        pdf.set_fill_color(*col)
        pdf.rect(bx, by, 3, 16, "F")
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_WHITE)
        pdf.set_xy(bx + 6, by + 3)
        pdf.cell(60, 5, _s(name))
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_GREY_MID)
        pdf.set_xy(bx + 6, by + 9)
        pdf.cell(60, 5, _s(model))
        # línea desde Kuine
        pdf.set_draw_color(*col)
        pdf.line(187, 81, bx, by + 8)

    pdf.bottom_bar("MermaOps — TFM Alvaro Ferrer", _GREEN_DARK, 10)
    pdf.slide_num(4, TOTAL)


def _slide_chuwi(pdf: _Slide):
    pdf.add_page()
    pdf.bg_dark()

    # Panel izquierdo oscuro-verde
    pdf.set_fill_color(4, 20, 16)
    pdf.rect(0, 0, 120, H, "F")
    pdf.set_fill_color(*_ACCENT)
    pdf.rect(120, 0, 2, H, "F")

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_ACCENT)
    pdf.set_xy(12, 10)
    pdf.cell(100, 6, "CHUWI - EL AGENTE DE CAMPO")

    pdf.h1("No es un bot.\nEs un agente.", 12, 22, 100, _WHITE, 28)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*_GREEN_LIGHT)
    pdf.set_xy(12, 70)
    pdf.multi_cell(100, 6,
        "Un bot espera preguntas.\nChuwi monitoriza la tienda solo\ny avisa cuando algo cambia.")

    # Features izquierda
    features = [
        "Streaming en Telegram (texto progresivo)",
        "Analisis de fotos de productos",
        "Alertas proactivas sin que se le pregunte",
        "Memoria episodica entre sesiones",
        "Comandos /informe y /semana → PDF",
    ]
    for i, f in enumerate(features):
        pdf.bullet(f, 12, 105 + i * 14, 105, _GREY_LIGHT, _ACCENT, 9)

    # Derecha: ejemplo de mensaje Telegram
    pdf.set_fill_color(18, 30, 28)
    pdf.rect(130, 20, 155, 155, "F")
    pdf.set_fill_color(*_GREEN_DARK)
    pdf.rect(130, 20, 155, 10, "F")
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*_ACCENT)
    pdf.set_xy(134, 23)
    pdf.cell(100, 5, "@ChuwiMermaOpsBot")

    msg_lines = [
        ("  ALERTA CRITICA  ", _RED, True),
        ("", _WHITE, False),
        ("Merluza fresca — Pasillo 4", _WHITE, True),
        ("Caduca MANIANA | 6 unidades", _GREY_LIGHT, False),
        ("Valor en riesgo: 48 EUR", _AMBER, False),
        ("", _WHITE, False),
        ("Kuine recomienda:", _ACCENT, True),
        ("  Donar hoy antes de las 17h", _WHITE, False),
        ("  Banco de alimentos Caritas", _WHITE, False),
        ("", _WHITE, False),
        ("[Donar]  [Rebajar 50%]  [Retirar]", _GREEN_LIGHT, True),
    ]
    my = 36
    for line, color, bold in msg_lines:
        if not line:
            my += 5
            continue
        pdf.set_font("Helvetica", "B" if bold else "", 9)
        pdf.set_text_color(*color)
        pdf.set_xy(136, my)
        pdf.cell(145, 6, _s(line))
        my += 10

    pdf.slide_num(5, TOTAL)


def _slide_resultados(pdf: _Slide):
    pdf.add_page()
    pdf.bg_dark()
    pdf.top_bar(_GREEN_DARK, 14)

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_ACCENT)
    pdf.set_xy(12, 3)
    pdf.cell(100, 8, "RESULTADOS")

    pdf.h1("Numeros que hablan\npor si solos.", 12, 20, 180, _WHITE, 28)
    pdf.accent_bar(64, 1.5)

    # KPIs fila 1
    kpis1 = [
        ("323/323", "Tests automatizados", _ACCENT),
        ("< 1s", "Tiempo total de tests", _GREEN_MID),
        ("100%", "Robustez adversarial", _ACCENT),
        ("23/23", "Ataques neutralizados", _GREEN_MID),
    ]
    for i, (v, l, c) in enumerate(kpis1):
        pdf.kpi_box(v, l, 12 + i * 71, 74, 63, 35, c)

    # KPIs fila 2
    kpis2 = [
        ("+83pp", "Mejora vs. baseline", _ACCENT),
        ("11", "Agentes activos", _BLUE),
        ("90.2%", "Mejora multi-agente vs. single", _AMBER),
        ("< 5min", "Setup completo desde cero", _GREEN_MID),
    ]
    for i, (v, l, c) in enumerate(kpis2):
        pdf.kpi_box(v, l, 12 + i * 71, 120, 63, 35, c)

    # Nota metodológica
    pdf.body(
        "Evaluacion cuantitativa propia: 233 casos de prueba funcionales + 23 ataques adversariales.\n"
        "El sistema clasifica correctamente el 100% de los casos vs 16.7% del baseline aleatorio.\n"
        "Tests ejecutados en entorno real con mocks de Supabase para garantizar reproducibilidad.",
        12, 165, 270, _GREY_MID, 9
    )

    pdf.bottom_bar("MermaOps — TFM Alvaro Ferrer", _GREEN_DARK, 10)
    pdf.slide_num(6, TOTAL)


def _slide_demo(pdf: _Slide):
    pdf.add_page()
    pdf.bg_dark()
    pdf.top_bar(_GREEN_DARK, 14)

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_ACCENT)
    pdf.set_xy(12, 3)
    pdf.cell(100, 8, "DEMO EN VIVO")

    pdf.h1("5 minutos. Sistema real.\nDatos reales.", 12, 20, 220, _WHITE, 28)
    pdf.accent_bar(64, 1.5)

    steps = [
        ("1", "make advance N=2", "Simula que pasaron 2 dias — aparecen nuevos CRITICOS en el dashboard"),
        ("2", "Chuwi en Telegram", "Llega una alerta proactiva: 'Nuevo CRITICO detectado por Kuine'"),
        ("3", "/estado", "Dashboard completo con semaforo, acciones pendientes y valor en riesgo"),
        ("4", "Foto producto", "Chuwi analiza foto real con vision → estado + accion recomendada en 3s"),
        ("5", "/informe", "PDF del brief de hoy generado y enviado directamente en el chat"),
    ]
    for i, (num, cmd, desc) in enumerate(steps):
        bx, by = 12, 75 + i * 24
        # número
        pdf.set_fill_color(*_ACCENT)
        pdf.rect(bx, by, 10, 14, "F")
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_BG)
        pdf.set_xy(bx, by + 2)
        pdf.cell(10, 10, num, align="C")
        # comando
        pdf.set_fill_color(15, 25, 42)
        pdf.rect(bx + 12, by, 70, 14, "F")
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_GREEN_LIGHT)
        pdf.set_xy(bx + 15, by + 4)
        pdf.cell(64, 6, _s(cmd))
        # descripcion
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*_GREY_LIGHT)
        pdf.set_xy(bx + 88, by + 4)
        pdf.cell(195, 6, _s(desc))

    pdf.bottom_bar("MermaOps — TFM Alvaro Ferrer", _GREEN_DARK, 10)
    pdf.slide_num(7, TOTAL)


def _slide_stack(pdf: _Slide):
    pdf.add_page()
    pdf.bg_dark()
    pdf.top_bar(_GREEN_DARK, 14)

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_ACCENT)
    pdf.set_xy(12, 3)
    pdf.cell(100, 8, "STACK TECNICO")

    pdf.h1("Tecnologia de produccion,\nno de laboratorio.", 12, 20, 200, _WHITE, 26)
    pdf.accent_bar(60, 1.5)

    cols = [
        {
            "title": "IA & Agentes",
            "color": _ACCENT,
            "items": [
                "Claude API (Opus 4.7 / Sonnet 4.6 / Haiku 4.5)",
                "python-anthropic SDK — tool_use nativo",
                "Extended thinking para decisiones criticas",
                "Streaming en tiempo real para Chuwi",
                "Vision multimodal para escaneo de productos",
            ],
        },
        {
            "title": "Backend",
            "color": _BLUE,
            "items": [
                "FastAPI — puerto 8001, async nativo",
                "APScheduler — jobs automaticos cada 30min",
                "Supabase (PostgreSQL + Auth + Realtime)",
                "python-telegram-bot 22.7 async",
                "fpdf2 — generacion de PDFs profesionales",
            ],
        },
        {
            "title": "App movil",
            "color": _PURPLE,
            "items": [
                "Flutter 3.x — Android / iOS / Web",
                "Riverpod — estado reactivo",
                "Go Router — navegacion declarativa",
                "Mobile Scanner — escaneo de codigos de barras",
                "share_plus — compartir PDFs desde la app",
            ],
        },
    ]
    for ci, col in enumerate(cols):
        cx = 12 + ci * 96
        pdf.set_fill_color(12, 20, 35)
        pdf.rect(cx, 68, 89, 112, "F")
        pdf.set_fill_color(*col["color"])
        pdf.rect(cx, 68, 89, 2.5, "F")
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*col["color"])
        pdf.set_xy(cx + 4, 74)
        pdf.cell(80, 6, _s(col["title"]))
        for ii, item in enumerate(col["items"]):
            pdf.bullet(item, cx + 4, 86 + ii * 17, 82, _GREY_LIGHT, col["color"], 8)

    pdf.bottom_bar("MermaOps — TFM Alvaro Ferrer", _GREEN_DARK, 10)
    pdf.slide_num(8, TOTAL)


def _slide_esg(pdf: _Slide):
    pdf.add_page()
    pdf.bg_dark()
    pdf.top_bar(_GREEN_DARK, 14)

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_ACCENT)
    pdf.set_xy(12, 3)
    pdf.cell(100, 8, "IMPACTO ESG")

    pdf.h1("Reducir merma es\ntambien reducir CO2.", 12, 20, 200, _WHITE, 28)
    pdf.accent_bar(64, 1.5)

    impacts = [
        ("kg CO2 evitados", "por kg merma reducida: 2.5 kg CO2eq", _GREEN_MID),
        ("Deduccion fiscal", "Ley 49/2002: 35% del valor donado", _ACCENT),
        ("Banco de alimentos", "Donacion automatica propuesta por Kuine", _GREEN_LIGHT),
        ("Informe ESG", "Generado automaticamente cada semana", _BLUE),
    ]
    for i, (title, desc, color) in enumerate(impacts):
        bx = 12 + (i % 2) * 145
        by = 78 + (i // 2) * 52
        pdf.set_fill_color(10, 35, 22)
        pdf.rect(bx, by, 133, 42, "F")
        pdf.set_fill_color(*color)
        pdf.rect(bx, by, 133, 2.5, "F")
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*color)
        pdf.set_xy(bx + 6, by + 7)
        pdf.cell(120, 6, _s(title))
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_GREY_LIGHT)
        pdf.set_xy(bx + 6, by + 16)
        pdf.multi_cell(120, 5, _s(desc))

    pdf.body(
        "MermaOps no solo ahorra dinero — genera un registro auditado de cada donacion\n"
        "y calcula automaticamente la deduccion fiscal aplicable segun la normativa espanola.",
        12, 172, 270, _GREY_MID, 10
    )

    pdf.bottom_bar("MermaOps — TFM Alvaro Ferrer", _GREEN_DARK, 10)
    pdf.slide_num(9, TOTAL)


def _slide_cierre(pdf: _Slide):
    pdf.add_page()
    pdf.bg_dark()

    # Panel verde
    pdf.set_fill_color(*_GREEN_DARK)
    pdf.rect(0, 0, W, H, "F")

    # Patrón de puntos decorativo
    for row in range(0, H + 10, 12):
        for col in range(0, W + 10, 12):
            pdf.set_fill_color(0, 100, 70)
            pdf.ellipse(col, row, 1.5, 1.5, "F")

    # Overlay oscuro central
    pdf.set_fill_color(4, 40, 30)
    pdf.rect(30, 25, 237, 160, "F")
    pdf.set_fill_color(*_ACCENT)
    pdf.rect(30, 25, 237, 2, "F")
    pdf.rect(30, 183, 237, 2, "F")

    pdf.set_font("Helvetica", "B", 42)
    pdf.set_text_color(*_WHITE)
    pdf.set_xy(30, 40)
    pdf.cell(237, 22, "MermaOps", align="C")

    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(*_GREEN_LIGHT)
    pdf.set_xy(30, 68)
    pdf.cell(237, 9, "La IA que hace que los supermercados desperdicien menos", align="C")

    pdf.accent_bar(84, 1.5, _ACCENT)

    summary = [
        "11 agentes activos — Kuine orquesta, Chuwi ejecuta",
        "323 tests en verde — sistema listo para produccion",
        "100% robustez adversarial — validado contra 23 ataques",
        "Stack completo: Claude API + FastAPI + Flutter + Supabase",
    ]
    for i, s in enumerate(summary):
        pdf.bullet(s, 60, 93 + i * 16, 220, _WHITE, _ACCENT, 11)

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*_ACCENT)
    pdf.set_xy(30, 163)
    pdf.cell(237, 10, "Gracias. Preguntas.", align="C")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_GREY_MID)
    pdf.set_xy(30, 175)
    pdf.cell(237, 8, "github.com/alvaroferrer1/Tfm  |  @ChuwiMermaOpsBot", align="C")

    pdf.slide_num(10, TOTAL)


# ── Función principal ─────────────────────────────────────────────────────────

def generate_presentation(output_path: str | None = None) -> bytes:
    pdf = _Slide()

    _slide_portada(pdf)
    _slide_problema(pdf)
    _slide_solucion(pdf)
    _slide_arquitectura(pdf)
    _slide_chuwi(pdf)
    _slide_resultados(pdf)
    _slide_demo(pdf)
    _slide_stack(pdf)
    _slide_esg(pdf)
    _slide_cierre(pdf)

    buf = io.BytesIO()
    pdf.output(buf)
    data = buf.getvalue()

    if output_path:
        Path(output_path).write_bytes(data)
        print(f"PDF generado: {output_path} ({len(data) // 1024} KB)")

    return data


if __name__ == "__main__":
    out = Path(__file__).parent.parent.parent / "MermaOps_Presentacion_TFM.pdf"
    generate_presentation(str(out))
