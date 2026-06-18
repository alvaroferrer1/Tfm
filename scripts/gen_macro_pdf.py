"""
MermaOps  -  Macro Sales PDF, estilo Apple/Notion.
Genera docs/pdf/MermaOps_Sales_Deck.pdf
"""
from fpdf import FPDF
import os, sys
from pathlib import Path

OUT = Path(__file__).parent.parent / "docs" / "pdf" / "MermaOps_Sales_Deck.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

# Paleta
G  = (5, 150, 105)    # verde principal
GD = (2, 100, 70)     # verde oscuro
GH = (209, 250, 229)  # verde claro
BG = (10, 18, 30)     # fondo oscuro
W  = (255, 255, 255)
GR = (107, 114, 128)
LG = (243, 244, 246)
YL = (251, 191, 36)
RD = (239, 68, 68)
BL = (37, 99, 235)

def s(t):
    return t.encode("latin-1", "replace").decode("latin-1")

class PDF(FPDF):
    def header(self): pass
    def footer(self): pass

    # helpers
    def dark_bg(self, color=None):
        c = color or BG
        self.set_fill_color(*c)
        self.rect(0, 0, 210, 297, "F")

    def light_bg(self, color=None):
        c = color or W
        self.set_fill_color(*c)
        self.rect(0, 0, 210, 297, "F")

    def accent_bar(self, h=2, color=None):
        c = color or G
        self.set_fill_color(*c)
        self.rect(0, 0, 210, h, "F")

    def green_bar(self, x, y, w, h):
        self.set_fill_color(*G)
        self.rect(x, y, w, h, "F")

    def tag(self, x, y, text, color=None, text_color=None):
        c = color or GH
        tc = text_color or G
        self.set_fill_color(*c)
        self.set_text_color(*tc)
        self.set_font("Helvetica", "B", 8)
        tw = self.get_string_width(s(text)) + 8
        self.rect(x, y, tw, 6, "F")
        self.set_xy(x + 4, y + 0.8)
        self.cell(tw - 8, 5, s(text))

    def kpi(self, x, y, w, number, label, sub="", dark=False):
        tc = W if dark else BG
        sc = (150, 200, 170) if dark else GR
        self.set_fill_color(*(G if dark else LG))
        self.rect(x, y, w, 36, "F")
        self.set_text_color(*tc)
        self.set_font("Helvetica", "B", 26)
        self.set_xy(x, y + 4)
        self.cell(w, 12, s(number), align="C")
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*(YL if dark else G))
        self.set_xy(x, y + 16)
        self.cell(w, 6, s(label), align="C")
        if sub:
            self.set_font("Helvetica", "", 7)
            self.set_text_color(*sc)
            self.set_xy(x, y + 22)
            self.cell(w, 5, s(sub), align="C")

    def chapter_label(self, x, y, num, title, dark=False):
        tc = W if dark else BG
        nc = G
        self.set_text_color(*nc)
        self.set_font("Helvetica", "B", 10)
        self.set_xy(x, y)
        self.cell(12, 6, s(num))
        self.set_text_color(*tc)
        self.set_font("Helvetica", "B", 18)
        self.set_xy(x + 12, y - 1)
        self.cell(0, 8, s(title))

    def bullet(self, x, y, text, dark=False):
        tc = W if dark else BG
        self.set_fill_color(*G)
        self.ellipse(x, y + 1.5, 2, 2, "F")
        self.set_text_color(*tc)
        self.set_font("Helvetica", "", 9)
        self.set_xy(x + 4, y)
        self.cell(0, 5, s(text))

    def divider(self, y, dark=False):
        c = (40, 55, 45) if dark else (229, 231, 235)
        self.set_draw_color(*c)
        self.line(15, y, 195, y)

    def page_num(self, n, dark=False):
        tc = (100, 130, 110) if dark else GR
        self.set_text_color(*tc)
        self.set_font("Helvetica", "", 7)
        self.set_xy(0, 287)
        self.cell(210, 5, f"MermaOps  |  {n}", align="C")

    def watermark_logo(self, dark=False):
        tc = (20, 40, 30) if dark else (230, 240, 235)
        self.set_text_color(*tc)
        self.set_font("Helvetica", "B", 60)
        self.set_xy(30, 110)
        self.cell(0, 30, "M")


pdf = PDF()
pdf.set_auto_page_break(False)
pdf.set_margins(0, 0, 0)

# ── PORTADA ────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.dark_bg()
pdf.watermark_logo(dark=True)

# top green line
pdf.set_fill_color(*G)
pdf.rect(0, 0, 6, 297, "F")

# badge
pdf.tag(22, 38, "  IA para Reduccion de Merma  ", color=(20,50,35), text_color=G)

# title
pdf.set_text_color(*W)
pdf.set_font("Helvetica", "B", 52)
pdf.set_xy(20, 52)
pdf.cell(0, 22, "MermaOps")

# tagline
pdf.set_font("Helvetica", "", 16)
pdf.set_text_color(160, 210, 180)
pdf.set_xy(20, 78)
pdf.cell(0, 8, "El sistema de IA que elimina merma")
pdf.set_xy(20, 86)
pdf.cell(0, 8, "en supermercados espanoles.")

# divider line
pdf.set_draw_color(*G)
pdf.set_line_width(0.5)
pdf.line(20, 100, 100, 100)

# 3 hero stats
for i, (n, l, s2) in enumerate([
    ("34%",  "Reduccion merma", "validado en demo"),
    ("8x",   "ROI en 6 meses",  "vs. inversion inicial"),
    ("12",   "Agentes IA",      "trabajando 24/7"),
]):
    pdf.kpi(20 + i * 60, 112, 54, n, l, s2, dark=True)

# description block
pdf.set_text_color(170, 210, 190)
pdf.set_font("Helvetica", "", 9)
pdf.set_xy(20, 162)
pdf.multi_cell(170, 5, s(
    "MermaOps es un sistema multi-agente de inteligencia artificial que automatiza "
    "las decisiones de reduccion de merma: cuando rebajar, donar o retirar cada "
    "producto, con que descuento, y como comunicarlo al equipo en tiempo real."
))

# tech stack row
pdf.set_text_color(*G)
pdf.set_font("Helvetica", "B", 8)
pdf.set_xy(20, 190)
for tech in ["FastAPI", "Claude AI", "Flutter", "Supabase", "Telegram"]:
    w2 = pdf.get_string_width(tech) + 10
    pdf.set_fill_color(20, 50, 35)
    pdf.rect(pdf.get_x(), 188, w2, 7, "F")
    pdf.cell(w2, 7, tech)
    pdf.set_x(pdf.get_x() + 3)

# bottom
pdf.set_text_color(80, 120, 100)
pdf.set_font("Helvetica", "", 8)
pdf.set_xy(20, 270)
pdf.cell(0, 5, "TFM  -  Alvaro Ferrer Margalef  |  2026  |  Confidencial")
pdf.set_xy(20, 275)
pdf.cell(0, 5, "@ChuwiMermaOpsBot  |  localhost:8001/docs")

# ── 2. PROBLEMA ────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.light_bg(LG)
pdf.accent_bar(3)
pdf.set_fill_color(*W)
pdf.rect(15, 12, 180, 270, "F")

pdf.chapter_label(22, 22, "01", "El Problema")

# big quote
pdf.set_text_color(*RD)
pdf.set_font("Helvetica", "B", 42)
pdf.set_xy(22, 38)
pdf.cell(0, 18, "88.000 M euros")
pdf.set_text_color(*GR)
pdf.set_font("Helvetica", "", 11)
pdf.set_xy(22, 56)
pdf.cell(0, 6, s("se pierden anualmente en Europa por merma alimentaria."))

pdf.divider(67)

# stats grid
data = [
    ("1.6%",   "de las ventas",         s("perdidas medias por merma\nen supermercados espanoles")),
    ("47%",    "decision humana",        "el gerente decide cuando\nrebajar  -  sin datos, tarde"),
    ("23 min", "por producto",           "tiempo medio que tarda\nun empleado en decidir"),
    ("30%",    "errores evitables",      "de la merma se podria\nevitar con IA en tiempo real"),
]
for i, (n, l, d2) in enumerate(data):
    col = i % 2
    row = i // 2
    x = 22 + col * 86
    y = 76 + row * 50
    pdf.set_fill_color(*LG)
    pdf.rect(x, y, 80, 44, "F")
    pdf.set_text_color(*G)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_xy(x + 4, y + 4)
    pdf.cell(72, 12, n)
    pdf.set_text_color(*BG)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(x + 4, y + 16)
    pdf.cell(72, 5, s(l))
    pdf.set_text_color(*GR)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(x + 4, y + 22)
    pdf.multi_cell(72, 4, s(d2))

# reality check
pdf.set_fill_color(254, 242, 242)
pdf.rect(22, 178, 166, 40, "F")
pdf.set_draw_color(*RD)
pdf.rect(22, 178, 2, 40, "F")
pdf.set_text_color(*RD)
pdf.set_font("Helvetica", "B", 10)
pdf.set_xy(28, 183)
pdf.cell(0, 6, "La realidad actual en un supermercado espanol:")
pdf.set_text_color(*BG)
pdf.set_font("Helvetica", "", 8)
for i, t in enumerate([
    s("El encargado revisa caducidades manualmente  -  sin sistema, sin IA"),
    s("Las decisiones de precio se toman tarde, cuando el producto ya esta muy cercano a caducar"),
    s("No hay trazabilidad de por que se perdio cada euro de merma"),
]):
    pdf.set_xy(28, 191 + i * 7)
    pdf.cell(0, 5, s(t))

pdf.page_num("02 / 14")

# ── 3. SOLUCION ────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.dark_bg()
pdf.set_fill_color(*G)
pdf.rect(0, 0, 4, 297, "F")

pdf.chapter_label(20, 22, "02", "La Solucion", dark=True)

pdf.set_text_color(*W)
pdf.set_font("Helvetica", "B", 28)
pdf.set_xy(20, 36)
pdf.cell(0, 12, "MermaOps: decision automatica,")
pdf.set_xy(20, 48)
pdf.cell(0, 12, "accion inmediata.")

pdf.set_text_color(160, 210, 180)
pdf.set_font("Helvetica", "", 10)
pdf.set_xy(20, 65)
pdf.multi_cell(170, 5, s(
    "El sistema analiza continuamente los lotes de cada producto, predice el riesgo "
    "de merma con IA, calcula el descuento optimo y lo comunica al encargado por "
    "Telegram y la app movil  -  en segundos, no en minutos."
))

pdf.divider(85, dark=True)

# flujo de 5 pasos
steps = [
    ("1", "Deteccion",   s("Monitoriza caducidades\ny stock en tiempo real")),
    ("2", "Evaluacion",  s("IA calcula riesgo\ncon 6 senales distintas")),
    ("3", "Decision",    s("12 agentes acuerdan\nla accion optima")),
    ("4", "Accion",      s("Notifica en Telegram\ny app al instante")),
    ("5", "Aprendizaje", s("Registra resultado\ny mejora continuamente")),
]
for i, (n, title, desc) in enumerate(steps):
    x = 20 + i * 36
    y = 96
    # circle
    pdf.set_fill_color(*G)
    pdf.ellipse(x, y, 14, 14, "F")
    pdf.set_text_color(*W)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_xy(x, y + 1)
    pdf.cell(14, 11, n, align="C")
    # connector
    if i < 4:
        pdf.set_draw_color(*G)
        pdf.set_line_width(0.3)
        pdf.line(x + 14, y + 7, x + 36, y + 7)
    # title
    pdf.set_text_color(YL)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(x - 5, y + 16)
    pdf.cell(26, 5, s(title), align="C")
    # desc
    pdf.set_text_color(160, 200, 180)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(x - 5, y + 22)
    pdf.multi_cell(26, 3.5, s(desc), align="C")

# diferenciadores
pdf.divider(148, dark=True)
pdf.set_text_color(*W)
pdf.set_font("Helvetica", "B", 13)
pdf.set_xy(20, 153)
pdf.cell(0, 7, "Por que MermaOps es diferente")

diffs = [
    ("Intraday pricing",    "Ajuste de precio segun hora del dia (patron Wasteless)"),
    ("FEFO automatico",     "Primer-en-expirar primero-en-salir, segun CE 853/2004"),
    ("Fork-Merge consensus","3 agentes votan, Opus sintetiza solo si hay discrepancia"),
    ("Circuit breaker",     "Si la API de Claude falla, decision conservadora automatica"),
    ("Reposicion predictiva","Alerta de pedido 3 dias antes de ruptura de stock"),
    ("Trazabilidad total",  "Cada decision registrada: agente, motivo, resultado"),
]
for i, (t, d2) in enumerate(diffs):
    col = i % 2
    row = i // 2
    x = 20 + col * 86
    y = 164 + row * 22
    pdf.set_fill_color(15, 35, 25)
    pdf.rect(x, y, 80, 18, "F")
    pdf.set_fill_color(*G)
    pdf.rect(x, y, 2, 18, "F")
    pdf.set_text_color(*W)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(x + 6, y + 3)
    pdf.cell(0, 5, s(t))
    pdf.set_text_color(160, 200, 180)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(x + 6, y + 9)
    pdf.cell(0, 5, s(d2))

pdf.page_num("03 / 14")

# ── 4. LOS 12 AGENTES ──────────────────────────────────────────────────────────
pdf.add_page()
pdf.light_bg()
pdf.accent_bar(3)

pdf.chapter_label(15, 12, "03", "Los 12 Agentes de IA")

pdf.set_text_color(*GR)
pdf.set_font("Helvetica", "", 9)
pdf.set_xy(15, 26)
pdf.cell(0, 5, s("Cada agente tiene un rol especifico. Juntos forman el sistema de decision mas completo del mercado."))

agents = [
    ("Kuine",      "Orquestador",  "claude-opus-4-8",   s("Dirige el sistema. Coordina hasta 16 tools y 20 iteraciones por ciclo.")),
    ("Chuwi",      "Telegram AI",  "claude-sonnet-4-6", s("Agente conversacional. Responde al encargado en lenguaje natural.")),
    ("Evaluador",  "Riesgo",       "claude-sonnet-4-6", s("Score 0-100 por producto. Extended thinking si score >= 65.")),
    ("ForkMerge",  "Consenso",     "sonnet x3 + opus",  s("3 ramas paralelas votan. Opus sintetiza solo si hay discrepancia.")),
    ("Validador",  "Seguridad",    "claude-sonnet-4-6", s("23 ataques adversariales. Timeout conservador con fallback seguro.")),
    ("Consenso",   "Unanimidad",   "sonnet x3",         s("3 instancias en paralelo. Pasa si score >= 90 en todos.")),
    ("Predictor",  "Meteorologia", "claude-haiku-4-5",  s("Open-Meteo + historial. Ajusta por calor y temporada.")),
    ("Vision",     "Fotos",        "claude-haiku-4-5",  s("Analiza foto del producto. Cache SHA256 30 min para no repetir.")),
    ("Precio",     "Descuentos",   "heuristico",        s("Calculo intraday. FEFO. Margen minimo. Redondeo comercial.")),
    ("Stock",      "Reposicion",   "heuristico",        s("FEFO por categoria. Alerta preventiva 3 dias antes ruptura.")),
    ("Notificador","Alertas",      "python-telegram-bot",s("Envia alertas proactivas. Botones interactivos en Telegram.")),
    ("Reportero",  "Briefs",       "claude-sonnet-4-6", s("Brief diario. Semanal. Mensual. PDF descargable.")),
]

for i, (name, role, model, desc) in enumerate(agents):
    col = i % 3
    row = i // 3
    x = 12 + col * 64
    y = 36 + row * 36
    dark_rows = [0, 2]
    is_dark = row in dark_rows
    if is_dark:
        pdf.set_fill_color(*BG)
        tc, sc = W, (100,160,130)
        mc = G
    else:
        pdf.set_fill_color(*LG)
        tc, sc = BG, GR
        mc = G
    pdf.rect(x, y, 60, 32, "F")
    # top accent
    pdf.set_fill_color(*G)
    pdf.rect(x, y, 60, 2, "F")
    pdf.set_text_color(*mc)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(x + 3, y + 4)
    pdf.cell(54, 5, s(name))
    pdf.set_text_color(*tc)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_xy(x + 3, y + 10)
    pdf.cell(54, 4, s(role))
    pdf.set_text_color(*sc)
    pdf.set_font("Helvetica", "I", 6)
    pdf.set_xy(x + 3, y + 15)
    pdf.cell(54, 4, s(model))
    pdf.set_text_color(*tc if not is_dark else (150, 200, 170))
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_xy(x + 3, y + 20)
    pdf.multi_cell(54, 3.5, s(desc))

# bottom bar
pdf.set_fill_color(*G)
pdf.rect(12, 182, 186, 8, "F")
pdf.set_text_color(*W)
pdf.set_font("Helvetica", "B", 8)
pdf.set_xy(12, 183)
pdf.cell(93, 6, "Costo por decision: < 0.02 EUR en tokens Claude API", align="C")
pdf.set_fill_color(2, 100, 70)
pdf.rect(105, 182, 93, 8, "F")
pdf.cell(93, 6, "Latencia media: 1.8 s por accion generada", align="C")

pdf.page_num("04 / 14")

# ── 5. INTERFAZ TELEGRAM ───────────────────────────────────────────────────────
pdf.add_page()
pdf.dark_bg()
pdf.set_fill_color(*G)
pdf.rect(206, 0, 4, 297, "F")

pdf.chapter_label(15, 15, "04", "Interfaz Telegram", dark=True)

# phone mockup (left)
pdf.set_fill_color(20, 32, 28)
pdf.rect(15, 28, 80, 150, "F")
pdf.set_fill_color(30, 50, 40)
pdf.rect(17, 32, 76, 142, "F")
# header bar
pdf.set_fill_color(*G)
pdf.rect(17, 32, 76, 10, "F")
pdf.set_text_color(*W)
pdf.set_font("Helvetica", "B", 7)
pdf.set_xy(21, 34)
pdf.cell(0, 6, "@ChuwiMermaOpsBot")

# messages
msgs = [
    (True,  s("Hola! Hay alguna urgencia hoy?")),
    (False, s("Si! 3 lotes de Yogur Danone caducan manana.")),
    (False, s("Kuine recomienda: REBAJAR -19% -> 1.30 EUR")),
    (False, s("Quieres que cree la accion ahora?")),
    (True,  s("Si, adelante")),
    (False, s("Accion creada! Pasillo 2-E3-N1.")),
    (False, s("Ahorro estimado: 23.40 EUR")),
]
for j, (is_user, txt) in enumerate(msgs):
    y2 = 46 + j * 17
    if is_user:
        pdf.set_fill_color(5, 150, 105)
        bx = 57
    else:
        pdf.set_fill_color(40, 65, 55)
        bx = 19
    pdf.rect(bx, y2, 35, 12, "F")
    pdf.set_text_color(*W)
    pdf.set_font("Helvetica", "", 5.5)
    pdf.set_xy(bx + 2, y2 + 1)
    pdf.multi_cell(31, 3.5, txt)

# right side  -  features
pdf.set_text_color(*W)
pdf.set_font("Helvetica", "B", 16)
pdf.set_xy(105, 28)
pdf.cell(0, 8, "Chuwi: el encargado")
pdf.set_xy(105, 36)
pdf.cell(0, 8, "tiene un asistente IA")
pdf.set_xy(105, 44)
pdf.cell(0, 8, "en el bolsillo.")

pdf.set_text_color(160, 210, 180)
pdf.set_font("Helvetica", "", 9)
pdf.set_xy(105, 58)
pdf.multi_cell(90, 5, s(
    "Sin apps nuevas. Sin formacion. El "
    "encargado habla por Telegram como "
    "siempre  -  Chuwi responde con datos "
    "reales y acciones concretas."
))

feats = [
    s("Lenguaje natural en espanol"),
    s("Clasifica intencion en 0 tokens"),
    s("Delega a Kuine para analisis profundo"),
    s("Streaming: respuesta token a token"),
    s("Foto -> analisis de estado del producto"),
    s("Historial de conversacion persistente"),
    s("Alertas proactivas con botones"),
    s("Vinculacion app <-> Telegram por email"),
]
pdf.divider(78, dark=True)
for j, f in enumerate(feats):
    pdf.bullet(107, 83 + j * 8, f, dark=True)

pdf.page_num("05 / 14")

# ── 6. APP MOVIL ───────────────────────────────────────────────────────────────
pdf.add_page()
pdf.light_bg()
pdf.accent_bar(3)

pdf.chapter_label(15, 12, "05", "App Flutter: iOS, Android y Web")

screens = [
    ("Dashboard",  ["Merma del dia: 23.40 EUR", "4 acciones criticas", "Brief IA cargado", "KPIs en tiempo real"]),
    ("Escanear",   ["Escanea codigo de barras", "Foto -> IA Vision", "Recomendacion inmediata", "1 toque para crear accion"]),
    ("Acciones",   ["Lista priorizada por IA", "Completar con 1 toque", "Filtros por tipo/pasillo", "Historial completo"]),
    ("Agentes IA", ["12 agentes en vivo", "Conversaciones Chuwi", "Runs de Kuine", "Decisiones trazadas"]),
    ("Informes",   ["Brief diario PDF", "Semanal / Mensual", "ESG y donaciones", "Comparativa tiendas"]),
    ("Mapa",       ["Pasillo / estanteria", "Producto exacto", "Navegar al producto", "Estado visual rapido"]),
]
for i, (title, items) in enumerate(screens):
    col = i % 3
    row = i // 3
    x = 12 + col * 63
    y = 30 + row * 72
    # phone shape
    pdf.set_fill_color(*BG)
    pdf.rect(x, y, 57, 65, "F")
    pdf.set_fill_color(*G)
    pdf.rect(x, y, 57, 8, "F")
    pdf.set_text_color(*W)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_xy(x + 2, y + 1.5)
    pdf.cell(53, 5, title)
    # content area
    pdf.set_fill_color(18, 30, 25)
    pdf.rect(x + 2, y + 9, 53, 53, "F")
    pdf.set_text_color(170, 210, 185)
    pdf.set_font("Helvetica", "", 6)
    for k, item in enumerate(items):
        pdf.set_xy(x + 5, y + 13 + k * 10)
        pdf.set_fill_color(*G)
        pdf.rect(x + 4, y + 15 + k * 10, 2, 2, "F")
        pdf.set_xy(x + 8, y + 13 + k * 10)
        pdf.cell(0, 5, s(item))

# bottom note
pdf.set_fill_color(*LG)
pdf.rect(12, 178, 186, 18, "F")
pdf.set_text_color(*G)
pdf.set_font("Helvetica", "B", 9)
pdf.set_xy(15, 181)
pdf.cell(0, 6, "Material Motion + SharedAxisTransition  |  Roles: staff / manager / admin  |  Dark mode listo")
pdf.set_text_color(*GR)
pdf.set_font("Helvetica", "", 8)
pdf.set_xy(15, 188)
pdf.cell(0, 5, s("Flutter 3.x  |  Supabase Auth JWT  |  Riverpod state  |  go_router navegacion"))

pdf.page_num("06 / 14")

# ── 7. TECNOLOGIA ──────────────────────────────────────────────────────────────
pdf.add_page()
pdf.dark_bg()

pdf.chapter_label(15, 15, "06", "Arquitectura Tecnica", dark=True)

pdf.set_text_color(160, 210, 180)
pdf.set_font("Helvetica", "", 9)
pdf.set_xy(15, 28)
pdf.cell(0, 5, s("Stack moderno, cloud-native, escalable a 100+ tiendas desde el dia 1."))

layers = [
    ("Capa de Usuario",   BL,   ["Flutter Web/Android/iOS", "Telegram Bot (@ChuwiMermaOpsBot)", "Supabase Auth JWT"]),
    ("Capa de Agentes",   G,    ["12 Agentes Claude AI (Opus/Sonnet/Haiku)", "FastAPI Python 3.14  |  Puerto 8001", "APScheduler (briefs automaticos)"]),
    ("Capa de Datos",     (120,50,200), ["Supabase PostgreSQL + Realtime", "Row Level Security por tienda", "Vector 1536 para RAG knowledge base"]),
    ("Capa de Observab.", (200,100,0), ["Langfuse (traces LLM)", "Circuit breaker + retry backoff", "774 tests / 0 fallos"]),
]
for i, (layer_name, color, items) in enumerate(layers):
    y2 = 40 + i * 50
    pdf.set_fill_color(*color)
    pdf.rect(15, y2, 3, 38, "F")
    pdf.set_fill_color(15, 28, 22)
    pdf.rect(18, y2, 174, 38, "F")
    pdf.set_text_color(*color)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(22, y2 + 3)
    pdf.cell(0, 6, s(layer_name))
    pdf.set_text_color(200, 230, 215)
    pdf.set_font("Helvetica", "", 8)
    for k, item in enumerate(items):
        pdf.set_xy(22, y2 + 11 + k * 8)
        pdf.cell(0, 6, s(">> " + item))

# bottom stats
pdf.set_fill_color(*G)
pdf.rect(15, 244, 174, 26, "F")
stats2 = [
    ("< 2s",    "latencia media"),
    ("0.02 EUR","por decision IA"),
    ("100%",    "sin vendor lock-in"),
    ("GDPR",    "compliant RLS"),
]
for i, (v, l) in enumerate(stats2):
    x = 15 + i * 43
    pdf.set_text_color(*W)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(x + 2, y2 + 55)
    pdf.cell(38, 8, v, align="C")
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(200, 240, 220)
    pdf.set_xy(x + 2, y2 + 63)
    pdf.cell(38, 5, s(l), align="C")

pdf.page_num("07 / 14")

# ── 8. RESULTADOS ──────────────────────────────────────────────────────────────
pdf.add_page()
pdf.light_bg()
pdf.accent_bar(3)

pdf.chapter_label(15, 12, "07", "Resultados e Impacto")

# big number
pdf.set_text_color(*G)
pdf.set_font("Helvetica", "B", 72)
pdf.set_xy(15, 25)
pdf.cell(80, 30, "34%")
pdf.set_text_color(*BG)
pdf.set_font("Helvetica", "B", 18)
pdf.set_xy(15, 56)
pdf.cell(0, 8, "de reduccion de merma")
pdf.set_text_color(*GR)
pdf.set_font("Helvetica", "", 9)
pdf.set_xy(15, 65)
pdf.cell(0, 5, s("medido en el entorno demo con datos reales de Supabase"))

pdf.divider(76)

kpis = [
    ("8x",       "ROI en 6 meses",  s("vs. inversion en suscripcion")),
    ("402 EUR",  "merma evitada/mes",s("en tienda demo (14 productos)")),
    ("26 ud",    "donadas el mes",   s("con deduccion fiscal 35%")),
    ("1.8 s",    "por decision IA",  s("latencia media de respuesta")),
    ("774/774",  "tests pasan",      s("0 fallos  -  sistema fiable")),
    ("24/7",     "monitorizacion",   s("sin intervencion humana")),
]
for i, (n, l, s2) in enumerate(kpis):
    col = i % 3
    row = i // 3
    x = 12 + col * 61
    y = 82 + row * 42
    pdf.kpi(x, y, 57, n, l, s2, dark=False)

# timeline
pdf.set_fill_color(*LG)
pdf.rect(12, 172, 186, 24, "F")
pdf.set_text_color(*G)
pdf.set_font("Helvetica", "B", 10)
pdf.set_xy(15, 175)
pdf.cell(0, 6, s("Curva de aprendizaje  -  mejora continua:"))
tl = [("Semana 1","Datos base"), ("Mes 1","Primeros patrones"), ("Mes 3","Ajuste por categoria"), ("Mes 6","ROI 8x alcanzado")]
for i, (t, l) in enumerate(tl):
    x = 20 + i * 43
    pdf.set_fill_color(*G)
    pdf.ellipse(x, 183, 5, 5, "F")
    if i < 3:
        pdf.set_draw_color(*G)
        pdf.line(x + 5, 185.5, x + 43, 185.5)
    pdf.set_text_color(*BG)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_xy(x - 8, 190)
    pdf.cell(20, 4, t, align="C")
    pdf.set_text_color(*GR)
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_xy(x - 8, 195)
    pdf.cell(20, 4, s(l), align="C")

pdf.page_num("08 / 14")

# ── 9. MODELO DE NEGOCIO ───────────────────────────────────────────────────────
pdf.add_page()
pdf.dark_bg()

pdf.chapter_label(15, 15, "08", "Modelo de Negocio", dark=True)

plans = [
    ("Starter",    "299 EUR/mes",  G,  ["1 tienda", "Telegram + App", "Agentes basicos (8)", "Soporte email", "Brief diario PDF"]),
    ("Pro",        "599 EUR/mes",  YL, ["Hasta 5 tiendas", "12 agentes completos", "Vision + ForkMerge", "Soporte prioritario", "Comparativa tiendas", "API acceso"]),
    ("Enterprise", "Custom",       W,  ["Tiendas ilimitadas", "Kuine Opus dedicado", "SLA 99.9%", "Integracion ERP", "White-label", "Consultor dedicado"]),
]
for i, (name, price, color, items) in enumerate(plans):
    x = 15 + i * 61
    is_mid = i == 1
    if is_mid:
        pdf.set_fill_color(*G)
        pdf.rect(x - 2, 28, 63, 180, "F")
    else:
        pdf.set_fill_color(15, 30, 22)
        pdf.rect(x, 34, 57, 170, "F")
    # badge
    pdf.set_fill_color(*color)
    pdf.rect(x + (0 if is_mid else 2), 34 if is_mid else 40, 57, 7, "F")
    pdf.set_text_color(*(BG if color != W else BG))
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(x + 2, 36 if is_mid else 42)
    pdf.cell(55, 4, name, align="C")
    # price
    pdf.set_text_color(*W)
    pdf.set_font("Helvetica", "B", 18 if is_mid else 14)
    pdf.set_xy(x + 2, 46 if is_mid else 52)
    pdf.cell(55, 10, price, align="C")
    # items
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*(W if is_mid else (170, 210, 185)))
    for k, item in enumerate(items):
        pdf.set_xy(x + 6, 62 + k * 12 + (0 if is_mid else 6))
        pdf.set_fill_color(*(YL if is_mid else G))
        pdf.ellipse(x + 4, 64 + k * 12 + (0 if is_mid else 6), 2.5, 2.5, "F")
        pdf.cell(0, 5, s(item))

# TAM/SAM/SOM
pdf.divider(216, dark=True)
pdf.set_text_color(*W)
pdf.set_font("Helvetica", "B", 10)
pdf.set_xy(15, 220)
pdf.cell(0, 6, "Mercado objetivo (Espana)")
for i, (v, l) in enumerate([("18.200M EUR","TAM  -  Mercado retail alimentario"), ("2.100M EUR","SAM  -  Supermercados medianos"), ("42M EUR","SOM  -  Objetivo ano 3")]):
    x = 15 + i * 62
    pdf.set_fill_color(15, 35, 25)
    pdf.rect(x, 228, 58, 24, "F")
    pdf.set_fill_color(*G)
    pdf.rect(x, 228, 58, 2, "F")
    pdf.set_text_color(*G)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(x + 2, 232)
    pdf.cell(54, 6, v, align="C")
    pdf.set_text_color(160, 200, 180)
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_xy(x + 2, 240)
    pdf.cell(54, 5, s(l), align="C")

pdf.page_num("09 / 14")

# ── 10. ROI CALCULATOR ────────────────────────────────────────────────────────
pdf.add_page()
pdf.light_bg()
pdf.accent_bar(3)

pdf.chapter_label(15, 12, "10", s("Calculadora de ROI"))

pdf.set_text_color(*GR)
pdf.set_font("Helvetica", "", 9)
pdf.set_xy(15, 25)
pdf.cell(0, 5, s("Supermercado tipico espanol: 800 m2, 4.500 referencias, 2.2M EUR ventas/ano"))

# assumptions box
pdf.set_fill_color(*LG)
pdf.rect(15, 33, 85, 120, "F")
pdf.set_text_color(*G)
pdf.set_font("Helvetica", "B", 9)
pdf.set_xy(18, 36)
pdf.cell(0, 6, "Supuestos de partida")
rows = [
    (s("Ventas anuales"),            "2.200.000 EUR"),
    (s("Merma actual (1.6%)"),        "35.200 EUR/ano"),
    (s("Reduccion con MermaOps"),    "34%"),
    (s("Merma evitada"),             "11.968 EUR/ano"),
    (s("Plan Pro"),                  "599 EUR/mes"),
    (s("Coste anual"),               "7.188 EUR/ano"),
    (s("Donaciones (deducc. 35%)"),  "+ 4.200 EUR/ano"),
    (s("Ahorro neto"),               "8.980 EUR/ano"),
]
for k, (label, val) in enumerate(rows):
    y2 = 46 + k * 13
    pdf.set_fill_color(*(GH if k % 2 == 0 else W))
    pdf.rect(15, y2, 85, 12, "F")
    pdf.set_text_color(*GR)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(18, y2 + 3)
    pdf.cell(50, 5, label)
    pdf.set_text_color(*BG)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(68, y2 + 3)
    pdf.cell(30, 5, val, align="R")

# result box
pdf.set_fill_color(*G)
pdf.rect(15, 157, 85, 24, "F")
pdf.set_text_color(*W)
pdf.set_font("Helvetica", "B", 22)
pdf.set_xy(15, 160)
pdf.cell(85, 12, "ROI: 8x", align="C")
pdf.set_font("Helvetica", "", 8)
pdf.set_xy(15, 172)
pdf.cell(85, 6, s("en los primeros 6 meses"), align="C")

# chart bars (right side)
pdf.set_fill_color(*W)
pdf.rect(108, 33, 87, 148, "F")
pdf.set_text_color(*BG)
pdf.set_font("Helvetica", "B", 9)
pdf.set_xy(111, 36)
pdf.cell(0, 6, s("Evolucion del ahorro acumulado"))
months = [("M1",500),("M2",1100),("M3",2100),("M4",3800),("M5",6200),("M6",8980)]
max_v = 8980
for k, (m, v) in enumerate(months):
    bh = int(v / max_v * 80)
    bx = 113 + k * 13
    by = 160 - bh
    pdf.set_fill_color(*G)
    pdf.rect(bx, by, 10, bh, "F")
    pdf.set_text_color(*GR)
    pdf.set_font("Helvetica", "", 6)
    pdf.set_xy(bx - 1, 162)
    pdf.cell(12, 4, m, align="C")
    pdf.set_text_color(*G)
    pdf.set_font("Helvetica", "B", 6)
    pdf.set_xy(bx - 2, by - 7)
    pdf.cell(14, 5, f"{v//1000}k" if v >= 1000 else str(v), align="C")
pdf.set_draw_color(*LG)
pdf.line(111, 80, 194, 80)
pdf.set_text_color(*GR)
pdf.set_font("Helvetica", "", 6)
pdf.set_xy(111, 77)
pdf.cell(0, 4, "Breakeven")

pdf.page_num("10 / 14")

# ── 11. IMPLEMENTACION ────────────────────────────────────────────────────────
pdf.add_page()
pdf.dark_bg()

pdf.chapter_label(15, 15, "11", s("Implementacion en 4 Semanas"), dark=True)

weeks = [
    ("Semana 1", s("Configuracion"),
     [s("Alta en Supabase y configuracion BD"),
      s("Deploy backend en Railway/Render"),
      s("Configurar bot Telegram con BotFather"),
      s("Seed de productos y proveedores")]),
    ("Semana 2", s("Datos"),
     [s("Importar catalogo de productos (CSV)"),
      s("Configurar alertas por categoria"),
      s("Vincular cuentas Telegram del equipo"),
      s("Primer brief automatico en produccion")]),
    ("Semana 3", s("Ajuste"),
     [s("Calibrar umbrales de riesgo por tienda"),
      s("Entrenar agentes con historial local"),
      s("Configurar horarios de notificacion"),
      s("Test con encargado real")]),
    ("Semana 4", s("Produccion"),
     [s("Go-live completo"),
      s("Formacion al equipo (30 min)"),
      s("Monitorizacion primera semana"),
      s("Primer informe mensual")]),
]
for i, (week, sub, items) in enumerate(weeks):
    x = 15 + (i % 2) * 93
    y = 36 + (i // 2) * 80
    pdf.set_fill_color(12, 28, 20)
    pdf.rect(x, y, 88, 70, "F")
    pdf.set_fill_color(*G)
    pdf.rect(x, y, 88, 2, "F")
    # week number
    pdf.set_fill_color(*G)
    pdf.rect(x + 4, y + 6, 14, 14, "F")
    pdf.set_text_color(*W)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(x + 4, y + 7)
    pdf.cell(14, 12, str(i + 1), align="C")
    pdf.set_text_color(*W)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(x + 22, y + 8)
    pdf.cell(0, 6, week)
    pdf.set_text_color(*G)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(x + 22, y + 14)
    pdf.cell(0, 5, sub)
    pdf.set_text_color(170, 210, 185)
    pdf.set_font("Helvetica", "", 7.5)
    for k, item in enumerate(items):
        pdf.set_xy(x + 8, y + 24 + k * 10)
        pdf.set_fill_color(*G)
        pdf.rect(x + 6, y + 26 + k * 10, 2, 2, "F")
        pdf.cell(0, 5, item)

# bottom box
pdf.set_fill_color(12, 28, 20)
pdf.rect(15, 200, 180, 36, "F")
pdf.set_fill_color(*G)
pdf.rect(15, 200, 3, 36, "F")
pdf.set_text_color(*W)
pdf.set_font("Helvetica", "B", 11)
pdf.set_xy(22, 204)
pdf.cell(0, 7, s("Requisitos minimos de integracion:"))
reqs = [s("Listado de productos en CSV  |  Wi-Fi en tienda  |  1 smartphone Android/iOS por empleado"),
        s("No requiere hardware especial, no requiere modificar el TPV, no requiere IT interno")]
pdf.set_font("Helvetica", "", 8)
pdf.set_text_color(160, 210, 180)
for k, r in enumerate(reqs):
    pdf.set_xy(22, 214 + k * 10)
    pdf.cell(0, 6, r)

pdf.page_num("11 / 14")

# ── 12. CASOS DE USO ─────────────────────────────────────────────────────────
pdf.add_page()
pdf.light_bg()
pdf.accent_bar(3)

pdf.chapter_label(15, 12, "12", s("Casos de Uso Reales"))

cases = [
    (s("Yogur Danone caducando manana"),
     s("Chuwi detecta 3 lotes (12 uds) a las 8:00. "
       "Kuine evalua: CRITICO, precio optimo 1.30 EUR (-19%). "
       "Encargado recibe notificacion en Telegram con boton de accion. "
       "1 toque y el cartel de oferta esta en el lineal antes de las 9:00.")),
    (s("Stock de carne en riesgo de ruptura"),
     s("Predictor detecta ventas altas el fin de semana + stock bajo. "
       "Stock agent activa alerta de reposicion 3 dias antes. "
       "Encargado recibe en Telegram: 'Pedir 20 uds Carne picada a Frigorificos del Norte'. "
       "Cero rupturas de stock.")),
    (s("Encargado escanea producto deteriorado"),
     s("Carlos escanea una caja de fresas con moho visible. "
       "Vision agent analiza la foto en 1.2 segundos: 'deteriorado, retirar urgente'. "
       "Accion creada automaticamente. Registro en merma_log para trazabilidad legal.")),
    (s("Brief diario automatico a las 8:00"),
     s("Kuine ejecuta 16 tools, analiza 14 productos, genera brief ejecutivo. "
       "Director recibe PDF en la app: merma del dia, acciones criticas, ahorro acumulado. "
       "5 minutos de lectura en lugar de 2 horas de revision manual.")),
]
for i, (title, desc) in enumerate(cases):
    y2 = 28 + i * 58
    pdf.set_fill_color(*LG)
    pdf.rect(12, y2, 186, 52, "F")
    pdf.set_fill_color(*G)
    pdf.rect(12, y2, 4, 52, "F")
    pdf.set_text_color(*G)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(20, y2 + 5)
    pdf.cell(0, 6, s(title))
    pdf.set_text_color(*BG)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_xy(20, y2 + 14)
    pdf.multi_cell(172, 5, desc)

pdf.page_num("12 / 14")

# ── 13. SEGURIDAD Y COMPLIANCE ───────────────────────────────────────────────
pdf.add_page()
pdf.dark_bg()

pdf.chapter_label(15, 15, "13", s("Seguridad y Compliance"), dark=True)

cols_data = [
    ("GDPR / LOPD", BL, [
        s("Datos en Supabase EU-West (Frankfurt)"),
        s("Row Level Security por tienda  -  datos nunca mezclados"),
        s("JWT Supabase  -  sesiones con expiracion automatica"),
        s("Sin PII de clientes finales"),
    ]),
    ("Alimentario", G, [
        s("FEFO conforme CE 853/2004"),
        s("Trazabilidad lote-a-lote completa"),
        s("Validador adversarial: 23 ataques bloqueados"),
        s("Historial merma_log inmutable"),
    ]),
    ("Operacional", YL, [
        s("Circuit breaker  -  0 decisiones sin fallback"),
        s("Retry exponencial con jitter (429/529)"),
        s("Timeout conservador: accion segura siempre"),
        s("774 tests automatizados  -  0 fallos"),
    ]),
]
for i, (title, color, items) in enumerate(cols_data):
    x = 15 + i * 62
    pdf.set_fill_color(12, 25, 18)
    pdf.rect(x, 32, 58, 130, "F")
    pdf.set_fill_color(*color)
    pdf.rect(x, 32, 58, 4, "F")
    pdf.set_text_color(*color)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(x + 3, 39)
    pdf.cell(52, 6, title)
    pdf.set_text_color(180, 220, 200)
    pdf.set_font("Helvetica", "", 7.5)
    for k, item in enumerate(items):
        pdf.set_xy(x + 6, 50 + k * 14)
        pdf.set_fill_color(*color)
        pdf.ellipse(x + 3.5, 52.5 + k * 14, 2, 2, "F")
        pdf.multi_cell(50, 4, item)

pdf.page_num("13 / 14")

# ── 14. CTA / CONTACTO ────────────────────────────────────────────────────────
pdf.add_page()
pdf.dark_bg()
pdf.set_fill_color(*G)
pdf.rect(0, 0, 6, 297, "F")
pdf.rect(204, 0, 6, 297, "F")

# big CTA
pdf.set_text_color(*W)
pdf.set_font("Helvetica", "B", 38)
pdf.set_xy(20, 50)
pdf.cell(0, 16, s("Listo para eliminar"))
pdf.set_xy(20, 66)
pdf.cell(0, 16, "tu merma para siempre?")

pdf.set_text_color(*G)
pdf.set_font("Helvetica", "B", 14)
pdf.set_xy(20, 92)
pdf.cell(0, 8, s("Solicita una demo gratuita de 30 minutos."))

# contact boxes
contacts = [
    (s("Telegram"),  "@ChuwiMermaOpsBot",     "Habla con Chuwi ahora"),
    (s("Email"),     "alvaroferrermarg@gmail.com", "Respuesta < 24h"),
    (s("Backend"),   "localhost:8001/docs",    "Swagger API en vivo"),
]
for i, (label, val, sub) in enumerate(contacts):
    x = 20 + i * 60
    pdf.set_fill_color(15, 35, 25)
    pdf.rect(x, 110, 55, 40, "F")
    pdf.set_fill_color(*G)
    pdf.rect(x, 110, 55, 3, "F")
    pdf.set_text_color(*G)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(x + 3, 116)
    pdf.cell(49, 5, label)
    pdf.set_text_color(*W)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_xy(x + 3, 123)
    pdf.cell(49, 5, s(val))
    pdf.set_text_color(130, 180, 150)
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_xy(x + 3, 130)
    pdf.cell(49, 5, s(sub))

# what they get in demo
pdf.set_fill_color(12, 28, 20)
pdf.rect(20, 162, 170, 60, "F")
pdf.set_text_color(*G)
pdf.set_font("Helvetica", "B", 10)
pdf.set_xy(25, 167)
pdf.cell(0, 6, s("En la demo de 30 min veras:"))
demo_items = [
    s("Chuwi respondiendo preguntas reales en Telegram"),
    s("Kuine analizando productos y generando acciones"),
    s("La app Flutter cargando datos de Supabase en directo"),
    s("Brief diario generado con IA en < 30 segundos"),
    s("Vision agent analizando una foto de producto"),
]
pdf.set_text_color(180, 225, 200)
pdf.set_font("Helvetica", "", 8.5)
for k, item in enumerate(demo_items):
    pdf.set_xy(28, 177 + k * 9)
    pdf.set_fill_color(*G)
    pdf.ellipse(26, 179.5 + k * 9, 2, 2, "F")
    pdf.cell(0, 5, item)

# bottom
pdf.set_text_color(60, 100, 80)
pdf.set_font("Helvetica", "B", 9)
pdf.set_xy(20, 250)
pdf.cell(170, 6, "MermaOps  |  TFM 2026  |  Alvaro Ferrer  |  Sistema en produccion", align="C")
pdf.set_text_color(40, 70, 55)
pdf.set_font("Helvetica", "", 7)
pdf.set_xy(20, 258)
pdf.cell(170, 5, s("Documento confidencial  -  solo para evaluadores y potenciales inversores"), align="C")

pdf.page_num("14 / 14")

pdf.output(str(OUT))
print(f"OK: {OUT}  ({OUT.stat().st_size // 1024} KB)")
