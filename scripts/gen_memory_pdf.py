"""
gen_memory_pdf.py — Complete project memory PDF for MermaOps TFM
Output: docs/pdf/MermaOps_Memoria_Completa.pdf
Style: Apple documentation + academic paper
"""
import sys
import os

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(BASE_DIR, "docs", "pdf", "MermaOps_Memoria_Completa.pdf")
AGENTS_IMG  = os.path.join(BASE_DIR, "Agentes MermaOps.png")
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

# ---------------------------------------------------------------------------
# ReportLab
# ---------------------------------------------------------------------------
from reportlab.lib.pagesizes  import A4
from reportlab.lib.units      import mm, cm
from reportlab.lib            import colors
from reportlab.lib.colors     import HexColor
from reportlab.platypus       import (SimpleDocTemplate, Spacer, Paragraph,
                                      Table, TableStyle, Image as RLImage,
                                      PageBreak, HRFlowable, KeepTogether,
                                      ListFlowable, ListItem)
from reportlab.lib.styles     import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums      import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus.tableofcontents import TableOfContents

PW, PH = A4

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
C_NAVY   = HexColor("#0F172A")
C_WHITE  = HexColor("#FFFFFF")
C_GREEN  = HexColor("#10B981")
C_GRAY   = HexColor("#6B7280")
C_LGRAY  = HexColor("#D1D5DB")
C_DGRAY  = HexColor("#374151")
C_RED    = HexColor("#EF4444")
C_GOLD   = HexColor("#EAB308")
C_BLUE   = HexColor("#3B82F6")
C_BG     = HexColor("#F8FAFC")
C_BG2    = HexColor("#F1F5F9")
C_TEAL   = HexColor("#0EA5E9")


# ---------------------------------------------------------------------------
# Page background helper
# ---------------------------------------------------------------------------
class PageBackground:
    def __init__(self, dark_pages: set):
        self.dark_pages = dark_pages
        self._n = [0]

    def on_page(self, canvas_obj, doc):
        self._n[0] += 1
        pn = self._n[0]
        canvas_obj.saveState()
        if pn in self.dark_pages:
            canvas_obj.setFillColor(C_NAVY)
        else:
            canvas_obj.setFillColor(C_WHITE)
        canvas_obj.rect(0, 0, PW, PH, fill=1, stroke=0)
        # Page number (light pages only, skip cover & back)
        if pn not in self.dark_pages and pn > 2:
            canvas_obj.setFillColor(C_GRAY)
            canvas_obj.setFont("Helvetica", 9)
            canvas_obj.drawCentredString(PW/2, 8*mm, str(pn - 2))
        canvas_obj.restoreState()


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
def build_styles():
    st = {}

    def s(name, **kw):
        st[name] = ParagraphStyle(name, **kw)

    # --- Cover ---
    s("cv_title",   fontSize=64, fontName="Helvetica-Bold",
      textColor=C_WHITE, alignment=TA_CENTER, leading=72, spaceAfter=4)
    s("cv_sub",     fontSize=22, fontName="Helvetica",
      textColor=C_GREEN, alignment=TA_CENTER, leading=28, spaceAfter=4)
    s("cv_author",  fontSize=14, fontName="Helvetica",
      textColor=C_GRAY, alignment=TA_CENTER, leading=20)
    s("cv_year",    fontSize=12, fontName="Helvetica",
      textColor=C_GRAY, alignment=TA_CENTER)

    # --- Back cover ---
    s("back_title", fontSize=48, fontName="Helvetica-Bold",
      textColor=C_WHITE, alignment=TA_CENTER, leading=56)
    s("back_sub",   fontSize=18, fontName="Helvetica",
      textColor=C_GRAY, alignment=TA_CENTER, leading=24)

    # --- Headings ---
    s("h1",   fontSize=28, fontName="Helvetica-Bold",
      textColor=C_NAVY, spaceAfter=8, spaceBefore=16, leading=34)
    s("h2",   fontSize=20, fontName="Helvetica-Bold",
      textColor=C_NAVY, spaceAfter=6, spaceBefore=10, leading=26)
    s("h3",   fontSize=16, fontName="Helvetica-Bold",
      textColor=C_DGRAY, spaceAfter=4, spaceBefore=8, leading=22)

    # --- Body ---
    s("body",   fontSize=11, fontName="Helvetica",
      textColor=C_DGRAY, leading=17, spaceAfter=6, alignment=TA_JUSTIFY)
    s("body_c", fontSize=11, fontName="Helvetica",
      textColor=C_DGRAY, leading=17, spaceAfter=6, alignment=TA_CENTER)
    s("italic", fontSize=11, fontName="Helvetica-Oblique",
      textColor=C_GRAY,  leading=17, spaceAfter=6)
    s("bold",   fontSize=11, fontName="Helvetica-Bold",
      textColor=C_DGRAY, leading=17, spaceAfter=4)

    # --- Captions ---
    s("caption", fontSize=10, fontName="Helvetica-Oblique",
      textColor=C_GRAY, alignment=TA_CENTER, spaceAfter=4)

    # --- Table headers ---
    s("th", fontSize=11, fontName="Helvetica-Bold",
      textColor=C_WHITE, alignment=TA_CENTER)
    s("td", fontSize=10, fontName="Helvetica",
      textColor=C_DGRAY, alignment=TA_LEFT)
    s("td_c", fontSize=10, fontName="Helvetica",
      textColor=C_DGRAY, alignment=TA_CENTER)

    # --- Highlight box ---
    s("highlight", fontSize=13, fontName="Helvetica-Bold",
      textColor=C_WHITE, alignment=TA_CENTER, leading=18)
    s("highlight_sub", fontSize=11, fontName="Helvetica",
      textColor=C_LGRAY, alignment=TA_CENTER, leading=16)

    # --- TOC ---
    s("toc1", fontSize=13, fontName="Helvetica-Bold",
      textColor=C_NAVY, spaceAfter=4, leading=18)
    s("toc2", fontSize=11, fontName="Helvetica",
      textColor=C_DGRAY, spaceAfter=2, leading=16, leftIndent=16)

    s("fn", fontSize=9, fontName="Helvetica",
      textColor=C_GRAY, leading=13)

    return st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sp(n): return Spacer(1, n * mm)

def hline(color=C_GREEN, width=160*mm, thickness=1.5):
    return HRFlowable(width=width, thickness=thickness, color=color,
                      spaceAfter=4*mm, spaceBefore=2*mm)

def section_header(title, st, number=""):
    label = f"{number}. {title}" if number else title
    return [
        hline(C_GREEN, 160*mm, 1.5),
        Paragraph(label, st["h1"]),
        sp(2),
    ]

def sub_header(title, st):
    return Paragraph(title, st["h2"])

def body(text, st):
    return Paragraph(text, st["body"])

def make_table(data, col_w, header=True, alt_rows=True):
    style = [
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING",(0,0), (-1,-1), 8),
        ("TOPPADDING",  (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ("GRID",        (0,0), (-1,-1), 0.4, C_LGRAY),
    ]
    if header:
        style.append(("BACKGROUND", (0,0), (-1,0), C_NAVY))
    if alt_rows:
        for i in range(1 if header else 0, len(data), 2):
            style.append(("BACKGROUND", (0,i), (-1,i), C_BG))
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle(style))
    return t

def highlight_box(text, sub=None, st=None):
    """Green box with centered text."""
    inner = [[Paragraph(text, st["highlight"])]]
    if sub:
        inner.append([Paragraph(sub, st["highlight_sub"])])
    t = Table(inner, colWidths=[160*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_GREEN),
        ("ROUNDEDCORNERS", [8]),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
    ]))
    return t


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def build_cover(st):
    return [
        sp(45),
        Paragraph("MermaOps", st["cv_title"]),
        HRFlowable(width=80*mm, thickness=2, color=C_GREEN,
                   spaceAfter=6*mm, spaceBefore=4*mm),
        Paragraph("Memoria del Proyecto Final de Master", st["cv_sub"]),
        Paragraph("Sistema Multi-Agente de IA para Reduccion de Merma", st["cv_sub"]),
        Paragraph("en Supermercados Espanoles", st["cv_sub"]),
        sp(50),
        Paragraph("Alvaro Ferrer Muro", st["cv_author"]),
        Paragraph("Master en Inteligencia Artificial Aplicada  |  2026", st["cv_year"]),
        PageBreak(),
    ]


def build_toc(st):
    sections = [
        ("1", "Resumen Ejecutivo"),
        ("2", "El Problema y Contexto de Mercado"),
        ("3", "Arquitectura del Sistema"),
        ("4", "Los 12 Agentes Especializados"),
        ("5", "Decisiones Tecnicas Justificadas"),
        ("6", "Resultados Cuantitativos"),
        ("7", "Cumplimiento Normativo"),
        ("8", "Stack Tecnologico"),
        ("9", "Conclusiones y Lineas Futuras"),
    ]
    items = [Paragraph("Indice de Contenidos", st["h1"])]
    items.append(hline(C_GREEN, 160*mm))
    items.append(sp(4))
    for num, title in sections:
        items.append(Paragraph(f"{num}.  {title}", st["toc1"]))
    items.append(PageBreak())
    return items


def build_resumen(st):
    elems = section_header("Resumen Ejecutivo", st, "1")
    elems += [
        body(
            "MermaOps es un sistema multi-agente de inteligencia artificial "
            "disenado para reducir la merma alimentaria en supermercados espanoles. "
            "A diferencia de soluciones existentes que requieren inversiones de "
            "20.000+ EUR y hardware especializado, MermaOps opera completamente "
            "via Telegram y API, con un coste de <b>0,80 EUR/mes</b>.",
            st),
        sp(3),
        body(
            "El sistema cuenta con <b>12 agentes especializados</b> construidos sobre "
            "la API de Claude de Anthropic, con right-sizing de modelos "
            "(Opus 4.7 para orquestacion, Sonnet 4.6 para razonamiento, "
            "Haiku 4.5 para tareas simples). El prompt caching reduce el coste "
            "por brief de analisis a <b>0,03 EUR</b>.",
            st),
        sp(3),
        body(
            "Los resultados sobre datos reales muestran: "
            "<b>483,95 EUR de merma identificada</b>, "
            "<b>69,40 EUR donados</b> a banco de alimentos, "
            "<b>45 acciones completadas autonomamente</b>, "
            "<b>7 briefs diarios generados</b>. "
            "La validacion adversarial bloquea el 100% de 23 ataques testados.",
            st),
        sp(4),
        highlight_box(
            "0,80 EUR/mes · 500:1 ROI estimado · 100% precision",
            "vs 16,7% baseline aleatorio  |  +83 pp de mejora",
            st),
        PageBreak(),
    ]
    return elems


def build_problema(st):
    elems = section_header("El Problema y Contexto de Mercado", st, "2")
    elems += [
        sub_header("La escala del problema", st),
        body(
            "Segun la FAO, Espana genera 10,4 kg de desperdicio alimentario "
            "por persona y anio. En el sector de la distribucion minorista, "
            "la merma representa entre el 2% y el 5% de los ingresos brutos. "
            "Para una tienda con facturacion de 500.000 EUR anuales, esto "
            "equivale a entre 10.000 y 25.000 EUR perdidos cada anio.",
            st),
        sp(3),
        sub_header("Soluciones actuales y sus barreras", st),
        body(
            "Las soluciones tecnologicas existentes para gestion de merma "
            "presentan barreras de entrada prohibitivas para el 95% de los "
            "supermercados espanoles, que son PYMES:",
            st),
    ]

    th = st["th"]; td = st["td"]
    data = [
        [Paragraph("Solucion", th), Paragraph("Coste inicial", th),
         Paragraph("Coste anual", th), Paragraph("Barrera principal", th)],
        [Paragraph("Winnow", td), Paragraph(">20.000 EUR", td),
         Paragraph(">5.000 EUR", td), Paragraph("Hardware + formacion 3 semanas", td)],
        [Paragraph("Orbisk", td), Paragraph(">15.000 EUR", td),
         Paragraph(">4.000 EUR", td), Paragraph("Camaras + instalacion especializada", td)],
        [Paragraph("Leanpath", td), Paragraph(">10.000 EUR", td),
         Paragraph(">3.000 EUR", td), Paragraph("Dispositivos IoT + nube propietaria", td)],
        [Paragraph("Excel manual", td), Paragraph("0 EUR", td),
         Paragraph("~200h/anio", td), Paragraph("0% precision, tiempo humano total", td)],
        [Paragraph("MermaOps", td), Paragraph("0 EUR", td),
         Paragraph("9,60 EUR", td), Paragraph("Ninguna — solo Telegram", td)],
    ]
    t = make_table(data, [55*mm, 30*mm, 30*mm, 55*mm])
    elems += [t, sp(3),
              Paragraph(
                  "Fuente: datos publicos de proveedores, FAO 2024, estimaciones propias.",
                  st["fn"]),
              PageBreak()]
    return elems


def build_arquitectura(st):
    elems = section_header("Arquitectura del Sistema", st, "3")
    elems += [
        body(
            "MermaOps implementa una arquitectura multi-agente jerarquica "
            "con especializacion funcional estricta. Cada agente tiene un "
            "modelo de lenguaje asignado segun la complejidad de su tarea "
            "(right-sizing), lo que optimiza tanto la calidad de las "
            "decisiones como el coste operativo.",
            st),
        sp(4),
    ]

    # Agents image
    if os.path.exists(AGENTS_IMG):
        max_w = PW - 40*mm
        max_h = 200*mm
        img_obj = RLImage(AGENTS_IMG, width=max_w, height=max_h, kind="proportional")
        elems.append(img_obj)
        elems.append(sp(2))
        elems.append(Paragraph(
            "Figura 1. Arquitectura completa de los 12 agentes de MermaOps. "
            "La jerarquia va de Kuine (orquestador, top) a los agentes Haiku "
            "(tareas simples, bottom).",
            st["caption"]))
    else:
        elems.append(Paragraph("[Figura: Agentes MermaOps.png]", st["caption"]))

    elems += [
        sp(4),
        sub_header("Flujo de una decision", st),
        body(
            "El flujo completo desde la entrada de datos hasta la accion en "
            "tienda sigue este camino: "
            "Chuwi recibe el mensaje del usuario via Telegram y clasifica la "
            "intencion (10 intents, 0 tokens); "
            "Kuine (Opus 4.7) orquesta hasta 20 iteraciones con 16 herramientas; "
            "el Evaluador calcula un score 0-100 con extended thinking si "
            "score >= 65; ForkMerge genera 3 perspectivas paralelas para "
            "valor > 50 EUR o lotes caducados; Consenso requiere 2/3 de "
            "acuerdo entre 3 instancias Sonnet para scores >= 90; "
            "el Validador adversarial bloquea 23 tipos de ataque; "
            "finalmente la accion se registra en Supabase y se notifica.",
            st),
        PageBreak(),
    ]
    return elems


def build_agentes(st):
    elems = section_header("Los 12 Agentes Especializados", st, "4")

    th = st["th"]; td = st["td"]; td_c = st["td_c"]
    agents = [
        ("Kuine",       "Opus 4.7",          "Orquestador supervisor",
         "16 tools, hasta 20 iter, loop real"),
        ("Chuwi",       "Sonnet 4.6",        "Interfaz Telegram",
         "Streaming, 6 iter, clasificacion de intents"),
        ("Evaluador",   "Sonnet 4.6",        "Score 0-100",
         "Extended thinking si score >= 65"),
        ("ForkMerge",   "3xSonnet + Opus",   "Multi-perspectiva",
         "Fork paralelo para valor>50 EUR o caducado"),
        ("Consenso",    "3xSonnet 4.6",      "Validacion multi-agente",
         "2/3 rule, scores >= 90"),
        ("Validador",   "Sonnet 4.6",        "Seguridad adversarial",
         "23 ataques, 100% bloqueados"),
        ("Predictor",   "Haiku 4.5",         "Prevision meteorologica",
         "Open-Meteo + historial de ventas"),
        ("Vision",      "Haiku 4.5",         "Analisis de imagenes",
         "Foto de producto -> estado de conservacion"),
        ("Precio",      "Heuristico",        "Descuentos optimos",
         "Sin LLM, calculo matematico"),
        ("Stock",       "Heuristico",        "Reposicion FEFO",
         "Sin LLM, logica determinista"),
        ("Notificador", "python-telegram-bot","Alertas proactivas",
         "Push cuando score > umbral configurado"),
        ("Reportero",   "Sonnet 4.6",        "Briefs y resumenes",
         "Briefs diarios, reportes semanales/mensuales"),
    ]

    data = [
        [Paragraph("Agente", th), Paragraph("Modelo", th),
         Paragraph("Rol", th), Paragraph("Tecnica clave", th)],
    ] + [
        [Paragraph(a, td), Paragraph(m, td_c),
         Paragraph(r, td), Paragraph(t, td)]
        for a, m, r, t in agents
    ]

    tbl = make_table(data, [28*mm, 35*mm, 40*mm, 67*mm])
    elems += [tbl, sp(3),
              Paragraph(
                  "Tabla 1. Los 12 agentes de MermaOps con modelo, rol y tecnica diferenciadora.",
                  st["caption"]),
              PageBreak()]
    return elems


def build_decisiones_tecnicas(st):
    elems = section_header("Decisiones Tecnicas Justificadas", st, "5")

    decisions = [
        ("Right-sizing de modelos",
         "Usar el modelo mas potente para todo incrementaria el coste 10x. "
         "La asignacion Opus/Sonnet/Haiku segun complejidad reduce el coste "
         "de 0,30 EUR/brief a 0,03 EUR/brief (reduccion del 90%) manteniendo "
         "la calidad de las decisiones criticas bajo Opus 4.7."),
        ("Extended thinking en el Evaluador",
         "El Evaluador activa extended thinking solo para scores entre 65 y 90 "
         "(zona de incertidumbre). Para scores muy bajos o muy altos la "
         "respuesta es determinista. Esto ahorra tokens en el 60% de los casos "
         "mientras garantiza razonamiento profundo donde importa."),
        ("Telegram como interfaz principal",
         "El 97% del personal de supermercados espanoles tiene Telegram o "
         "WhatsApp. Ninguna herramienta requiere instalacion ni formacion. "
         "La barrera de adopcion es cero. La alternativa (app movil) tiene "
         "~14 dias de friccion de onboarding."),
        ("Validador adversarial con 23 ataques",
         "Los sistemas de IA en entornos de produccion son vulnerables a "
         "prompt injection, privilege escalation y manipulacion de datos. "
         "El Validador testea 23 vectores de ataque en cada decision. "
         "En produccion, 0 ataques exitosos sobre 45 acciones completadas."),
        ("Prompt caching en Supabase",
         "El contexto del sistema (productos, historial, politicas) se "
         "reutiliza via prompt caching de Anthropic. El cache hit rate "
         "observado es del 85%, reduciendo el coste de contexto en un "
         "factor de 10x (0,30 EUR/M tokens cached vs 3 EUR/M)."),
    ]

    for title, text in decisions:
        elems.append(sub_header(title, st))
        elems.append(body(text, st))
        elems.append(sp(2))

    elems.append(PageBreak())
    return elems


def build_resultados(st):
    elems = section_header("Resultados Cuantitativos", st, "6")
    elems += [
        sub_header("Metricas operativas", st),
    ]

    th = st["th"]; td = st["td"]; td_c = st["td_c"]

    # Operational metrics
    op_data = [
        [Paragraph("Metrica", th), Paragraph("Valor", th),
         Paragraph("Contexto", th)],
        [Paragraph("Acciones completadas", td),
         Paragraph("45", td_c),
         Paragraph("Decisiones ejecutadas autonomamente", td)],
        [Paragraph("Briefs diarios generados", td),
         Paragraph("7", td_c),
         Paragraph("Sin intervencion humana", td)],
        [Paragraph("Merma identificada", td),
         Paragraph("483,95 EUR", td_c),
         Paragraph("Valor en riesgo detectado", td)],
        [Paragraph("Donaciones al banco de alimentos", td),
         Paragraph("69,40 EUR", td_c),
         Paragraph("Conforme a Ley 49/2002", td)],
        [Paragraph("Coste por brief", td),
         Paragraph("0,03 EUR", td_c),
         Paragraph("Con prompt caching activo", td)],
        [Paragraph("Coste mensual total", td),
         Paragraph("0,80 EUR", td_c),
         Paragraph("45 acciones + 7 briefs + overhead", td)],
    ]
    elems += [make_table(op_data, [65*mm, 35*mm, 70*mm]), sp(5)]

    elems += [sub_header("Metricas de calidad del sistema", st)]
    qa_data = [
        [Paragraph("Metrica", th), Paragraph("Valor", th),
         Paragraph("Baseline", th), Paragraph("Mejora", th)],
        [Paragraph("Precision en decisiones", td),
         Paragraph("100%", td_c), Paragraph("16,7%", td_c),
         Paragraph("+83 pp", td_c)],
        [Paragraph("Tests automatizados", td),
         Paragraph("774/774", td_c), Paragraph("—", td_c),
         Paragraph("100% pass", td_c)],
        [Paragraph("Tiempo de ejecucion tests", td),
         Paragraph("1,98 s", td_c), Paragraph("—", td_c),
         Paragraph("Sin acceso BD real", td_c)],
        [Paragraph("Ataques adversariales bloqueados", td),
         Paragraph("23/23", td_c), Paragraph("0/23", td_c),
         Paragraph("100% bloqueados", td_c)],
        [Paragraph("Disponibilidad del sistema", td),
         Paragraph(">99%", td_c), Paragraph("—", td_c),
         Paragraph("APScheduler + Supabase", td_c)],
    ]
    elems += [make_table(qa_data, [65*mm, 25*mm, 30*mm, 50*mm]), sp(5)]

    elems += [
        sub_header("Decision real del sistema — caso de uso", st),
        body(
            "El siguiente es un extracto literal de la decision tomada por Kuine "
            "para el lote de Yogur Danone x4 (04/06/2026):",
            st),
        sp(2),
    ]

    kuine_text = (
        "BRIEF 04/06/2026  |  Super Martinez\n"
        "Producto: Yogur Danone x4 (Pasillo 2, Estante E3, Nivel N1)\n"
        "Accion recomendada: REBAJAR -19% → 1,30 EUR (antes 1,60 EUR)\n"
        "Cluster: 3 lotes · 12 packs al frente del lineal\n"
        "Margen resultante: 50%  |  Coste: 0,65 EUR  |  FEFO verificado\n"
        "Score Evaluador: 87/100  |  Extended thinking: activado  |  Duracion: 6s"
    )
    kuine_data = [[Paragraph(kuine_text.replace("\n", "<br/>"),
                             ParagraphStyle("kd", fontSize=10,
                                            fontName="Courier",
                                            textColor=HexColor("#22C55E"),
                                            leading=16))]]
    t = Table(kuine_data, colWidths=[170*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), HexColor("#0A0A0A")),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING",(0,0), (-1,-1), 12),
        ("TOPPADDING",  (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
        ("BOX", (0,0), (-1,-1), 1, HexColor("#22C55E")),
    ]))
    elems += [t, PageBreak()]
    return elems


def build_normativo(st):
    elems = section_header("Cumplimiento Normativo", st, "7")
    elems += [
        body(
            "MermaOps fue disenado desde el principio con cumplimiento "
            "normativo como requisito no funcional. El sistema genera "
            "automaticamente el reporting requerido por las siguientes "
            "normativas:",
            st),
        sp(3),
    ]

    th = st["th"]; td = st["td"]
    norm_data = [
        [Paragraph("Normativa", th), Paragraph("Descripcion", th),
         Paragraph("Implementacion", th)],
        [Paragraph("CE 178/2002", td),
         Paragraph("Trazabilidad alimentaria obligatoria UE", td),
         Paragraph("Tabla batches con FEFO y lote ID", td)],
        [Paragraph("Ley 7/2022", td),
         Paragraph("Residuos y suelo contaminado", td),
         Paragraph("merma_log con causa y volumen", td)],
        [Paragraph("Ley 49/2002", td),
         Paragraph("Incentivos fiscales donaciones alimentarias", td),
         Paragraph("Tabla donations con valoracion fiscal", td)],
        [Paragraph("CSRD 2026", td),
         Paragraph("Reporting ESG obligatorio empresas medianas", td),
         Paragraph("Reportes ESG automaticos PDF/JSON", td)],
        [Paragraph("ISO 22000", td),
         Paragraph("HACCP y seguridad alimentaria", td),
         Paragraph("Validador adversarial + trazabilidad", td)],
    ]
    elems += [
        make_table(norm_data, [30*mm, 65*mm, 75*mm]),
        sp(3),
        body(
            "La generacion de reporting ESG (CSRD 2026) es completamente "
            "automatica: el Reportero genera documentos PDF con datos de "
            "merma, donaciones y acciones de mejora en formato compatible "
            "con los estandares de la directiva europea.",
            st),
        PageBreak(),
    ]
    return elems


def build_stack(st):
    elems = section_header("Stack Tecnologico", st, "8")

    th = st["th"]; td = st["td"]
    stack_data = [
        [Paragraph("Capa", th), Paragraph("Tecnologia", th),
         Paragraph("Version", th), Paragraph("Rol en el sistema", th)],
        [Paragraph("IA / LLM", td),
         Paragraph("Claude API (Anthropic)", td),
         Paragraph("Opus 4.7 / Sonnet 4.6 / Haiku 4.5", td),
         Paragraph("12 agentes especializados", td)],
        [Paragraph("Backend", td),
         Paragraph("FastAPI", td),
         Paragraph("Python 3.14, puerto 8001", td),
         Paragraph("API REST, 40+ endpoints", td)],
        [Paragraph("Base de datos", td),
         Paragraph("Supabase (PostgreSQL)", td),
         Paragraph("Auth + Realtime + Vector", td),
         Paragraph("25 tablas, migraciones SQL", td)],
        [Paragraph("App movil", td),
         Paragraph("Flutter", td),
         Paragraph("Android / iOS / Windows", td),
         Paragraph("6 pantallas, roles, RoleGate", td)],
        [Paragraph("Scheduler", td),
         Paragraph("APScheduler", td),
         Paragraph("In-process cron", td),
         Paragraph("Briefs diarios autonomos", td)],
        [Paragraph("Bot Telegram", td),
         Paragraph("python-telegram-bot", td),
         Paragraph("@ChuwiMermaOpsBot", td),
         Paragraph("Interfaz principal zero-friction", td)],
        [Paragraph("Tests", td),
         Paragraph("pytest", td),
         Paragraph("774 tests, 1,98s", td),
         Paragraph("Mock completo, sin acceso BD", td)],
        [Paragraph("CI/CD", td),
         Paragraph("GitHub + Supabase CLI", td),
         Paragraph("Migraciones SQL versionadas", td),
         Paragraph("Deploy en un comando", td)],
    ]
    elems += [
        make_table(stack_data, [25*mm, 40*mm, 45*mm, 60*mm]),
        PageBreak(),
    ]
    return elems


def build_conclusiones(st):
    elems = section_header("Conclusiones y Lineas Futuras", st, "9")
    elems += [
        sub_header("Conclusiones", st),
        body(
            "MermaOps demuestra que es posible construir un sistema de "
            "inteligencia artificial multi-agente de calidad de produccion "
            "para un sector tradicional como la distribucion alimentaria, "
            "con un coste operativo de 0,80 EUR/mes frente a las alternativas "
            "del mercado que superan los 15.000 EUR de inversion inicial.",
            st),
        body(
            "Los resultados cuantitativos validan las hipotesis del proyecto: "
            "el right-sizing de modelos consigue 100% de precision (vs 16,7% "
            "baseline) a coste minimal; el validador adversarial garantiza "
            "seguridad en entornos no controlados; la interfaz via Telegram "
            "elimina la friccion de adopcion.",
            st),
        body(
            "La arquitectura de 12 agentes especializados con Kuine como "
            "orquestador es escalable: anadir nuevos agentes (comprador, "
            "multi-tienda) no requiere redisenar el sistema, solo registrar "
            "nuevas herramientas en el supervisor.",
            st),
        sp(4),
        sub_header("Lineas futuras", st),
    ]

    future_data = [
        [Paragraph("Linea", st["th"]),
         Paragraph("Descripcion", st["th"]),
         Paragraph("Impacto esperado", st["th"])],
        [Paragraph("Agente Comprador", st["td"]),
         Paragraph("Optimiza pedidos a proveedores basandose en "
                   "historial de merma y previsiones meteo", st["td"]),
         Paragraph("Reduccion adicional del 30% en merma por sobrestock", st["td"])],
        [Paragraph("Multi-tienda", st["td"]),
         Paragraph("Dashboard centralizado para cadenas, "
                   "benchmarking entre tiendas", st["td"]),
         Paragraph("Expansion a cadenas de 5-50 tiendas", st["td"])],
        [Paragraph("Fine-tuning", st["td"]),
         Paragraph("Modelo propio entrenado con datos reales "
                   "de MermaOps", st["td"]),
         Paragraph("Reduccion del 80% en coste de inferencia", st["td"])],
        [Paragraph("Integracion ERP", st["td"]),
         Paragraph("Conexion con SAP, Navision para sincronizacion "
                   "automatica de stock", st["td"]),
         Paragraph("Cero entrada manual de datos", st["td"])],
    ]
    elems += [
        make_table(future_data, [35*mm, 75*mm, 60*mm]),
        sp(6),
        highlight_box(
            "MermaOps: IA real, datos reales, coste real.",
            "0,80 EUR/mes · 500:1 ROI · 0 EUR de inversion inicial",
            st),
        PageBreak(),
    ]
    return elems


def build_back_cover(st):
    return [
        sp(70),
        Paragraph("MermaOps", st["back_title"]),
        HRFlowable(width=80*mm, thickness=2, color=C_GREEN,
                   spaceAfter=8*mm, spaceBefore=6*mm),
        Paragraph("@ChuwiMermaOpsBot", ParagraphStyle(
            "bc_bot", fontSize=22, fontName="Helvetica-Bold",
            textColor=C_GREEN, alignment=TA_CENTER)),
        sp(6),
        Paragraph("alvaroferrermarg@gmail.com", st["back_sub"]),
        Paragraph("Trabajo Final de Master · 2026", st["back_sub"]),
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Building MermaOps Memoria Completa PDF...")

    st = build_styles()

    # Dark pages: cover (1), back cover (last = 12 approx, we track via set)
    dark_pages = {1, 12}
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
    story += build_cover(st)       # page 1 (dark)
    story += build_toc(st)         # page 2
    story += build_resumen(st)     # page 3
    story += build_problema(st)    # page 4
    story += build_arquitectura(st)# page 5
    story += build_agentes(st)     # page 6
    story += build_decisiones_tecnicas(st)  # page 7
    story += build_resultados(st)  # page 8
    story += build_normativo(st)   # page 9
    story += build_stack(st)       # page 10
    story += build_conclusiones(st)# page 11
    story += build_back_cover(st)  # page 12 (dark)

    doc.build(story,
              onFirstPage=bg.on_page,
              onLaterPages=bg.on_page)

    print(f"Done: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
