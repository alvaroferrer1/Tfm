"""
gen_pitch_pdf.py — Executive pitch PDF for MermaOps TFM
Output: docs/pdf/MermaOps_Pitch.pdf
Style: Apple/YC — minimal, huge typography, one message per page
"""
import sys
import os

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(BASE_DIR, "docs", "pdf", "MermaOps_Pitch.pdf")
AGENTS_IMG  = os.path.join(BASE_DIR, "Agentes MermaOps.png")
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

# ---------------------------------------------------------------------------
# ReportLab
# ---------------------------------------------------------------------------
from reportlab.lib.pagesizes import A4
from reportlab.lib.units     import mm, cm
from reportlab.lib            import colors
from reportlab.lib.colors     import HexColor, Color, white, black
from reportlab.platypus       import (SimpleDocTemplate, Spacer, Paragraph,
                                      Table, TableStyle, Image as RLImage,
                                      PageBreak, HRFlowable, KeepTogether)
from reportlab.lib.styles     import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums      import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen         import canvas
from reportlab.platypus.flowables import Flowable

PW, PH = A4  # 595 x 842 pts

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
C_BLACK  = HexColor("#000000")
C_NAVY   = HexColor("#0F172A")
C_WHITE  = HexColor("#FFFFFF")
C_GREEN  = HexColor("#10B981")
C_GRAY   = HexColor("#6B7280")
C_LGRAY  = HexColor("#D1D5DB")
C_DGRAY  = HexColor("#374151")
C_RED    = HexColor("#EF4444")
C_GOLD   = HexColor("#EAB308")
C_BLUE   = HexColor("#3B82F6")

# ---------------------------------------------------------------------------
# Custom canvas callback for background color
# ---------------------------------------------------------------------------
class DarkPage(Flowable):
    """Full-page dark background — used as first element on dark pages."""
    def __init__(self, color=C_NAVY):
        super().__init__()
        self.color = color
        self.width  = PW
        self.height = 0  # zero height — draws behind

    def draw(self):
        pass  # handled via onPage


def build_styles():
    base = getSampleStyleSheet()

    styles = {}

    def s(name, **kw):
        styles[name] = ParagraphStyle(name, **kw)

    # Cover
    s("cover_title",    fontSize=72, fontName="Helvetica-Bold",
      textColor=C_WHITE, alignment=TA_CENTER, spaceAfter=8)
    s("cover_sub",      fontSize=24, fontName="Helvetica",
      textColor=C_GREEN, alignment=TA_CENTER, spaceAfter=4)
    s("cover_sub2",     fontSize=20, fontName="Helvetica",
      textColor=C_GRAY,  alignment=TA_CENTER, spaceAfter=4)
    s("cover_author",   fontSize=14, fontName="Helvetica",
      textColor=C_GRAY,  alignment=TA_CENTER)

    # Section title (dark bg)
    s("section_title_dark", fontSize=42, fontName="Helvetica-Bold",
      textColor=C_WHITE, alignment=TA_CENTER, spaceAfter=12)
    # Section title (light bg)
    s("section_title",  fontSize=36, fontName="Helvetica-Bold",
      textColor=C_NAVY,  alignment=TA_CENTER, spaceAfter=12)

    # Huge number (dark)
    s("huge_num_dark",  fontSize=140, fontName="Helvetica-Bold",
      textColor=C_WHITE, alignment=TA_CENTER, leading=150)
    s("huge_num_green", fontSize=140, fontName="Helvetica-Bold",
      textColor=C_GREEN, alignment=TA_CENTER, leading=150)
    s("huge_num_navy",  fontSize=120, fontName="Helvetica-Bold",
      textColor=C_NAVY,  alignment=TA_CENTER, leading=130)

    # Body
    s("body_dark",  fontSize=22, fontName="Helvetica",
      textColor=C_LGRAY, alignment=TA_CENTER, spaceAfter=8, leading=30)
    s("body_light", fontSize=22, fontName="Helvetica",
      textColor=C_DGRAY, alignment=TA_CENTER, spaceAfter=8, leading=30)
    s("body_green", fontSize=22, fontName="Helvetica",
      textColor=C_GREEN, alignment=TA_CENTER, spaceAfter=8, leading=30)
    s("body_gray",  fontSize=18, fontName="Helvetica",
      textColor=C_GRAY,  alignment=TA_CENTER, spaceAfter=6, leading=24)
    s("body_red",   fontSize=22, fontName="Helvetica-Bold",
      textColor=C_RED,   alignment=TA_CENTER, spaceAfter=8, leading=28)
    s("footnote",   fontSize=10, fontName="Helvetica",
      textColor=C_GRAY,  alignment=TA_CENTER)
    s("caption",    fontSize=14, fontName="Helvetica",
      textColor=C_GRAY,  alignment=TA_CENTER)

    # Table cell styles
    s("cell_head",  fontSize=13, fontName="Helvetica-Bold",
      textColor=C_WHITE,  alignment=TA_CENTER)
    s("cell_body",  fontSize=12, fontName="Helvetica",
      textColor=C_DGRAY,  alignment=TA_LEFT)

    return styles


# ---------------------------------------------------------------------------
# Page template helper — background via onPageBegin
# ---------------------------------------------------------------------------
class PageBackground:
    """Canvas-level background painter injected via DocTemplate."""

    def __init__(self, dark_pages: set):
        self.dark_pages = dark_pages
        self._page_num  = [0]

    def on_page(self, canvas_obj, doc):
        self._page_num[0] += 1
        pn = self._page_num[0]
        if pn in self.dark_pages:
            canvas_obj.saveState()
            canvas_obj.setFillColor(C_NAVY)
            canvas_obj.rect(0, 0, PW, PH, fill=1, stroke=0)
            canvas_obj.restoreState()
        else:
            canvas_obj.saveState()
            canvas_obj.setFillColor(C_WHITE)
            canvas_obj.rect(0, 0, PW, PH, fill=1, stroke=0)
            canvas_obj.restoreState()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sp(n): return Spacer(1, n * mm)

def hline(color=C_GREEN, width=80*mm, thickness=2):
    return HRFlowable(width=width, thickness=thickness, color=color,
                      spaceAfter=4*mm, spaceBefore=4*mm)

def pill(text, bg=C_GREEN, fg=C_WHITE, st=None):
    """Return a 1-cell table styled as a pill/badge."""
    if st is None:
        st = ParagraphStyle("pill_inner", fontSize=13, fontName="Helvetica-Bold",
                            textColor=fg, alignment=TA_CENTER)
    t = Table([[Paragraph(text, st)]], colWidths=[100*mm], rowHeights=[10*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("ROUNDEDCORNERS", [5]),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
    ]))
    return t


def checkmark_table(items, fg=C_GREEN, st=None):
    """List with green checkmarks."""
    if st is None:
        st = ParagraphStyle("chk", fontSize=15, fontName="Helvetica",
                            textColor=C_DGRAY)
    data = [[Paragraph(f"<font color='#10B981'>&#10003;</font>  {item}", st)]
            for item in items]
    t = Table(data, colWidths=[160*mm])
    t.setStyle(TableStyle([
        ("ALIGN",       (0,0), (-1,-1), "LEFT"),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("TOPPADDING",  (0,0), (-1,-1), 6),
    ]))
    return t


# ---------------------------------------------------------------------------
# Page builders — return list of flowables
# ---------------------------------------------------------------------------
def page_cover(styles):
    return [
        sp(55),
        Paragraph("MermaOps", styles["cover_title"]),
        hline(C_GREEN, 80*mm),
        sp(4),
        Paragraph("Sistema Multi-Agente de IA", styles["cover_sub"]),
        Paragraph("para Reduccion de Merma Alimentaria", styles["cover_sub2"]),
        sp(50),
        Paragraph("Alvaro Ferrer Muro  |  2026", styles["cover_author"]),
        PageBreak(),
    ]


def page_problem(styles):
    body_dark = ParagraphStyle("bd2", fontSize=24, fontName="Helvetica",
                               textColor=C_GRAY, alignment=TA_CENTER, leading=32)
    body_bold = ParagraphStyle("bb2", fontSize=28, fontName="Helvetica-Bold",
                               textColor=C_NAVY, alignment=TA_CENTER, leading=36)
    fn = ParagraphStyle("fn2", fontSize=10, fontName="Helvetica",
                        textColor=C_GRAY, alignment=TA_CENTER)
    return [
        sp(30),
        Paragraph("2-5%", styles["huge_num_navy"]),
        hline(C_GREEN, 60*mm),
        sp(2),
        Paragraph("de los ingresos de tu supermercado", body_dark),
        Paragraph("se pierde en merma.", body_bold),
        sp(60),
        Paragraph("Fuente: FAO Espana 2024  |  10,4 kg/persona/anio",
                  styles["footnote"]),
        PageBreak(),
    ]


def page_existing_solutions(styles):
    head_st = ParagraphStyle("hs", fontSize=13, fontName="Helvetica-Bold",
                             textColor=C_WHITE, alignment=TA_CENTER)
    cell_st = ParagraphStyle("cs", fontSize=12, fontName="Helvetica",
                             textColor=C_DGRAY, alignment=TA_LEFT)

    data = [
        [Paragraph("Solucion",  head_st),
         Paragraph("Coste",     head_st),
         Paragraph("Barrera",   head_st)],
        [Paragraph("Winnow",    cell_st),
         Paragraph(">20.000 EUR", cell_st),
         Paragraph("Hardware especializado + formacion", cell_st)],
        [Paragraph("Orbisk",    cell_st),
         Paragraph(">15.000 EUR", cell_st),
         Paragraph("Instalacion 3 semanas + camaras", cell_st)],
        [Paragraph("Excel manual", cell_st),
         Paragraph("0 EUR",     cell_st),
         Paragraph("0% precision, 100% tiempo humano", cell_st)],
    ]

    col_w = [55*mm, 45*mm, 75*mm]
    t = Table(data, colWidths=col_w, rowHeights=[12*mm, 14*mm, 14*mm, 14*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0),  C_NAVY),
        ("BACKGROUND",  (0,1), (-1,-1), HexColor("#F8FAFC")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1),
         [HexColor("#F8FAFC"), HexColor("#F1F5F9")]),
        ("GRID",        (0,0), (-1,-1), 0.5, C_LGRAY),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING",(0,0), (-1,-1), 8),
    ]))

    highlight_st = ParagraphStyle("hl", fontSize=18, fontName="Helvetica-Bold",
                                  textColor=C_RED, alignment=TA_CENTER)
    return [
        sp(25),
        Paragraph("Las soluciones actuales fallan", styles["section_title"]),
        hline(C_GREEN, 80*mm),
        sp(6),
        t,
        sp(16),
        Paragraph("El 95% de supermercados no puede permitirselo.",
                  highlight_st),
        PageBreak(),
    ]


def page_mermaops(styles):
    sub_st = ParagraphStyle("ms", fontSize=40, fontName="Helvetica-Bold",
                            textColor=C_WHITE, alignment=TA_CENTER, leading=48)
    no_hw  = ParagraphStyle("nohw", fontSize=22, fontName="Helvetica",
                            textColor=C_GRAY, alignment=TA_CENTER, leading=32)
    return [
        sp(40),
        Paragraph("0,80 EUR", styles["huge_num_green"]),
        Paragraph("al mes.", sub_st),
        sp(6),
        hline(C_GREEN, 80*mm),
        sp(4),
        Paragraph("Sin hardware. Sin instalacion. Sin formacion.", no_hw),
        PageBreak(),
    ]


def page_agents_image(styles):
    cap_st = ParagraphStyle("cap", fontSize=14, fontName="Helvetica",
                            textColor=C_GRAY, alignment=TA_CENTER)
    elements = [
        sp(6),
        Paragraph("12 Agentes Especializados", styles["section_title"]),
        hline(C_GREEN, 80*mm),
        sp(4),
    ]
    if os.path.exists(AGENTS_IMG):
        max_w = PW - 40*mm
        max_h = 180*mm
        img_obj = RLImage(AGENTS_IMG, width=max_w, height=max_h,
                          kind="proportional")
        elements.append(img_obj)
    else:
        elements.append(Paragraph("[Agentes MermaOps.png — imagen no encontrada]",
                                  cap_st))
    elements += [
        sp(4),
        Paragraph(
            "Arquitectura multi-agente: Kuine (orquestador), Chuwi (Telegram), "
            "Evaluador (extended thinking), ForkMerge, Consenso, Validador, "
            "Predictor, Vision, Precio, Stock, Notificador, Reportero.",
            cap_st),
        PageBreak(),
    ]
    return elements


def page_100pct(styles):
    sub_st = ParagraphStyle("s100", fontSize=24, fontName="Helvetica",
                            textColor=C_LGRAY, alignment=TA_CENTER, leading=30)
    sm_st  = ParagraphStyle("sm100", fontSize=16, fontName="Helvetica",
                            textColor=C_GRAY, alignment=TA_CENTER, leading=22)
    return [
        sp(50),
        Paragraph("100%", styles["huge_num_dark"]),
        hline(C_GREEN, 60*mm),
        sp(2),
        Paragraph("de precision en decisiones.", sub_st),
        sp(4),
        Paragraph(
            "vs 16,7% baseline aleatorio  |  mejora de +83 puntos porcentuales.",
            sm_st),
        PageBreak(),
    ]


def page_architecture(styles):
    head_st = ParagraphStyle("ah", fontSize=13, fontName="Helvetica-Bold",
                             textColor=C_WHITE, alignment=TA_CENTER)
    cell_st = ParagraphStyle("ac", fontSize=12, fontName="Helvetica",
                             textColor=C_DGRAY, alignment=TA_LEFT)
    cell_why= ParagraphStyle("aw", fontSize=11, fontName="Helvetica",
                             textColor=C_GRAY, alignment=TA_LEFT)

    rows = [
        ("Claude API",    "Anthropic Sonnet/Opus/Haiku", "Right-sizing por tarea"),
        ("FastAPI",       "Python 3.14, puerto 8001",    "Async, tipado, rapido"),
        ("Supabase",      "PostgreSQL + Auth + Realtime", "Tiempo real sin backend extra"),
        ("Flutter",       "Android / iOS / Windows",     "Una sola base de codigo"),
        ("APScheduler",   "Cron en proceso",             "Briefs diarios autonomos"),
        ("Telegram Bot",  "@ChuwiMermaOpsBot",           "0 friccion de adopcion"),
    ]

    data = [
        [Paragraph("Capa", head_st),
         Paragraph("Tecnologia", head_st),
         Paragraph("Por que", head_st)],
    ] + [
        [Paragraph(a, cell_st), Paragraph(b, cell_st), Paragraph(c, cell_why)]
        for a, b, c in rows
    ]

    col_w = [45*mm, 65*mm, 70*mm]
    row_h = [12*mm] + [14*mm]*len(rows)
    t = Table(data, colWidths=col_w, rowHeights=row_h)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), C_NAVY),
        ("ROWBACKGROUNDS", (0,1), (-1,-1),
         [HexColor("#F8FAFC"), HexColor("#F1F5F9")]),
        ("GRID",       (0,0), (-1,-1), 0.5, C_LGRAY),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",(0,0), (-1,-1), 8),
    ]))

    return [
        sp(20),
        Paragraph("La arquitectura", styles["section_title"]),
        hline(C_GREEN, 80*mm),
        sp(6),
        t,
        PageBreak(),
    ]


def page_normativo(styles):
    body_st = ParagraphStyle("nb", fontSize=15, fontName="Helvetica",
                             textColor=C_DGRAY, alignment=TA_CENTER, leading=22)
    concl_st= ParagraphStyle("nc", fontSize=16, fontName="Helvetica",
                             textColor=C_DGRAY, alignment=TA_CENTER, leading=24,
                             spaceAfter=6)

    regs = [
        "CE 178/2002 — Trazabilidad alimentaria obligatoria",
        "Ley 7/2022 — Residuos y suelo contaminado (merma)",
        "Ley 49/2002 — Deduccion fiscal por donaciones alimentarias",
        "CSRD 2026 — Reporting ESG obligatorio para empresas medianas",
        "ISO 22000 — HACCP digital integrado",
    ]

    data = [[Paragraph(
        f"<font color='#10B981' size='16'><b>&#10003;</b></font>  {r}", body_st)]
        for r in regs]
    t = Table(data, colWidths=[160*mm], rowHeights=[16*mm]*len(regs))
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1),
         [HexColor("#F0FDF4"), HexColor("#F8FAFC")]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("GRID", (0,0), (-1,-1), 0.5, C_LGRAY),
    ]))

    return [
        sp(16),
        Paragraph("Cumplimiento normativo", styles["section_title"]),
        hline(C_GREEN, 80*mm),
        sp(6),
        t,
        sp(8),
        Paragraph(
            "MermaOps genera el reporting ESG obligatorio desde 2026 "
            "de forma automatica.",
            concl_st),
        PageBreak(),
    ]


def page_roi(styles):
    sub_st = ParagraphStyle("rs", fontSize=32, fontName="Helvetica-Bold",
                            textColor=C_WHITE, alignment=TA_CENTER, leading=40)
    det_st = ParagraphStyle("rd", fontSize=20, fontName="Helvetica",
                            textColor=C_GRAY, alignment=TA_CENTER, leading=28)
    return [
        sp(45),
        Paragraph("500:1", styles["huge_num_green"]),
        hline(C_GREEN, 60*mm),
        Paragraph("retorno estimado", sub_st),
        sp(6),
        Paragraph(
            "0,80 EUR/mes de coste  |  ~400 EUR/mes de merma evitada  |  "
            "30h de tiempo ahorrado.",
            det_st),
        PageBreak(),
    ]


def page_futuro(styles):
    card_title = ParagraphStyle("ct", fontSize=18, fontName="Helvetica-Bold",
                                textColor=C_NAVY, alignment=TA_CENTER)
    card_body  = ParagraphStyle("cb", fontSize=13, fontName="Helvetica",
                                textColor=C_GRAY, alignment=TA_CENTER, leading=18)

    cards = [
        ("Agente Comprador",
         "Optimiza pedidos a proveedores basandose en historial de merma y previsiones"),
        ("Multi-tienda",
         "Dashboard centralizado para cadenas, benchmarking entre tiendas"),
        ("Fine-tuning",
         "Modelo propio entrenado con datos reales del sistema"),
    ]

    col_w = 52*mm
    gap   = 6*mm

    row = [
        Table([[Paragraph(title, card_title)],
               [Paragraph(body, card_body)]],
              colWidths=[col_w],
              style=TableStyle([
                  ("BACKGROUND", (0,0), (-1,-1), HexColor("#F0FDF4")),
                  ("BOX",        (0,0), (-1,-1), 1.5, C_GREEN),
                  ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
                  ("TOPPADDING", (0,0), (-1,-1), 8),
                  ("BOTTOMPADDING",(0,0),(-1,-1), 8),
                  ("LEFTPADDING",(0,0), (-1,-1), 8),
                  ("RIGHTPADDING",(0,0), (-1,-1), 8),
              ]))
        for title, body in cards
    ]

    outer = Table([row],
                  colWidths=[col_w]*3,
                  style=TableStyle([
                      ("VALIGN",      (0,0), (-1,-1), "TOP"),
                      ("LEFTPADDING", (0,0), (-1,-1), gap),
                      ("RIGHTPADDING",(0,0), (-1,-1), gap),
                  ]))

    return [
        sp(20),
        Paragraph("Lineas futuras", styles["section_title"]),
        hline(C_GREEN, 80*mm),
        sp(8),
        outer,
        PageBreak(),
    ]


def page_contacto(styles):
    email_st = ParagraphStyle("em", fontSize=20, fontName="Helvetica",
                              textColor=C_LGRAY, alignment=TA_CENTER, leading=28)
    bot_st   = ParagraphStyle("bt", fontSize=22, fontName="Helvetica-Bold",
                              textColor=C_GREEN, alignment=TA_CENTER)
    return [
        sp(55),
        Paragraph("MermaOps", styles["section_title_dark"]),
        hline(C_GREEN, 60*mm),
        sp(6),
        Paragraph("alvaroferrermarg@gmail.com", email_st),
        sp(4),
        Paragraph("github.com/alvaroferrermarg/mermaops", email_st),
        sp(6),
        Paragraph("@ChuwiMermaOpsBot", bot_st),
        PageBreak(),
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Building MermaOps Pitch PDF...")

    styles = build_styles()

    # Dark pages: cover(1), mermaops(4), 100%(6), roi(9), contacto(11)
    dark_pages = {1, 4, 6, 9, 11}
    bg = PageBackground(dark_pages)

    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=A4,
        leftMargin=20*mm,
        rightMargin=20*mm,
        topMargin=15*mm,
        bottomMargin=15*mm,
    )

    story = []
    story += page_cover(styles)
    story += page_problem(styles)
    story += page_existing_solutions(styles)
    story += page_mermaops(styles)
    story += page_agents_image(styles)
    story += page_100pct(styles)
    story += page_architecture(styles)
    story += page_normativo(styles)
    story += page_roi(styles)
    story += page_futuro(styles)
    story += page_contacto(styles)

    doc.build(story,
              onFirstPage=bg.on_page,
              onLaterPages=bg.on_page)

    print(f"Done: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
