"""
generate_master_pdf.py — MermaOps PDF tecnico premium
Ejecutar: python generate_master_pdf.py
"""
from __future__ import annotations
import os, io
from fpdf import FPDF, XPos, YPos
from PIL import Image as PILImage

OUT   = "docs/pdf/MermaOps_Sistema_Completo.pdf"
SHOTS = "docs/screenshots_now"
DOCS  = "docs"

# ── Paleta ────────────────────────────────────────────────────────────────────
G1  = (4,  80,  60)   # verde oscuro
G2  = (6, 148, 100)   # verde medio
G3  = (13,180,120)    # verde claro intenso
GL  = (209,250,229)   # verde muy claro
TE  = (13,110, 80)    # teal
AM  = (180,100,  0)   # amber
RE  = (180, 30, 30)   # rojo
BL  = (37,  99,235)   # azul
PU  = (109, 40,217)   # purpura
TK  = (0,  136,204)   # telegram azul
GB  = (248,250,252)   # gris fondo
GBD = (209,213,219)   # gris borde
TD  = (17,  24, 39)   # texto dark
TM  = (75,  85, 99)   # texto mid
TL  = (156,163,175)   # texto light
WH  = (255,255,255)   # blanco
BK  = (15,  23, 42)   # casi negro
DG  = (30,  41, 59)   # gris oscuro (frame movil)


def _s(t):
    t = str(t)
    for a, b in {
        "—":"-","–":"-","·":".","°":"o","…":"...","'":"'","'":"'",
        "'":"'","'":"'",""":'"',""":'"',"✅":"[OK]","❌":"[X]",
        "⚠️":"[!]","⚠":"[!]","✓":"v","✗":"X","→":"->","←":"<-",
        "▶":">","◀":"<","▲":"^","▼":"v","●":"*","○":"o",
        "├":"+","└":"+","│":"|","─":"-","┌":"+","┐":"+","┘":"+",
        "€":"EUR","×":"x","≥":">=","≤":"<=","≈":"~",
        "🤖":"","📱":"","🗺":"","📊":"","💰":"","❤️":"","⚡":"",
        "🔴":"!!!","🟡":">>","🟢":"OK","📋":"","🏆":"*","🌡":"",
        "☀️":"","🌧":"","➔":"->","⟶":"->",
    }.items():
        t = t.replace(a, b)
    return t.encode("latin-1", errors="replace").decode("latin-1")


def crop_center_jpeg(path: str, w_px: int, h_px: int) -> bytes:
    """Recorta imagen centrada y devuelve bytes JPEG."""
    img = PILImage.open(path).convert("RGB")
    iw, ih = img.size
    # Calcular ratio para llenar el area objetivo
    r = max(w_px / iw, h_px / ih)
    nw, nh = int(iw * r), int(ih * r)
    img = img.resize((nw, nh), PILImage.LANCZOS)
    left = (nw - w_px) // 2
    top  = (nh - h_px) // 2
    img = img.crop((left, top, left + w_px, top + h_px))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


class PDF(FPDF):
    _section_label = ""
    _accent = G1

    def header(self):
        if self.page_no() == 1: return
        self.set_fill_color(*BK)
        self.rect(0, 0, 210, 8, "F")
        self.set_fill_color(*self._accent)
        self.rect(0, 7, 210, 1.5, "F")
        self.set_font("Helvetica", "B", 7)
        self.set_text_color(*WH)
        self.set_xy(10, 1)
        self.cell(100, 6, _s("MermaOps - Sistema Multi-Agente de IA"))
        self.set_xy(110, 1)
        self.cell(90, 6, _s(self._section_label), align="R")
        self.set_text_color(*TD)
        self.ln(11)

    def footer(self):
        if self.page_no() == 1: return
        self.set_y(-11)
        self.set_fill_color(*BK)
        self.rect(0, self.get_y(), 210, 11, "F")
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*TL)
        self.set_xy(10, self.get_y() + 2)
        self.cell(95, 5, "TFM 2026  |  alvaroferrermarg@gmail.com")
        self.cell(95, 5, f"Pagina {self.page_no()}", align="R")

    # ─── Bloque de seccion ────────────────────────────────────────────────
    def section_cover(self, number: str, title: str, subtitle: str, color=G1):
        """Pagina separadora de seccion con fondo coloreado."""
        self._accent = color
        self._section_label = f"{number}. {title}"
        self.add_page()
        self.set_fill_color(*color)
        self.rect(0, 0, 210, 297, "F")
        # Patron de lineas diagonales
        self.set_draw_color(*(max(c-20,0) for c in color))
        for i in range(0, 300, 18):
            self.line(0, i, i, 0)
        # Numero grande
        self.set_font("Helvetica", "B", 80)
        self.set_text_color(*(min(c+30,255) for c in color))
        self.set_xy(0, 60)
        self.cell(210, 60, number, align="C")
        # Titulo
        self.set_font("Helvetica", "B", 26)
        self.set_text_color(*WH)
        self.set_xy(20, 140)
        self.cell(170, 15, _s(title), align="C")
        # Subtitulo
        self.set_font("Helvetica", "", 12)
        self.set_text_color(*(min(c+120,255) for c in color))
        self.set_xy(20, 160)
        self.multi_cell(170, 8, _s(subtitle), align="C")
        # Barra inferior
        self.set_fill_color(*WH)
        self.rect(0, 260, 210, 37, "F")
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*color)
        self.set_xy(0, 272)
        self.cell(210, 8, "MermaOps - TFM 2026", align="C")

    def new_section_page(self, title: str, color=G1):
        """Pagina de contenido con header de seccion."""
        self._accent = color
        self._section_label = title
        self.add_page()
        # Banner de seccion
        self.set_fill_color(*color)
        self.rect(0, 9.5, 210, 12, "F")
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*WH)
        self.set_xy(12, 11.5)
        self.cell(0, 8, _s(title))
        self.set_text_color(*TD)
        self.ln(6)

    # ─── Tipografia ───────────────────────────────────────────────────────
    def h2(self, t, color=G1):
        if self.get_y() > 250: self.add_page()
        self.ln(5)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*color)
        self.set_x(12)
        self.cell(0, 8, _s(t), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*color)
        self.set_line_width(0.6)
        self.line(12, self.get_y(), 100, self.get_y())
        self.set_line_width(0.2)
        self.set_text_color(*TD)
        self.ln(5)

    def body(self, t, x=12, w=186, lh=5.5):
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(*TD)
        self.set_x(x)
        self.multi_cell(w, lh, _s(t))
        self.ln(1)

    def bullet(self, t, x=16, color=G2):
        self.set_x(x)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*color)
        self.cell(5, 5.5, "-")
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(*TD)
        self.multi_cell(182 - x, 5.5, _s(t))

    # ─── Imagen movil ─────────────────────────────────────────────────────
    def phone_frame(self, img_path: str, x: float, y: float,
                    frame_w: float = 44, caption: str = ""):
        """Dibuja un frame de movil con la captura dentro."""
        frame_h = frame_w * 844 / 390
        pad = 2.5
        # Sombra
        self.set_fill_color(180, 190, 200)
        self.rect(x + 1.5, y + 1.5, frame_w, frame_h, "F")
        # Marco oscuro
        self.set_fill_color(*DG)
        self.rect(x, y, frame_w, frame_h, "F")
        # Pantalla (area interna)
        ix, iy = x + pad, y + pad + 3
        iw = frame_w - pad * 2
        ih = frame_h - pad * 2 - 4
        # Imagen
        try:
            jpeg = crop_center_jpeg(img_path, int(iw * 12), int(ih * 12))
            self.image(io.BytesIO(jpeg), ix, iy, iw, ih)
        except Exception:
            self.set_fill_color(*GL)
            self.rect(ix, iy, iw, ih, "F")
            self.set_font("Helvetica", "", 6)
            self.set_text_color(*G2)
            self.set_xy(ix, iy + ih / 2)
            self.cell(iw, 4, "(captura)", align="C")
        # Notch
        self.set_fill_color(*DG)
        self.rect(x + frame_w/2 - 5, y + pad/2, 10, 1.5, "F")
        # Boton home
        self.set_fill_color(60, 80, 70)
        self.rect(x + frame_w/2 - 4, y + frame_h - pad/2 - 1, 8, 1.2, "F")
        # Caption
        if caption:
            self.set_font("Helvetica", "I", 6.5)
            self.set_text_color(*TM)
            self.set_xy(x, y + frame_h + 1.5)
            self.cell(frame_w, 4, _s(caption), align="C")

    def web_screenshot(self, img_path: str, x: float, y: float,
                       w: float = 140, caption: str = ""):
        """Captura web en marco de navegador."""
        bar_h = 5
        h = w * 820 / 1280 + bar_h
        # Sombra
        self.set_fill_color(180, 190, 200)
        self.rect(x + 1, y + 1, w, h, "F")
        # Barra del navegador
        self.set_fill_color(*DG)
        self.rect(x, y, w, bar_h, "F")
        # Puntos de ventana (rojo/amarillo/verde)
        for i, c in enumerate([RE, AM, G2]):
            self.set_fill_color(*c)
            self.rect(x + 3 + i * 4, y + 1.5, 2.5, 2.5, "F")
        # URL bar
        self.set_fill_color(50, 60, 70)
        self.rect(x + 18, y + 1, w - 26, 3, "F")
        self.set_font("Helvetica", "", 4.5)
        self.set_text_color(*TL)
        self.set_xy(x + 19, y + 1.5)
        self.cell(w - 28, 2.5, "localhost:8080 - MermaOps")
        # Imagen
        try:
            jpeg = crop_center_jpeg(img_path, int(w * 10), int((h - bar_h) * 10))
            self.image(io.BytesIO(jpeg), x, y + bar_h, w, h - bar_h)
        except Exception:
            self.set_fill_color(*GL)
            self.rect(x, y + bar_h, w, h - bar_h, "F")
        # Caption
        if caption:
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(*TM)
            self.set_xy(x, y + h + 1)
            self.cell(w, 4, _s(caption), align="C")
        return h

    # ─── Tablas ───────────────────────────────────────────────────────────
    def thead(self, cols, bg=G1):
        self.ln(2)
        self.set_fill_color(*bg)
        self.set_text_color(*WH)
        self.set_font("Helvetica", "B", 7.5)
        self.set_x(12)
        for label, w in cols:
            self.cell(w, 7.5, _s(label), border=1, fill=True)
        self.set_text_color(*TD)
        self.ln()

    def trow(self, vals, cols, shade=False, bold_col=-1):
        self.set_fill_color(*(GB if shade else WH))
        self.set_x(12)
        for i, ((val, _), (_, w)) in enumerate(zip(
                [v if isinstance(v, tuple) else (v, None) for v in vals],
                cols)):
            is_bold = (i == bold_col)
            self.set_font("Helvetica", "B" if is_bold else "", 7.5)
            self.set_text_color(*(G1 if is_bold else TD))
            self.cell(w, 6.5, _s(val if isinstance(val, str) else vals[i]), border=1, fill=True)
        self.set_text_color(*TD)
        self.ln()

    def trow_plain(self, vals, shade=False):
        self.set_fill_color(*(GB if shade else WH))
        self.set_x(12)
        self.set_font("Helvetica", "", 7.5)
        for val, w in vals:
            self.cell(w, 6.5, _s(val), border=1, fill=True)
        self.ln()

    # ─── Card de agente ───────────────────────────────────────────────────
    def agent_card(self, name, model, desc, bullets, color=G2, icon=""):
        if self.get_y() > 240: self.add_page()
        y = self.get_y()
        # Franja lateral de color
        self.set_fill_color(*color)
        self.rect(12, y, 3, 9999, "F")  # se dibuja despues con la altura real
        # Cabecera
        self.set_fill_color(*BK)
        self.rect(15, y, 183, 9, "F")
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*WH)
        self.set_xy(18, y + 1.5)
        self.cell(100, 6, _s(name))
        # Badge modelo
        self.set_fill_color(*color)
        bw = len(model) * 2.2 + 6
        self.rect(198 - bw, y + 2, bw, 5, "F")
        self.set_font("Helvetica", "B", 6.5)
        self.set_xy(198 - bw + 1, y + 2.8)
        self.cell(bw - 2, 3.5, _s(model), align="C")
        # Cuerpo
        self.set_fill_color(*GB)
        body_start = y + 10
        self.set_xy(18, body_start + 2)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*TD)
        self.set_x(18)
        self.multi_cell(180, 5, _s(desc))
        self.ln(1)
        for b in bullets:
            self.set_x(19)
            self.set_font("Helvetica", "B", 7.5)
            self.set_text_color(*color)
            self.cell(4, 5, "-")
            self.set_font("Helvetica", "", 7.5)
            self.set_text_color(*TM)
            self.multi_cell(177, 5, _s(b))
        self.ln(2)
        body_end = self.get_y()
        self.set_fill_color(*GB)
        self.rect(15, body_start, 183, body_end - body_start + 2, "F")
        # Dibujar borde lateral de color sobre el fondo
        self.set_fill_color(*color)
        self.rect(12, y, 3, body_end - y + 2, "F")
        self.set_fill_color(*BK)
        self.rect(15, y, 183, 10, "F")
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*WH)
        self.set_xy(18, y + 2)
        self.cell(100, 6, _s(name))
        self.set_fill_color(*color)
        self.rect(198 - bw, y + 2.5, bw, 5, "F")
        self.set_font("Helvetica", "B", 6.5)
        self.set_xy(198 - bw + 1, y + 3.3)
        self.cell(bw - 2, 3.5, _s(model), align="C")
        self.set_text_color(*TD)
        self.set_xy(18, body_start + 2)
        self.set_font("Helvetica", "", 8)
        self.multi_cell(180, 5, _s(desc))
        self.ln(1)
        for b in bullets:
            self.set_x(19)
            self.set_font("Helvetica", "B", 7.5)
            self.set_text_color(*color)
            self.cell(4, 5, "-")
            self.set_font("Helvetica", "", 7.5)
            self.set_text_color(*TM)
            self.multi_cell(177, 5, _s(b))
        self.ln(6)

    # ─── KPI cards ────────────────────────────────────────────────────────
    def kpi_strip(self, items):
        """items = [(valor, label, color), ...]"""
        n = len(items)
        w = 186 / n
        y = self.get_y()
        for i, (val, lbl, col) in enumerate(items):
            x = 12 + i * w
            self.set_fill_color(*BK)
            self.rect(x, y, w - 1, 18, "F")
            self.set_fill_color(*col)
            self.rect(x, y, w - 1, 3, "F")
            self.set_font("Helvetica", "B", 15)
            self.set_text_color(*WH)
            self.set_xy(x, y + 4)
            self.cell(w - 1, 8, _s(val), align="C")
            self.set_font("Helvetica", "", 6.5)
            self.set_text_color(*TL)
            self.set_xy(x, y + 12)
            self.cell(w - 1, 5, _s(lbl), align="C")
        self.set_text_color(*TD)
        self.ln(26)

    def info_pill(self, text, color=BL):
        self.set_fill_color(*color)
        self.set_text_color(*WH)
        self.set_font("Helvetica", "B", 7)
        tw = len(text) * 2.1 + 6
        self.cell(tw, 5, _s(text), fill=True)
        self.set_text_color(*TD)
        self.cell(2, 5, "")

    def callout(self, title, text, color=BL, bg=None):
        if bg is None:
            bg = tuple(min(c + 200, 255) for c in color)
        y = self.get_y()
        self.set_fill_color(*color)
        self.rect(12, y, 4, 999, "F")
        self.set_fill_color(*bg)
        tw = 12
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*color)
        self.set_xy(tw + 5, y + 3)
        self.cell(0, 5, _s(title))
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*TD)
        self.set_xy(tw + 5, self.get_y() + 2)
        self.multi_cell(183, 5, _s(text))
        self.ln(1)
        h = self.get_y() - y + 3
        self.set_fill_color(*bg)
        self.rect(16, y, 182, h, "F")
        self.set_fill_color(*color)
        self.rect(12, y, 4, h, "F")
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*color)
        self.set_xy(tw + 5, y + 3)
        self.cell(0, 5, _s(title))
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*TD)
        self.set_xy(tw + 5, y + 9)
        self.multi_cell(183, 5, _s(text))
        self.ln(6)


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTRUIR PDF
# ═══════════════════════════════════════════════════════════════════════════════
pdf = PDF()
pdf.set_auto_page_break(True, margin=16)
pdf.set_margins(0, 0, 0)

# helper para imagen de captura
def shot(name): return os.path.join(SHOTS, name)
def docs(name): return os.path.join(DOCS, name)

# ══════════════════════════════════════════════════════════════════════════════
# PORTADA
# ══════════════════════════════════════════════════════════════════════════════
pdf.add_page()

# Fondo negro
pdf.set_fill_color(*BK)
pdf.rect(0, 0, 210, 297, "F")

# Linea de acento verde
pdf.set_fill_color(*G2)
pdf.rect(0, 0, 6, 297, "F")
pdf.set_fill_color(*G3)
pdf.rect(6, 0, 2, 297, "F")

# Grid de puntos decorativo
pdf.set_fill_color(30, 45, 35)
for row in range(0, 300, 12):
    for col in range(20, 210, 12):
        pdf.rect(col, row, 1, 1, "F")

# Titulo
pdf.set_font("Helvetica", "B", 52)
pdf.set_text_color(*WH)
pdf.set_xy(14, 38)
pdf.cell(0, 22, "MermaOps")

# Linea verde bajo titulo
pdf.set_fill_color(*G2)
pdf.rect(14, 63, 120, 1.5, "F")

pdf.set_font("Helvetica", "", 13)
pdf.set_text_color(*GL)
pdf.set_xy(14, 67)
pdf.cell(0, 8, _s("Sistema Multi-Agente de IA"))
pdf.set_xy(14, 75)
pdf.cell(0, 8, _s("para Reduccion de Merma Alimentaria"))
pdf.set_xy(14, 83)
pdf.cell(0, 8, _s("en Supermercados Espanoles"))

# Screenshots en portada — stack de 3 moviles
try:
    screen_files = [
        (shot("01_dashboard.png"), 118, 28),
        (shot("03_mapa_plano.png"), 148, 45),
        (shot("09_chuwi.png"), 133, 65),
    ]
    for spath, sx, sy in screen_files:
        if os.path.exists(spath):
            pdf.phone_frame(spath, sx, sy, frame_w=40)
except Exception:
    pass

# KPIs en portada
kpi_data = [
    ("12", "Agentes IA", G2),
    ("774", "Tests 100%", TE),
    ("30+", "Cmds Telegram", BL),
    ("9", "Pantallas App", PU),
    ("0.80", "EUR/mes", AM),
    ("23/23", "Seg. adversarial", RE),
]
pdf.set_y(148)
n = len(kpi_data)
kw = 185 / n
for i, (val, lbl, col) in enumerate(kpi_data):
    x = 14 + i * kw
    pdf.set_fill_color(*BK)
    pdf.set_draw_color(*col)
    pdf.rect(x, pdf.get_y(), kw - 1, 22, "FD")
    pdf.set_fill_color(*col)
    pdf.rect(x, pdf.get_y(), kw - 1, 2.5, "F")
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*WH)
    pdf.set_xy(x, pdf.get_y() + 5)
    pdf.cell(kw - 1, 8, _s(val), align="C")
    pdf.set_font("Helvetica", "", 6)
    pdf.set_text_color(*TL)
    pdf.set_xy(x, pdf.get_y() + 7)
    pdf.cell(kw - 1, 5, _s(lbl), align="C")
pdf.ln(28)

# Separador
pdf.set_fill_color(*DG)
pdf.rect(14, pdf.get_y(), 182, 0.5, "F")
pdf.ln(5)

# Stack tecnico en portada
tech_items = [
    ("Backend",  "FastAPI + Python 3.14  |  Puerto 8001"),
    ("IA",       "Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5"),
    ("BD",       "Supabase PostgreSQL + Realtime + pgvector"),
    ("App",      "Flutter Web + Android/iOS  |  Riverpod"),
    ("Bot",      "@ChuwiMermaOpsBot  |  python-telegram-bot"),
    ("Tests",    "pytest 774/774  |  < 2 segundos"),
]
for label, val in tech_items:
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*G3)
    pdf.set_xy(14, pdf.get_y())
    pdf.cell(28, 6, _s(label))
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*TL)
    pdf.cell(0, 6, _s(val))
    pdf.ln()

# Pie portada
pdf.set_fill_color(*G1)
pdf.rect(0, 268, 210, 29, "F")
pdf.set_fill_color(*G2)
pdf.rect(0, 268, 210, 2, "F")
pdf.set_font("Helvetica", "B", 10)
pdf.set_text_color(*WH)
pdf.set_xy(14, 274)
pdf.cell(0, 7, _s("TFM — Master en Inteligencia Artificial  |  2026"))
pdf.set_font("Helvetica", "", 8)
pdf.set_text_color(*GL)
pdf.set_xy(14, 282)
pdf.cell(0, 6, "alvaroferrermarg@gmail.com")


# ══════════════════════════════════════════════════════════════════════════════
# SECCION 1 — ARQUITECTURA
# ══════════════════════════════════════════════════════════════════════════════
pdf.new_section_page("01 — Arquitectura del Sistema", G1)

# Diagrama visual de arquitectura
pdf.h2("Diagrama de componentes", G1)

# Bloque USUARIOS
y0 = pdf.get_y()
pdf.set_fill_color(*BK)
pdf.rect(12, y0, 186, 72, "F")

# Columna izquierda — canales de entrada
for i, (label, color) in enumerate([("Telegram Bot\n@ChuwiMermaOpsBot", TK), ("App Flutter\nWeb + Movil", BL)]):
    bx, by = 14, y0 + 3 + i * 32
    pdf.set_fill_color(*color)
    pdf.rect(bx, by, 38, 26, "F")
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*WH)
    lines = label.split("\n")
    for j, l in enumerate(lines):
        pdf.set_xy(bx, by + 7 + j * 7)
        pdf.cell(38, 5, _s(l), align="C")
    # Flecha ->
    pdf.set_fill_color(*color)
    pdf.rect(52, by + 11, 8, 2, "F")
    pdf.set_xy(58, by + 7.5)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*color)
    pdf.cell(4, 8, ">")

# Backend central
pdf.set_fill_color(*G1)
pdf.rect(62, y0 + 3, 72, 60, "F")
pdf.set_font("Helvetica", "B", 8)
pdf.set_text_color(*WH)
pdf.set_xy(62, y0 + 5)
pdf.cell(72, 5, "Backend FastAPI :8001", align="C")
# Endpoints
for i, ep in enumerate(["/dashboard", "/actions", "/scan", "/agent/chat", "/reports", "/weather"]):
    pdf.set_font("Courier", "", 6.5)
    pdf.set_xy(64, y0 + 12 + i * 7.5)
    pdf.set_text_color(*(int(c * 0.7 + 76) for c in GL))
    pdf.cell(68, 5, ep)
# Flecha ->
pdf.set_fill_color(*G2)
pdf.rect(134, y0 + 29, 8, 2, "F")
pdf.set_font("Helvetica", "B", 10)
pdf.set_text_color(*G2)
pdf.set_xy(140, y0 + 25)
pdf.cell(4, 8, ">")

# Capa agentes
pdf.set_fill_color(*DG)
pdf.rect(144, y0 + 3, 52, 60, "F")
pdf.set_font("Helvetica", "B", 7)
pdf.set_text_color(*G3)
pdf.set_xy(144, y0 + 5)
pdf.cell(52, 4, "AGENTES IA", align="C")
agentes_txt = ["Kuine (Opus)", "Chuwi (Sonnet)", "Evaluador", "ForkMerge", "Validador",
               "Consenso", "Predictor", "Vision", "Reportero", "Notificador"]
for i, a in enumerate(agentes_txt):
    c = [G2, TK, BL, AM, RE, PU, TE, G3, TM, GL][i]
    pdf.set_fill_color(*c)
    pdf.rect(146, y0 + 10 + i * 5.2, 48, 4.5, "F")
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_text_color(*WH)
    pdf.set_xy(147, y0 + 10.5 + i * 5.2)
    pdf.cell(46, 3.5, _s(a))

# Flecha abajo Supabase
pdf.set_fill_color(*TM)
pdf.rect(98, y0 + 63, 2, 5, "F")
pdf.set_text_color(*TM)
pdf.set_font("Helvetica", "B", 10)
pdf.set_xy(95, y0 + 67)
pdf.cell(8, 5, "v")

# Supabase
pdf.set_fill_color(30, 60, 100)
pdf.rect(44, y0 + 68, 120, 14, "F")
pdf.set_font("Helvetica", "B", 8)
pdf.set_text_color(*WH)
pdf.set_xy(44, y0 + 70)
pdf.cell(120, 5, "Supabase  (PostgreSQL + Realtime + Auth + pgvector)", align="C")
pdf.set_font("Helvetica", "", 6.5)
pdf.set_text_color(*TL)
pdf.set_xy(44, y0 + 76)
pdf.cell(120, 5, "stores | products | batches | actions | merma_log | agent_memory | donations | ...", align="C")

pdf.set_text_color(*TD)
pdf.ln(y0 + 88 - pdf.get_y())

pdf.ln(3)

# Stack tecnico
pdf.h2("Stack tecnologico", G1)
cols_tech = [("Capa", 30), ("Tecnologia", 50), ("Version", 30), ("Detalle clave", 76)]
pdf.thead(cols_tech)
tech_rows = [
    ("API", "FastAPI + Uvicorn", "Python 3.14", "Puerto 8001, async, JWT auth"),
    ("Agentes", "Claude API Anthropic", "Opus 4.7 / Sonnet 4.6 / Haiku 4.5", "Right-sizing por tarea"),
    ("BD", "Supabase PostgreSQL", "pgvector 1536 dim", "RLS por store_id, Realtime WS"),
    ("App", "Flutter + Dart", "Riverpod + GoRouter", "Web + Android/iOS, ShellRoute"),
    ("Telegram", "python-telegram-bot", "v21+", "Polling, callbacks, inline keyboards"),
    ("PDF", "fpdf2", "2.x", "6 tipos de PDF server-side"),
    ("Scheduler", "APScheduler", "3.x", "15 jobs cron 07:00-21:30"),
    ("Clima", "Open-Meteo API", "Gratuita", "Sin API key, coordenadas GPS tienda"),
    ("Tests", "pytest", "774/774", "< 2s, sin conexion real BD/API"),
    ("RAG", "pgvector", "1536 dim", "Normativa alimentaria indexada"),
]
for i, r in enumerate(tech_rows):
    pdf.trow_plain(list(zip(r, [c[1] for c in cols_tech])), shade=(i%2==0))
pdf.ln(4)

# Variables de entorno
pdf.h2("Variables de entorno requeridas", G1)
pdf.callout("Seguridad", "Ningun valor secreto en codigo. Todo gestionado por .env. Nunca subir .env al repositorio.", RE, (255,240,240))
env_vars = [
    ("ANTHROPIC_API_KEY", "sk-ant-...", "Acceso a Claude API (Opus/Sonnet/Haiku)"),
    ("SUPABASE_URL", "https://XXXX.supabase.co", "URL del proyecto Supabase"),
    ("SUPABASE_KEY", "sb_anon_...", "Clave anonima para operaciones de cliente"),
    ("SUPABASE_SERVICE_KEY", "sb_service_...", "Clave de servicio para operaciones admin"),
    ("TELEGRAM_BOT_TOKEN", "123456:ABC...", "Token del bot @ChuwiMermaOpsBot"),
    ("STORE_ID", "demo-store-001", "Identificador unico de la tienda"),
    ("APP_PORT", "8001", "Puerto del backend (8000 bloqueado por Manager.exe)"),
]
cols_env = [("Variable", 52), ("Ejemplo", 58), ("Uso", 76)]
pdf.thead(cols_env, DG)
for i, r in enumerate(env_vars):
    pdf.trow_plain(list(zip(r, [c[1] for c in cols_env])), shade=(i%2==0))


# ══════════════════════════════════════════════════════════════════════════════
# SECCION 2 — AGENTES IA
# ══════════════════════════════════════════════════════════════════════════════
pdf.new_section_page("02 — Los 12 Agentes de IA", G1)

# Tabla resumen
pdf.h2("Resumen de los 12 agentes", G1)
cols_ag = [("Agente", 38), ("Modelo", 30), ("Activacion", 44), ("Tecnica principal", 74)]
pdf.thead(cols_ag)
agents_tbl = [
    ("Kuine (orquestador)", "Opus 4.7", "07:30 / 12:00 / 20:00 / scan", "Loop 20 iter, 16 tools, extended thinking"),
    ("Chuwi (Telegram)", "Sonnet 4.6", "Msgs Telegram, streaming", "Intent 0-token, reflexion, caching"),
    ("Evaluador", "Sonnet 4.6", "Scan + Kuine tools", "Score 0-100, thinking >= score 65"),
    ("ForkMerge", "3xSonnet + Opus", "Valor>50EUR o caducado", "3 ramas paralelas + sintesis Opus"),
    ("Validador", "Sonnet 4.6", "Pre-ejecucion toda accion", "23 ataques adversariales, 100%"),
    ("Consenso", "3x Sonnet", "Score>=90 Y valor>=30EUR", "3 instancias paralelas, regla 2/3"),
    ("Predictor", "Haiku 4.5", "07:00 diario + peticion", "Open-Meteo API + historial merma"),
    ("Vision", "Haiku 4.5", "Foto Telegram / scan app", "Image understanding, analisis producto"),
    ("Reportero", "Sonnet 4.6", "Cierre diario / semanal", "Sintesis datos -> brief + PDF"),
    ("Notificador", "python-tg-bot", "Alertas scheduler 8-21h", "SLA tracking, escalaciones"),
    ("Precio", "Heuristico", "Cada evaluacion", "Descuento lineal dias x categoria (0 tokens)"),
    ("Stock", "Heuristico", "Reposicion almacen", "FEFO automatico, umbral configurable (0 tokens)"),
]
for i, r in enumerate(agents_tbl):
    pdf.trow_plain(list(zip(r, [c[1] for c in cols_ag])), shade=(i%2==0))
pdf.ln(4)

# Cards detalladas
pdf.h2("Descripcion tecnica detallada", G1)

pdf.agent_card("KUINE — Orquestador principal", "Claude Opus 4.7",
    "El cerebro del sistema. Loop agentico real: recibe prompt, decide si necesita tools, las ejecuta, "
    "recibe resultados, decide si continuar o dar respuesta final. Hasta 20 iteraciones, timeout 5 min. "
    "Analiza la tienda entera: caducidades, stock, historial, normativa. Genera acciones concretas.",
    ["16 tools reales: get_expiring_batches, evaluate_product_risk, create_action, calculate_discount, "
     "get_warehouse_stock, search_food_regulations, store_memory, recall_memory, get_roi, evaluate_all_products_parallel...",
     "Extended thinking ADAPTATIVO (sin limite de tokens) para brief diario. Budget 1500 tokens para scan rapido",
     "3 flujos principales: run_daily_brief (07:30) | run_intraday_check (12:00) | run_closing (20:00)",
     "ThreadPoolExecutor para evaluate_all_products_parallel: evalua todos los lotes en paralelo",
     "Memoria episodica en agent_memory: guarda decisiones, patrones, aprendizajes de la tienda"], G1)

pdf.agent_card("CHUWI — Bot Telegram conversacional", "Claude Sonnet 4.6",
    "Agente conversacional en Telegram. Clasifica intents sin tokens (palabras clave), precarga contexto "
    "de Supabase, decide si necesita LLM o responde directo. Streaming real: texto progresivo en Telegram.",
    ["Intent classification 0-token: 10 intents por keywords -> ahorro ~60% llamadas LLM",
     "Prompt caching: tools estaticos TTL 5min -> ahorro ~85% tokens cached vs. sin cache",
     "Reflexion loop (Shinn 2023): aprende de cada interaccion, guarda 5 lecciones en agent_memory",
     "30+ comandos: /menu /criticos /ruta /brief /scan /mapa /historial /merma7 /tiempo /esg /insights...",
     "Modo ruta activa: guia empleado accion por accion (GPS de tienda), avanza al confirmar/donar"], TK)

pdf.agent_card("EVALUADOR — Score de riesgo 0-100", "Claude Sonnet 4.6",
    "Calcula el riesgo de cada lote. Score 0=sin riesgo, 100=caducado hoy con stock alto. "
    "El score determina la accion: CRITICO >=85, ALTO >=65, MEDIO >=40, BAJO <40.",
    ["Extended thinking ACTIVADO solo para scores 65-90 (zona de ambiguedad, decision puede cambiar)",
     "Para scores obvios (>90 o <30): thinking desactivado -> misma precision con ~60% menos tokens thinking",
     "Output: {risk_level, action, price_adjustment_pct, reasoning, thinking_used: bool}"], BL)

pdf.agent_card("FORKMERGE — Evaluacion paralela alto impacto", "3x Sonnet 4.6 + Opus 4.7 sintesis",
    "Patron fork-merge (Anthropic 2024). Activa cuando value_at_risk > 50 EUR o lote ya caducado. "
    "3 ramas paralelas con perspectivas distintas -> sintesis por Opus.",
    ["Rama 'clearance': maximizar sell-through, descuento agresivo para vaciar lote",
     "Rama 'margin': proteger margen bruto, no vender bajo coste de adquisicion",
     "Rama 'donation': impacto social + deduccion fiscal Ley 49/2002 (35%)",
     "Opus sintetiza las 3 hipotesis y elige la mas solida con justificacion estructurada"], AM)

pdf.agent_card("VALIDADOR — Seguridad adversarial", "Claude Sonnet 4.6",
    "El unico agente que puede REVERTIR decisiones de Kuine. Se ejecuta antes de cualquier accion real. "
    "23 verificaciones adversariales. Bloquea 100% de ataques en suite de tests (47/47).",
    ["Tipos de ataque bloqueados: prompt injection, precio < coste, caducidad falsificada, "
     "entidad donacion no verificada, violacion FEFO, escalada injustificada, action type invalido...",
     "Output: VALIDADO | CORREGIDO | RECHAZADO + final_action + explanation",
     "Integracion RAG: Reglamento CE 178/2002 consultado via pgvector antes de cada decision"], RE)

pdf.agent_card("CONSENSO — Votacion 3 instancias paralelas", "3x Claude Sonnet 4.6",
    "Para casos extremos (score >= 90 Y valor >= 30 EUR), tres instancias independientes analizan "
    "el mismo producto. La decision pasa si al menos 2/3 coinciden. En empate, Opus actua como arbitro.",
    ["Doble umbral deliberado: yogur de 0,80 EUR con score 92 NO activa consenso. Solo impacto real",
     "42/42 tests del modulo consenso al 100% (regla 2/3 correctamente implementada)",
     "Latencia aceptable: 3 evaluadores corren en PARALELO (ThreadPoolExecutor, no secuencialmente)"], PU)


# ══════════════════════════════════════════════════════════════════════════════
# SECCION 3 — PATRONES MULTI-AGENTE
# ══════════════════════════════════════════════════════════════════════════════
pdf.new_section_page("03 — Patrones Multi-Agente Implementados", G2)

pdf.h2("3.1 Loop agentico de Kuine (Orchestrator-Workers)", G2)
pdf.callout("Referencia", "Anthropic — Building Effective Agents, 2024. Patron: Orchestrator-Workers.", G1, GL)

# Diagrama del loop
y_loop = pdf.get_y()
steps_loop = [
    (G1,  "Prompt entrada",       "Sistema envia instrucciones + contexto tienda"),
    (G2,  "Claude analiza",       "Opus 4.7: necesito tools? -> SI | NO"),
    (BL,  "Ejecutar tool",        "get_expiring_batches() / evaluate_product_risk() / create_action()..."),
    (TK,  "Resultado a Claude",   "tool_result devuelto al modelo como mensaje"),
    (AM,  "Siguiente iteracion",  "Claude decide si necesita mas tools (hasta 20 iter)"),
    (G1,  "Respuesta final",      "Brief / Informe / Acciones creadas en Supabase"),
]
for i, (col, title, desc) in enumerate(steps_loop):
    y = pdf.get_y()
    pdf.set_fill_color(*col)
    pdf.rect(12, y, 6, 8, "F")
    pdf.set_fill_color(*GB)
    pdf.rect(18, y, 180, 8, "F")
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*col)
    pdf.set_xy(20, y + 1.5)
    pdf.cell(40, 5, _s(f"[{i+1}] {title}"))
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*TD)
    pdf.cell(130, 5, _s(desc))
    pdf.ln(8)
    if i < len(steps_loop) - 1:
        pdf.set_fill_color(*col)
        pdf.rect(14, pdf.get_y() - 1, 2, 3, "F")
        pdf.ln(2)

pdf.ln(3)
pdf.h2("3.2 Fork-Merge — Evaluacion paralela de alto impacto", G2)
pdf.callout("Activacion", "value_at_risk > 50 EUR  O  days_left <= 0  ->  ForkMerge sustituye al Evaluador estandar", AM, (255,250,230))

# Diagrama fork-merge horizontal
y_fm = pdf.get_y()
pdf.set_fill_color(*BK)
pdf.rect(12, y_fm, 186, 44, "F")
# Entrada
pdf.set_fill_color(*AM)
pdf.rect(14, y_fm + 17, 28, 9, "F")
pdf.set_font("Helvetica", "B", 7)
pdf.set_text_color(*WH)
pdf.set_xy(14, y_fm + 19)
pdf.cell(28, 5, "Producto", align="C")
# Flechas ->
for lane in [8, 19, 30]:
    pdf.set_fill_color(*AM)
    pdf.rect(42, y_fm + lane, 10, 1.5, "F")
# 3 ramas
for i, (label, col, sub) in enumerate([
    ("CLEARANCE", G2, "Descuento agresivo\nvaciar lote"),
    ("MARGIN", BL, "Proteger margen\nno vender bajo coste"),
    ("DONATION", RE, "Impacto social\nDed. fiscal 35%"),
]):
    rx = 52
    ry = y_fm + 3 + i * 13
    pdf.set_fill_color(*col)
    pdf.rect(rx, ry, 42, 10, "F")
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_text_color(*WH)
    pdf.set_xy(rx + 1, ry + 1)
    pdf.cell(40, 4, _s(f"Sonnet 4.6 - {label}"), align="C")
    pdf.set_font("Helvetica", "", 5.5)
    for j, line in enumerate(sub.split("\n")):
        pdf.set_xy(rx + 1, ry + 5 + j * 3)
        pdf.cell(40, 3, _s(line), align="C")
    # Flechas ->
    pdf.set_fill_color(*col)
    pdf.rect(94, ry + 4, 12, 1.5, "F")
# Sintesis Opus
pdf.set_fill_color(*G1)
pdf.rect(106, y_fm + 9, 35, 25, "F")
pdf.set_font("Helvetica", "B", 7)
pdf.set_text_color(*WH)
pdf.set_xy(106, y_fm + 15)
pdf.cell(35, 5, "Opus 4.7", align="C")
pdf.set_font("Helvetica", "", 6.5)
pdf.set_xy(106, y_fm + 21)
pdf.cell(35, 4, "Sintesis", align="C")
pdf.set_xy(106, y_fm + 26)
pdf.cell(35, 4, "3 hipotesis", align="C")
# Flecha -> decision
pdf.set_fill_color(*G2)
pdf.rect(141, y_fm + 20, 10, 1.5, "F")
# Decision
pdf.set_fill_color(*G2)
pdf.rect(151, y_fm + 13, 38, 15, "F")
pdf.set_font("Helvetica", "B", 7)
pdf.set_text_color(*WH)
pdf.set_xy(151, y_fm + 18)
pdf.cell(38, 5, "Decision Final", align="C")
pdf.set_font("Helvetica", "", 5.5)
pdf.set_xy(151, y_fm + 24)
pdf.cell(38, 4, "action + reasoning", align="C")
pdf.set_text_color(*TD)
pdf.ln(y_fm + 50 - pdf.get_y())

pdf.ln(3)
pdf.h2("3.3 Reflexion Loop — aprendizaje continuo", G2)
pdf.callout("Referencia", "Shinn et al. (2023) — 'Reflexion: Language Agents with Verbal Reinforcement Learning'", PU, (245,240,255))
pdf.body("Despues de cada interaccion con Evaluador/Vision, Chuwi genera via Haiku 4.5 (fire-and-forget): "
         "'Que aprendi de esta interaccion? Que haria diferente?' Las 5 lecciones mas recientes se guardan "
         "en agent_memory y se incluyen en el system_prompt de la siguiente sesion.")
pdf.ln(2)

pdf.h2("3.4 Intent 0-token + Prompt Caching", G2)
cols_int = [("Intent", 38), ("Keywords detectadas", 72), ("Contexto precargado", 76)]
pdf.thead(cols_int, DG)
intent_rows = [
    ("consulta_estado", "estado, cuantos, que hay, muestrame", "Conteo acciones criticas/altas"),
    ("pedir_brief", "brief, resumen, informe, analisis", "Fecha + valor riesgo ultimo brief"),
    ("completar_accion", "completado, hecho, ya, listo", "Top 3 acciones por prioridad"),
    ("pedir_ruta", "ruta, recorrido, por donde empiezo", "Top 3 acciones por prioridad"),
    ("registrar_donacion", "donacion, banco alimentos, donar", "Stats donaciones del mes"),
    ("registrar_merma", "tirar, caducado, se ha puesto malo", "LLM fallback (dialogo necesario)"),
    ("otros", "[ninguna keyword coincide]", "LLM fallback completo"),
]
for i, r in enumerate(intent_rows):
    pdf.trow_plain(list(zip(r, [c[1] for c in cols_int])), shade=(i%2==0))
pdf.ln(3)

pdf.callout("ROI del Prompt Caching",
    "Brief diario (Opus, 8 iter): sin cache ~0,48 EUR | con cache ~0,058 EUR -> ahorro 88%\n"
    "Sesion Chuwi (Sonnet, 6 turnos): sin cache ~0,045 EUR | con cache ~0,007 EUR -> ahorro 85%\n"
    "Mes completo (1 tienda): coste real medido ~0,80 EUR con caching activo", G2, GL)


# ══════════════════════════════════════════════════════════════════════════════
# SECCION 4 — BOT TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════
# Pagina con screenshot de Telegram + comandos
pdf.new_section_page("04 — Bot Telegram @ChuwiMermaOpsBot", TK)
pdf._accent = TK

# Two-column layout: screenshot izq, comandos der
chuwi_shot = shot("09_chuwi.png")
if not os.path.exists(chuwi_shot):
    chuwi_shot = shot("08_chat.png")

pdf.h2("Interfaz conversacional en Telegram", TK)
y_tg = pdf.get_y()

# Screenshot movil izquierda
if os.path.exists(chuwi_shot):
    pdf.phone_frame(chuwi_shot, 12, y_tg, 50, "Chuwi en accion")

# Texto derecha
pdf.set_xy(68, y_tg)
pdf.set_font("Helvetica", "B", 9)
pdf.set_text_color(*TK)
pdf.cell(0, 6, _s("Por que Telegram como interfaz?"))
pdf.set_text_color(*TD)
pdf.set_xy(68, y_tg + 7)
pdf.set_font("Helvetica", "", 8)
pdf.multi_cell(130, 4.5, _s(
    "El encargado ya tiene Telegram instalado. "
    "Sin app nueva, sin formacion, sin friccion de adopcion. "
    "El streaming visual (texto progresivo) muestra que el agente 'piensa'. "
    "Funciona en cualquier movil sin instalar la app Flutter."
))

right_y = pdf.get_y() + 3
features = [
    (TK, "Streaming real", "texto aparece progresivamente"),
    (G2, "Inline keyboards", "botones bajo cada mensaje"),
    (BL, "30+ comandos", "publicos + operativos + manager"),
    (AM, "Modo ruta GPS", "guia accion por accion"),
    (RE, "Alertas proactivas", "sin que nadie pregunte"),
    (PU, "Scheduler 15 jobs", "cron 07:00-21:30 autonomo"),
]
for col, title, desc in features:
    pdf.set_xy(68, right_y)
    pdf.set_fill_color(*col)
    pdf.rect(68, right_y, 3, 6, "F")
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*col)
    pdf.set_xy(73, right_y + 1)
    pdf.cell(30, 4, _s(title))
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*TM)
    pdf.cell(90, 4, _s(desc))
    right_y += 8

pdf.set_y(max(y_tg + 115, pdf.get_y()) + 3)

# Tabla comandos
pdf.h2("Comandos disponibles", TK)

sections_cmd = [
    ("Publicos — sin login", TK, [
        ("/start",    "Onboarding completo con presentacion del sistema y menu principal"),
        ("/yo",       "Perfil: nombre, rol (staff/manager), tienda asignada"),
        ("/menu",     "Menu principal con botones inline a todas las funciones"),
        ("/estado",   "Semaforo tienda: verde/amarillo/rojo segun criticos pendientes"),
        ("/ayuda",    "Guia completa de todos los comandos con ejemplos"),
        ("/agentes",  "Estado 12 agentes: activo/inactivo, modelo, ultimo run"),
        ("/kuine",    "Info detallada Kuine: tools, runs recientes, iteraciones"),
    ]),
    ("Operativos — empleados", G2, [
        ("/acciones",  "Lista pendientes por urgencia. Cada una con botones Confirmar/Donar/Escalar"),
        ("/criticos",  "Solo acciones score >= 85 (CRITICO). Vista rapida urgente"),
        ("/ruta",      "Ruta diaria optimizada por pasillos. Boton 'Iniciar modo ruta guiada'"),
        ("/brief",     "Brief diario de Kuine. Genera o recupera el mas reciente"),
        ("/hoy",       "Resumen del dia: ventas estimadas, merma, acciones, donaciones"),
        ("/scan",      "Escanear: foto o barcode. Vision + Kuine -> accion"),
        ("/merma",     "Registrar merma manualmente: producto deteriorado o caducado"),
        ("/donaciones","Resumen donaciones mes + flujo guiado nueva donacion"),
        ("/prediccion","Prediccion merma 7 dias (Haiku + Open-Meteo)"),
        ("/mapa",      "Mapa por pasillos: productos proximos a caducar por zona"),
        ("/historial", "Acciones completadas ultimos 7 dias con empleado y tipo"),
        ("/merma7",    "Proyeccion merma a 7 dias basada en caducidades proximas"),
        ("/tiempo",    "Tiempo actual tienda (Open-Meteo) + prevision 5 dias"),
    ]),
    ("Manager — solo encargados", AM, [
        ("/proveedores","Ficha proveedores con merma historica por categoria"),
        ("/pedido",    "Pedido semanal generado por IA: rotacion + merma historica"),
        ("/esg",       "Informe ESG: CO2, agua, donaciones, CSRD 2026"),
        ("/costes",    "Analisis costes: merma por categoria, evolucion semanal"),
        ("/reflexiones","Lecciones aprendidas del reflexion loop de Chuwi"),
        ("/informe",   "Informe completo del mes: todas las metricas"),
        ("/semana",    "Resumen semana: tendencias vs. semana anterior"),
        ("/insights",  "Insights IA estrategicos (Sonnet 4.6)"),
        ("/simular",   "Panel demo: 5 botones para simular brief/check/cierre/alerta/escalacion"),
    ]),
]

for sec_title, sec_col, cmds in sections_cmd:
    if pdf.get_y() > 220: pdf.add_page()
    pdf.set_fill_color(*sec_col)
    pdf.rect(12, pdf.get_y(), 186, 6, "F")
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*WH)
    pdf.set_xy(14, pdf.get_y() + 1)
    pdf.cell(0, 4, _s(sec_title))
    pdf.set_text_color(*TD)
    pdf.ln(6)
    for i, (cmd, desc) in enumerate(cmds):
        pdf.set_fill_color(*(GB if i%2==0 else WH))
        pdf.set_x(12)
        pdf.set_font("Courier", "B", 8)
        pdf.set_text_color(*sec_col)
        pdf.cell(32, 5.5, _s(cmd), border=1, fill=True)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*TD)
        pdf.cell(154, 5.5, _s(desc), border=1, fill=True)
        pdf.ln()
    pdf.ln(3)

# Scheduler
pdf.add_page()
pdf.h2("Scheduler — 15 trabajos autonomos (07:00-21:30)", TK)
pdf.callout("Autonomia total", "El scheduler corre independientemente. Kuine analiza, notifica y escala sin que nadie lo active. "
    "El notificador NUNCA silencia mensajes en horario 8-21h.", G2, GL)

sched_cols = [("Hora / Frec.", 32), ("Job", 38), ("Funcion principal", 116)]
pdf.thead(sched_cols, DG)
sched_rows = [
    ("07:00 diario",  "Prediccion",  "Open-Meteo + historial merma -> prediccion 7 dias con contexto climatico"),
    ("07:28 diario",  "Saludo",      "Mensaje proactivo de buenos dias con resumen de acciones pendientes"),
    ("07:30 diario",  "Brief diario","Kuine run_daily_brief: analisis completo tienda, genera acciones"),
    ("12:00 diario",  "Check mediodia","Kuine run_intraday_check: escala si hay criticos sin resolver"),
    ("16:00 diario",  "Reflexion",   "Retrospectiva: que fue bien, que se puede mejorar hoy"),
    ("20:00 diario",  "Cierre",      "Kuine run_closing: resumen real del dia, merma efectiva"),
    ("Lunes 06:00",   "Semanal",     "Informe semanal completo + PDF adjunto en Telegram"),
    ("Dia 1 08:00",   "Mensual",     "Informe mensual completo + PDF adjunto"),
    ("Cada 2h 8-20h", "Escalacion", "Escala acciones score>=85 sin resolver mas de 4 horas"),
    ("Cada 30min 8-21h","Monitor",  "Alertas proactivas con botones donacion inline"),
    ("Cada 15min 8-20h","SLA check","Verifica que acciones criticas tienen respuesta en tiempo"),
    ("Cada 30min 8-21h","Spike",    "Auto-brief si se detecta pico de acciones criticas nuevas"),
    ("Cada 30min 8-21h","Triggers", "Evalua intents automaticos segun contexto de la tienda"),
    ("21:30 diario",  "Anomalias",  "Detecta patrones anomalos en inventario nocturno"),
    ("9h / 13h / 18h","Health",    "Verifica conexion BD, bot Telegram, agentes activos"),
]
for i, r in enumerate(sched_rows):
    pdf.trow_plain(list(zip(r, [c[1] for c in sched_cols])), shade=(i%2==0))
pdf.ln(3)

# Flujo de modo ruta
pdf.h2("Flujo modo ruta activa (GPS de tienda)", TK)
ruta_steps = [
    ("Activar", "Escribe 'iniciar ruta' / 'modo ruta' o pulsa boton 'Iniciar modo ruta guiada'"),
    ("Primera accion", "Muestra tarjeta: producto, pasillo-estanteria-nivel, urgencia, accion"),
    ("Empleado actua", "Pulsa Confirmar / Donar entidad / Escalar segun tipo de accion"),
    ("Sistema registra", "complete_action() en Supabase + log merma + SLA dismissed"),
    ("Avance automatico", "Modo ruta detecta estado route_active y muestra siguiente accion"),
    ("Fin ruta", "Cuando no quedan acciones: 'RUTA COMPLETADA: X completadas, Y saltadas'"),
]
for i, (step, desc) in enumerate(ruta_steps):
    y = pdf.get_y()
    col = [TK, G2, BL, AM, G1, PU][i]
    pdf.set_fill_color(*col)
    pdf.rect(12, y, 5, 8, "F")
    pdf.set_fill_color(*GB)
    pdf.rect(17, y, 181, 8, "F")
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*col)
    pdf.set_xy(19, y + 2)
    pdf.cell(28, 4.5, _s(step))
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*TD)
    pdf.cell(150, 4.5, _s(desc))
    pdf.ln(8)
    if i < len(ruta_steps) - 1:
        pdf.set_fill_color(*col)
        pdf.rect(14, pdf.get_y() - 1, 1.5, 3, "F")
        pdf.ln(2)


# ══════════════════════════════════════════════════════════════════════════════
# SECCION 5 — APP FLUTTER
# ══════════════════════════════════════════════════════════════════════════════
# Pantalla 1: Onboarding + Login
pdf.new_section_page("05 — App Flutter: Onboarding y Dashboard", BL)
pdf._accent = BL

pdf.h2("Onboarding y Login", BL)
y_ob = pdf.get_y()
shots_row1 = [
    (docs("01_onboarding.png"),  "Onboarding"),
    (docs("screen_02_login.png"), "Login"),
    (docs("04_after_login.png"),  "Post-login"),
    (shot("01_dashboard.png"),   "Dashboard inicial"),
]
for i, (path, cap) in enumerate(shots_row1):
    if os.path.exists(path):
        pdf.phone_frame(path, 12 + i * 47, y_ob, 43, cap)
pdf.ln(y_ob + 105 - pdf.get_y())
pdf.body("El onboarding explica el sistema en 3 pasos. El login usa Supabase Auth con JWT. "
         "Tras el login, el rol (staff/manager) se lee del perfil y controla el acceso a features.")
pdf.ln(4)

# Pantalla 2: Dashboard
pdf.h2("Dashboard — KPIs en tiempo real", BL)
y_dash = pdf.get_y()
dash_shots = [
    (shot("01_dashboard.png"),      "Dashboard cargado"),
    (shot("02_dash_scroll.png"),    "KPIs y donuts"),
    (shot("dashboard_charts.png"),  "Charts merma 7d"),
    (shot("02b_dashboard_bottom.png"), "Tarjeta tiempo"),
]
for i, (path, cap) in enumerate(dash_shots):
    if os.path.exists(path):
        pdf.phone_frame(path, 12 + i * 47, y_dash, 43, cap)
pdf.ln(y_dash + 105 - pdf.get_y())
features_dash = [
    "KPIs streaming Supabase Realtime: acciones_criticas, merma_evitada, donaciones, valor_riesgo",
    "Shimmer loading mientras carga. StreamProvider Riverpod con asyncMap",
    "Donut chart de urgencia (critico/alto/medio/bajo) + Area chart merma 7 dias",
    "Tarjeta del tiempo Open-Meteo: temperatura, icono WMO, prevision 5 dias",
    "Auto-refresh: 5 min dashboard, 30 min weather. Badge criticos actualiza sin recargar (Realtime WS)",
]
for f in features_dash:
    pdf.bullet(f, color=BL)
pdf.ln(3)

# Pantalla 3: Acciones
pdf.add_page()
pdf.h2("Acciones — Gestion con swipe y export", BL)
y_acc = pdf.get_y()
acc_shots = [
    (shot("02_acciones.png"),           "Lista acciones"),
    (shot("03_acciones.png"),           "Swipe to complete"),
    (shot("acciones_full.png"),         "Vista completa"),
    (shot("acciones_after_export_click.png"), "Export CSV"),
]
for i, (path, cap) in enumerate(acc_shots):
    if os.path.exists(path):
        pdf.phone_frame(path, 12 + i * 47, y_acc, 43, cap)
pdf.ln(y_acc + 105 - pdf.get_y())
for f in [
    "Swipe to complete: DismissDirection.endToStart, solo rol manager (staff ve pero no puede)",
    "Donacion con calculo fiscal 35% automatico (Ley 49/2002) al confirmar",
    "Export CSV: Share.shareXFiles con XFile.fromData (funciona en web y movil)",
    "Import CSV desde TPV: POST /api/v1/import/batches con parseo automatico",
    "Filtro por tipo (rebajar/donar/retirar/revisar) y urgencia (critico/alto/medio)",
]:
    pdf.bullet(f, color=BL)
pdf.ln(3)

# Pantalla 4: Mapa
pdf.h2("Mapa / Plano — CustomPainter con plano real", BL)
y_map = pdf.get_y()
map_shots = [
    (shot("03_mapa_plano.png"),    "Plano tienda"),
    (shot("04_mapa_pasillos.png"), "Tab Pasillos"),
    (shot("05_mapa_fefo.png"),     "Tab FEFO"),
    (docs("floor_plan_screenshot.png"), "Plano completo"),
]
for i, (path, cap) in enumerate(map_shots):
    if os.path.exists(path):
        pdf.phone_frame(path, 12 + i * 47, y_map, 43, cap)
pdf.ln(y_map + 105 - pdf.get_y())
for f in [
    "Plano real dibujado con CustomPainter: almacen + 4 pasillos + Frutas&Verduras + cajas",
    "Hit-testing via _floorPlanRects: tap en zona -> navegacion. Tap almacen -> pantalla Almacen",
    "Tab Pasillos: lista por pasillo con QR y boton Cerrar correcto (dlgCtx, no parent context)",
    "Tab FEFO: lotes ordenados por fecha caducidad (First Expired First Out)",
    "Tab Plano: tarjeta inline Almacen con datos reales del backend (items, valor, alertas)",
]:
    pdf.bullet(f, color=BL)
pdf.ln(3)

# Pantalla 5: Scan
pdf.add_page()
pdf.h2("Escanear — Camara web + Vision Agent IA", BL)
y_scan = pdf.get_y()
scan_shots = [
    (shot("03_scan.png"),    "Pantalla scan"),
    (shot("10_scan.png"),    "Camara activa"),
    (shot("scan.png"),       "Resultado scan"),
    (docs("screen_chuwi.png"), "Resultado IA"),
]
for i, (path, cap) in enumerate(scan_shots):
    if os.path.exists(path):
        pdf.phone_frame(path, 12 + i * 47, y_scan, 43, cap)
pdf.ln(y_scan + 105 - pdf.get_y())
for f in [
    "Web: mobile_scanner v6.0.2, Chrome 83+ / Edge (BarcodeDetector API nativa del navegador)",
    "Dialog.fullscreen: back button + overlay verde esquinas + deteccion automatica del codigo",
    "Movil: CameraFacing.back con permiso de camara automatico (Android/iOS)",
    "Vision Agent (Haiku 4.5): analiza foto y devuelve nombre, caducidad y recomendacion",
    "POST /api/v1/scan -> Kuine -> Evaluador -> accion creada automaticamente en Supabase",
]:
    pdf.bullet(f, color=BL)
pdf.ln(3)

# Pantalla 6: Informes
pdf.h2("Informes — 11 tabs con datos reales", BL)
y_inf = pdf.get_y()
inf_shots = [
    (shot("06_informes_diarios.png"), "Diarios PDF"),
    (shot("07_informes_merma.png"),   "Merma filtros"),
    (docs("ss_esg.png"),             "ESG CSRD"),
    (docs("ss_predicciones.png"),    "Predicciones"),
]
for i, (path, cap) in enumerate(inf_shots):
    if os.path.exists(path):
        pw = 43
        if path.startswith(docs("ss_")):
            # Es screenshot web (1280x820) — renderizar como web screenshot pequeno
            try:
                jpeg = crop_center_jpeg(path, int(pw * 1280 / 390 * 8), int(pw * 844 / 390 * 8))
                pdf.phone_frame.__func__  # just check
            except Exception:
                pass
            pdf.phone_frame(path, 12 + i * 47, y_inf, pw, cap)
        else:
            pdf.phone_frame(path, 12 + i * 47, y_inf, pw, cap)
pdf.ln(y_inf + 105 - pdf.get_y())
for f in [
    "11 tabs: PDF brief, PDF semanal, Merma, Pedidos, ESG, Predicciones, Benchmark, Proveedores, Alternativas, Insights IA",
    "Merma tab: filtro por razon (Todos/Caducidad/Calidad...) + dialog detalle por fila clicable",
    "ESG CSRD 2026: cada punto clicable con informacion de normativa aplicable",
    "Benchmark: badge 'Datos reales del backend' + ranking competidores con explicacion clicable",
    "Insights IA: POST /api/v1/reports/insights (Sonnet 4.6) generado con boton 'Generar'",
]:
    pdf.bullet(f, color=BL)
pdf.ln(3)

# Pantalla 7+: Resto de pantallas en tabla
pdf.add_page()
pdf.h2("Resto de pantallas: Agentes, Proveedores, Almacen, Perfil", BL)
y_rest = pdf.get_y()
rest_shots = [
    (shot("08_proveedores.png"),  "Proveedores"),
    (shot("08_chat.png"),         "Chat agentes"),
    (shot("mapa_plano.png"),      "Almacen FEFO"),
    (docs("screen_profile_menu.png"), "Perfil"),
]
for i, (path, cap) in enumerate(rest_shots):
    if os.path.exists(path):
        pdf.phone_frame(path, 12 + i * 47, y_rest, 43, cap)
pdf.ln(y_rest + 105 - pdf.get_y())

# Tabla resumen pantallas
cols_screens = [("Pantalla", 32), ("Riverpod Provider", 45), ("Endpoint principal", 55), ("Feature clave", 54)]
pdf.thead(cols_screens, BL)
screens_tbl = [
    ("Dashboard",    "pendingActionsStreamProvider", "GET /api/v1/dashboard", "Realtime Supabase WS"),
    ("Acciones",     "actionsProvider", "GET/POST /api/v1/actions", "Swipe + CSV export/import"),
    ("Mapa/Plano",   "_warehouseQuickProvider", "GET /api/v1/warehouse", "CustomPainter real"),
    ("Escanear",     "_scanResultProvider", "POST /api/v1/scan", "mobile_scanner + Vision"),
    ("Agentes",      "_agentStatusProvider", "GET /api/v1/agent/*", "4 tabs: estado+runs"),
    ("Proveedores",  "_suppliersProvider", "GET /api/v1/suppliers", "Merma historica + pedido IA"),
    ("Almacen",      "_warehouseProvider", "GET /api/v1/warehouse", "FEFO + alertas caducidad"),
    ("Informes",     "_reportsProvider", "GET /api/v1/reports/*", "11 tabs + PDF + ESG"),
    ("Perfil/Config","userRoleProvider", "GET/PUT /store/profile", "GPS coords para weather"),
]
for i, r in enumerate(screens_tbl):
    pdf.trow_plain(list(zip(r, [c[1] for c in cols_screens])), shade=(i%2==0))


# ══════════════════════════════════════════════════════════════════════════════
# SECCION 6 — RESULTADOS
# ══════════════════════════════════════════════════════════════════════════════
pdf.new_section_page("06 — Resultados y Metricas Reales", G2)
pdf._accent = G2

pdf.kpi_strip([
    ("774/774", "Tests 100% pass", G1),
    ("+83,3 pp", "Precision vs. baseline", G2),
    ("23/23", "Ataques bloqueados", RE),
    ("483,95 EUR", "Merma identificada", AM),
    ("45", "Acciones completadas", BL),
    ("0,80 EUR", "Coste/mes real", PU),
])

# Tests por modulo
pdf.h2("Suite de tests por modulo", G2)
cols_test = [("Modulo", 52), ("Tests", 18), ("Pass", 18), ("Tiempo", 22), ("Cobertura", 76)]
pdf.thead(cols_test)
tests_data = [
    ("Evaluador (score 0-100)", "89", "89/89", "0,14s", "Todos los rangos, edge cases caducidad"),
    ("Validador (23 ataques)", "47", "47/47", "0,08s", "Prompt injection, precio<coste, FEFO, bypass..."),
    ("Consenso (regla 2/3)", "42", "42/42", "0,12s", "Empate, mayoria, caso arbitro Opus"),
    ("Supervisor / Kuine", "25", "25/25", "0,19s", "Loop, tools, timeouts, errores BD"),
    ("Chuwi agent", "61", "61/61", "0,31s", "Intent, callbacks, modo ruta, donacion"),
    ("Database & API", "38", "38/38", "0,42s", "Todos los endpoints, auth, RLS"),
    ("Scheduler", "18", "18/18", "0,09s", "15 jobs, horarios, quiet hours 21-8h"),
    ("Otros modulos", "454", "454/454", "0,63s", "Price, stock, PDF, formateo, telegram_formatter"),
    ("TOTAL", "774", "774/774", "1,98s", "Sin conexion real a Supabase/Claude API"),
]
for i, r in enumerate(tests_data):
    bold = (i == len(tests_data) - 1)
    pdf.set_fill_color(*(GL if bold else (GB if i%2==0 else WH)))
    pdf.set_x(12)
    for j, (val, (_, w)) in enumerate(zip(r, cols_test)):
        pdf.set_font("Helvetica", "B" if (bold or j==0) else "", 7.5)
        pdf.set_text_color(*(G1 if bold else TD))
        pdf.cell(w, 5.5, _s(val), border=1, fill=True)
    pdf.ln()
pdf.set_text_color(*TD)
pdf.ln(4)

# Comparativa
pdf.h2("Comparativa con soluciones del mercado", G2)
cols_comp = [("Criterio", 42), ("MermaOps", 32), ("Winnow V2", 32), ("Orbisk", 28), ("Manual", 52)]
pdf.thead(cols_comp, BK)
comp_rows = [
    ("Coste implantacion",  "0 EUR",       ">20.000 EUR", ">15.000 EUR", "0 EUR"),
    ("Coste operativo/mes", "~0,80 EUR",   "~300 EUR",    "~250 EUR",    "~120 EUR"),
    ("Hardware requerido",  "Ninguno",     "Bascula+cam", "Camara+srv",  "Ninguno"),
    ("Autonomia 24/7",      "Si (15 cron)","Parcial",     "Parcial",     "No"),
    ("Precision",           "100% tests",  "N/D publico", "N/D publico", "16,7%"),
    ("Normativa CSRD",      "Si (RAG)",    "No",          "No",          "No"),
    ("Multi-agente IA",     "12 agentes",  "No",          "No",          "No"),
    ("Extended thinking",   "Si",          "No",          "No",          "No"),
]
for i, r in enumerate(comp_rows):
    pdf.set_fill_color(*(GB if i%2==0 else WH))
    pdf.set_x(12)
    for j, (val, (_, w)) in enumerate(zip(r, cols_comp)):
        is_merma = (j == 1)
        pdf.set_font("Helvetica", "B" if is_merma else "", 7.5)
        pdf.set_text_color(*(G1 if is_merma else TD))
        pdf.cell(w, 5.5, _s(val), border=1, fill=True)
    pdf.ln()
pdf.set_text_color(*TD)
pdf.ln(3)

# Datos operativos reales
pdf.h2("Datos operativos reales — Supabase demo-store-001", G2)
pdf.callout("Verificable", "Todos los datos pueden consultarse en Supabase, tabla a tabla, sin estimaciones.", G2, GL)
oper_cols = [("Metrica", 88), ("Valor real", 98)]
pdf.thead(oper_cols, DG)
oper_rows = [
    ("Acciones completadas por empleados", "45"),
    ("Briefs diarios generados por Kuine", "7"),
    ("Decisiones tomadas por Kuine", "15"),
    ("Runs completos de Kuine (analisis tienda)", "9"),
    ("Registros en merma_log", "45"),
    ("Donaciones registradas", "4"),
    ("Valor de merma identificado", "483,95 EUR"),
    ("Valor donado (genera deduccion fiscal 35%)", "69,40 EUR"),
    ("Duracion media por run de Kuine", "~6,3 min (377 segundos)"),
    ("Coste estimado por brief diario (con caching)", "~0,03 EUR"),
    ("Coste total mensual estimado (1 tienda)", "~0,80 EUR"),
    ("ROI mensual estimado (merma evitada / coste)", ">500:1"),
]
for i, (k, v) in enumerate(oper_rows):
    pdf.trow_plain([(k, 88), (v, 98)], shade=(i%2==0))
pdf.ln(4)

# ESG
pdf.h2("Metricas ESG y cumplimiento normativo CSRD 2026", G2)
norm_cols = [("Normativa", 52), ("Cobertura", 40), ("Agente que la aplica", 94)]
pdf.thead(norm_cols, G1)
norms = [
    ("Reglamento (CE) 178/2002", "Seguridad alimentaria", "Validador: nunca completar venta de caducado"),
    ("RD 1334/1999", "Etiquetado y caducidad", "Evaluador: dias restantes vs. tipo producto"),
    ("Ley 7/2022", "Residuos/economia circular", "ESG module: tracking CO2 evitado"),
    ("Ley 49/2002 Art.20", "Deduccion fiscal 35%", "Donaciones: deduccion calculada automaticamente"),
    ("CSRD 2026", "Reporting ESG PYMEs", "Modulo ESG: genera datos para informe obligatorio UE"),
    ("WRAP Food Waste 2023", "Benchmark 1,3% revenue", "Benchmark: comparativa sector espanol"),
    ("FAO Food Loss 2022", "Recuperacion 28% total", "Benchmark: tasa recuperacion vs. referencia FAO"),
    ("Poore & Nemecek (2018)", "CO2 por kg producto", "ESG: calculo CO2 evitado por categoria"),
    ("Mekonnen & Hoekstra (2011)", "Agua por kg producto", "ESG: calculo agua ahorrada por categoria"),
]
for i, r in enumerate(norms):
    pdf.trow_plain(list(zip(r, [c[1] for c in norm_cols])), shade=(i%2==0))


# ══════════════════════════════════════════════════════════════════════════════
# CONTRAPORTADA
# ══════════════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.set_fill_color(*BK)
pdf.rect(0, 0, 210, 297, "F")
# Grid de puntos
pdf.set_fill_color(25, 40, 30)
for row in range(0, 300, 10):
    for col in range(0, 215, 10):
        pdf.rect(col, row, 0.8, 0.8, "F")
# Barra verde lateral
pdf.set_fill_color(*G2)
pdf.rect(0, 0, 5, 297, "F")
pdf.set_fill_color(*G3)
pdf.rect(5, 0, 1.5, 297, "F")

# Titulo
pdf.set_font("Helvetica", "B", 36)
pdf.set_text_color(*WH)
pdf.set_xy(14, 50)
pdf.cell(0, 18, "MermaOps")
pdf.set_fill_color(*G2)
pdf.rect(14, 70, 100, 1.5, "F")

# Subtitulo
pdf.set_font("Helvetica", "", 11)
pdf.set_text_color(*GL)
pdf.set_xy(14, 75)
pdf.multi_cell(180, 7, _s("Sistema Multi-Agente de IA para Reduccion de\nMerma Alimentaria en Supermercados Espanoles"))

# Resumen en columnas
pdf.set_y(108)
col_items = [
    [("12 Agentes IA", G2), ("10 con LLM real", TM), ("2 heuristicos", TM)],
    [("774/774 Tests", G3), ("< 2 segundos", TM), ("Sin API real", TM)],
    [("30+ Comandos", TK), ("Telegram nativo", TM), ("Streaming real", TM)],
    [("0,80 EUR/mes", AM), ("Prompt caching", TM), ("ROI > 500:1", TM)],
]
cw = 44
for i, col in enumerate(col_items):
    cx = 14 + i * cw
    pdf.set_fill_color(*col[0][1])
    pdf.rect(cx, pdf.get_y(), cw - 2, 2, "F")
    for j, (text, color) in enumerate(col):
        pdf.set_font("Helvetica", "B" if j==0 else "", 8 if j==0 else 7)
        pdf.set_text_color(*color)
        pdf.set_xy(cx, 112 + j * 8)
        pdf.cell(cw - 2, 6, _s(text), align="C")

pdf.set_y(145)
pdf.set_fill_color(30, 45, 35)
pdf.rect(14, pdf.get_y(), 182, 0.5, "F")
pdf.ln(5)

# Patrones implementados
titles_p = ["Loop agentico (Kuine)", "Fork-Merge (Anthropic 2024)",
            "Reflexion Loop (Shinn 2023)", "Intent 0-token", "Prompt Caching"]
colors_p = [G1, AM, PU, TK, G2]
for i, (title, col) in enumerate(zip(titles_p, colors_p)):
    pdf.set_xy(14, pdf.get_y())
    pdf.set_fill_color(*col)
    pdf.rect(14, pdf.get_y() + 1.5, 3, 5, "F")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*WH)
    pdf.set_xy(20, pdf.get_y())
    pdf.cell(80, 8, _s(title))
    if i % 2 == 1: pdf.ln(8)
pdf.ln(8)

# Normativa
pdf.set_fill_color(30, 45, 35)
pdf.rect(14, pdf.get_y(), 182, 0.5, "F")
pdf.ln(5)
norm_short = ["CE 178/2002", "RD 1334/1999", "Ley 7/2022", "Ley 49/2002", "CSRD 2026"]
for i, n in enumerate(norm_short):
    pdf.set_xy(14 + i * 37, pdf.get_y())
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(*G3)
    pdf.cell(36, 6, _s(n), align="C")
pdf.ln(10)

# Pie
pdf.set_fill_color(*G1)
pdf.rect(0, 255, 210, 42, "F")
pdf.set_fill_color(*G2)
pdf.rect(0, 255, 210, 2, "F")
pdf.set_font("Helvetica", "B", 11)
pdf.set_text_color(*WH)
pdf.set_xy(14, 262)
pdf.cell(0, 7, _s("TFM — Master en Inteligencia Artificial  |  2026"))
pdf.set_font("Helvetica", "", 9)
pdf.set_text_color(*GL)
pdf.set_xy(14, 271)
pdf.cell(0, 6, "alvaroferrermarg@gmail.com")
pdf.set_font("Helvetica", "I", 8)
pdf.set_xy(14, 279)
pdf.cell(0, 5, _s("Reduce la merma alimentaria hasta un 40% con IA multi-agente. Coste: 0,80 EUR/mes."))

# ── Output ─────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(OUT), exist_ok=True)
pdf.output(OUT)
size_kb = os.path.getsize(OUT) // 1024
print(f"PDF generado: {OUT}  ({size_kb} KB)")# ── Output ─────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(OUT), exist_ok=True)
pdf.output(OUT)
size_kb = os.path.getsize(OUT) // 1024
print(f"PDF generado: {OUT}  ({size_kb} KB)")
