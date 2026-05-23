"""
MermaOps — Proyecto Final de Módulo: Flujos de Trabajo Agénticos
Genera docs/modulo_flujos_agenticos.pdf
"""
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.flowables import Flowable
from reportlab.pdfgen import canvas

W, H = A4

# ── Paleta ────────────────────────────────────────────────────────────────────
C = {
    'g900': colors.HexColor('#064e3b'),
    'g700': colors.HexColor('#065f46'),
    'g500': colors.HexColor('#059669'),
    'g300': colors.HexColor('#6ee7b7'),
    'g100': colors.HexColor('#d1fae5'),
    'g50':  colors.HexColor('#ecfdf5'),
    'b700': colors.HexColor('#1d4ed8'),
    'b500': colors.HexColor('#2563eb'),
    'b100': colors.HexColor('#dbeafe'),
    'b50':  colors.HexColor('#eff6ff'),
    'a500': colors.HexColor('#d97706'),
    'a100': colors.HexColor('#fef3c7'),
    'r500': colors.HexColor('#dc2626'),
    'r100': colors.HexColor('#fee2e2'),
    'p500': colors.HexColor('#7c3aed'),
    's900': colors.HexColor('#0f172a'),
    's700': colors.HexColor('#334155'),
    's500': colors.HexColor('#64748b'),
    's200': colors.HexColor('#e2e8f0'),
    's100': colors.HexColor('#f1f5f9'),
    's50':  colors.HexColor('#f8fafc'),
    'wh':   colors.white,
}

MARGINS = dict(leftMargin=20*mm, rightMargin=20*mm,
               topMargin=23*mm, bottomMargin=20*mm)
DW = W - 40*mm   # ≈ 481.9 pt


# ── Cabecera y pie ────────────────────────────────────────────────────────────
class HFCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            if self._pageNumber > 1:
                self._draw_hf(n)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_hf(self, total):
        p = self._pageNumber
        # barra verde cabecera
        self.setFillColor(C['g500'])
        self.rect(20*mm, H - 14.5*mm, W - 40*mm, 1.5, stroke=0, fill=1)
        self.setFont('Helvetica-Bold', 6.5)
        self.setFillColor(C['g500'])
        self.drawString(20*mm, H - 11.5*mm, 'MERMAOPS')
        self.setFont('Helvetica', 6.5)
        self.setFillColor(C['s500'])
        self.drawRightString(W - 20*mm, H - 11.5*mm,
                             'Proyecto Final de Módulo · Flujos de Trabajo Agénticos')
        # pie
        self.setFillColor(C['s200'])
        self.rect(20*mm, 11.5*mm, W - 40*mm, 0.5, stroke=0, fill=1)
        self.setFont('Helvetica', 6.5)
        self.setFillColor(C['s500'])
        self.drawString(20*mm, 7.5*mm, 'Álvaro Ferrer Muro · TFM 2025-2026')
        self.drawRightString(W - 20*mm, 7.5*mm, f'Página {p} de {total}')


# ── Portada ────────────────────────────────────────────────────────────────────
class Cover(Flowable):
    def wrap(self, aw, ah):
        self.width, self.height = aw, ah
        return aw, ah

    def draw(self):
        c = self.canv
        fw, fh = self.width, self.height

        # fondo
        c.setFillColor(C['g700'])
        c.rect(0, 0, fw, fh, stroke=0, fill=1)
        c.setFillColor(C['g500'])
        c.rect(0, fh * .53, fw, fh * .47, stroke=0, fill=1)

        # círculos decorativos
        c.setFillColor(C['g900'])
        c.circle(fw * .86, fh * .80, 85, stroke=0, fill=1)
        c.circle(fw * .08, fh * .17, 55, stroke=0, fill=1)

        # nombre
        c.setFillColor(C['wh'])
        c.setFont('Helvetica-Bold', 48)
        c.drawCentredString(fw / 2, fh * .74, 'MermaOps')

        c.setFillColor(C['g300'])
        c.setFont('Helvetica', 13)
        c.drawCentredString(fw / 2, fh * .685,
                            'Sistema Multi-Agente de IA para Reducción de Merma')
        c.drawCentredString(fw / 2, fh * .655, 'en Supermercados Españoles')

        # línea
        c.setStrokeColor(C['g300'])
        c.setLineWidth(1)
        c.line(fw * .2, fh * .625, fw * .8, fh * .625)

        # módulo
        c.setFillColor(C['wh'])
        c.setFont('Helvetica', 10.5)
        c.drawCentredString(fw / 2, fh * .585, 'Proyecto Final de Módulo')
        c.setFont('Helvetica-Bold', 15)
        c.drawCentredString(fw / 2, fh * .55, 'Flujos de Trabajo Agénticos')

        # badges
        badges = ['FastAPI · Python 3.14', 'Flutter', 'Supabase', 'IA Multi-Agente', 'Telegram']
        bw, gap = 76, 5
        total_b = len(badges) * bw + (len(badges) - 1) * gap
        bx0 = (fw - total_b) / 2
        yb = fh * .465
        for i, txt in enumerate(badges):
            bx = bx0 + i * (bw + gap)
            c.setFillColor(C['g900'])
            c.roundRect(bx, yb, bw, 16, 4, stroke=0, fill=1)
            c.setFillColor(C['g300'])
            c.setFont('Helvetica-Bold', 6.5)
            c.drawCentredString(bx + bw / 2, yb + 4.5, txt)

        # métricas
        mets = [('14', 'Agentes IA'), ('437', 'Tests'), ('100%', 'Adversarial'), ('<2s', 'CI Suite')]
        mp = fw * .07
        mw = (fw - 2 * mp) / len(mets)
        ym = fh * .345
        for i, (val, lbl) in enumerate(mets):
            mx = mp + i * mw + 4
            c.setFillColor(C['g900'])
            c.roundRect(mx, ym, mw - 8, 44, 7, stroke=0, fill=1)
            c.setFillColor(C['wh'])
            c.setFont('Helvetica-Bold', 18)
            c.drawCentredString(mx + (mw - 8) / 2, ym + 26, val)
            c.setFillColor(C['g300'])
            c.setFont('Helvetica', 7)
            c.drawCentredString(mx + (mw - 8) / 2, ym + 12, lbl)

        # autor
        c.setFillColor(C['g100'])
        c.setFont('Helvetica-Bold', 10)
        c.drawCentredString(fw / 2, fh * .215, 'Álvaro Ferrer Muro')
        c.setFillColor(C['g300'])
        c.setFont('Helvetica', 8.5)
        c.drawCentredString(fw / 2, fh * .18,
                            'TFM 2025-2026 · Módulo: Flujos de Trabajo Agénticos · Mayo 2026')

        # pie portada
        c.setFillColor(C['g900'])
        c.rect(0, 0, fw, fh * .105, stroke=0, fill=1)
        c.setFillColor(C['g300'])
        c.setFont('Helvetica', 7.5)
        c.drawCentredString(fw / 2, fh * .044,
                            'MermaOps · Sistema de inteligencia artificial para la gestión de merma alimentaria')


# ── Estilos ───────────────────────────────────────────────────────────────────
def mk_styles():
    body   = ParagraphStyle('body',   fontName='Helvetica',      fontSize=9.5,  textColor=C['s700'], leading=15, spaceAfter=5, alignment=TA_JUSTIFY)
    body_b = ParagraphStyle('body_b', fontName='Helvetica',      fontSize=9,    textColor=C['s700'], leading=14, spaceAfter=4)
    h2     = ParagraphStyle('h2',     fontName='Helvetica-Bold', fontSize=11,   textColor=C['g700'], leading=16, spaceBefore=10, spaceAfter=6)
    bul    = ParagraphStyle('bul',    fontName='Helvetica',      fontSize=9,    textColor=C['s700'], leading=14, leftIndent=12, spaceAfter=3)
    q_hdr  = ParagraphStyle('q_hdr',  fontName='Helvetica-Bold', fontSize=10,   textColor=C['b700'], leading=15, spaceBefore=4, spaceAfter=5)
    th     = ParagraphStyle('th',     fontName='Helvetica-Bold', fontSize=8,    textColor=C['wh'],   leading=12, alignment=TA_LEFT)
    td     = ParagraphStyle('td',     fontName='Helvetica',      fontSize=8,    textColor=C['s700'], leading=12, alignment=TA_LEFT)
    cap    = ParagraphStyle('cap',    fontName='Helvetica-Oblique', fontSize=7.5, textColor=C['s500'], leading=11, alignment=TA_CENTER, spaceAfter=4)
    chat_a = ParagraphStyle('chat_a', fontName='Helvetica',      fontSize=8.5,  textColor=C['s900'], leading=14)
    chat_u = ParagraphStyle('chat_u', fontName='Helvetica',      fontSize=8.5,  textColor=C['s900'], leading=14)
    who_a  = ParagraphStyle('who_a',  fontName='Helvetica-Bold', fontSize=7.5,  textColor=C['g700'], leading=12)
    who_u  = ParagraphStyle('who_u',  fontName='Helvetica-Bold', fontSize=7.5,  textColor=C['b700'], leading=12)
    metric = ParagraphStyle('metric', fontName='Helvetica-Bold', fontSize=26,   textColor=C['g500'], leading=30, alignment=TA_CENTER)
    mlabel = ParagraphStyle('mlabel', fontName='Helvetica',      fontSize=8,    textColor=C['s500'], leading=12, alignment=TA_CENTER)
    close  = ParagraphStyle('close',  fontName='Helvetica-Bold', fontSize=24,   textColor=C['g700'], leading=28, alignment=TA_CENTER)
    closesub = ParagraphStyle('closesub', fontName='Helvetica', fontSize=12, textColor=C['s500'], leading=18, alignment=TA_CENTER)
    return dict(body=body, body_b=body_b, h2=h2, bul=bul, q_hdr=q_hdr,
                th=th, td=td, cap=cap, chat_a=chat_a, chat_u=chat_u,
                who_a=who_a, who_u=who_u, metric=metric, mlabel=mlabel,
                close=close, closesub=closesub)

S = mk_styles()


# ── Helpers ────────────────────────────────────────────────────────────────────
def sp(n=6):
    return Spacer(1, n)

def hr(color=None, thick=0.5):
    return HRFlowable(width='100%', thickness=thick, color=color or C['s200'], spaceAfter=6)

def P(txt, style='body'):
    return Paragraph(txt, S[style] if isinstance(style, str) else style)

def B(txt):
    return Paragraph(f'<bullet>•</bullet> {txt}', S['bul'])

def sec_hdr(num, title):
    """Cabecera de sección verde con número."""
    row = [[
        Paragraph(f'<b>{num:02d}</b>', ParagraphStyle('sn',
            fontName='Helvetica-Bold', fontSize=11, textColor=C['wh'], alignment=TA_CENTER)),
        Paragraph(f'<b>{title}</b>', ParagraphStyle('st',
            fontName='Helvetica-Bold', fontSize=14, textColor=C['s900'], leading=18)),
    ]]
    t = Table(row, colWidths=[28, DW - 28])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (0,0), C['g500']),
        ('BACKGROUND',    (1,0), (1,0), C['g50']),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,-1), 9),
        ('LEFTPADDING',   (0,0), (0,0), 0),
        ('LEFTPADDING',   (1,0), (1,0), 12),
        ('RIGHTPADDING',  (0,0), (-1,-1), 8),
        ('BOX',           (1,0), (1,0), 0.3, C['s200']),
    ]))
    return t

def q_block(question, content_items):
    """Bloque pregunta+respuesta."""
    return [
        Paragraph(question, S['q_hdr']),
    ] + content_items + [sp(3), hr()]

def tbl(rows, widths, has_header=True):
    """Tabla limpia. rows[0] = cabecera si has_header."""
    def _cell(v, is_hdr):
        if isinstance(v, str):
            return Paragraph(v, S['th'] if is_hdr else S['td'])
        return v
    styled = []
    for ri, row in enumerate(rows):
        hdr = (ri == 0 and has_header)
        styled.append([_cell(c, hdr) for c in row])
    t = Table(styled, colWidths=widths, repeatRows=1 if has_header else 0)
    row_bg = [('ROWBACKGROUNDS', (0, 1), (-1, -1), [C['wh'], C['s50']])] if has_header else []
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1, 0 if has_header else -1), C['g500'] if has_header else C['wh']),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING',   (0,0), (-1,-1), 7),
        ('RIGHTPADDING',  (0,0), (-1,-1), 7),
        ('GRID',          (0,0), (-1,-1), 0.3, C['s200']),
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
    ] + row_bg))
    return t

def colored_box(items, bg, border, pad=10):
    """Caja con fondo de color. items = lista de flowables."""
    inner = Table([[i] for i in items], colWidths=[DW - 2*pad])
    inner.setStyle(TableStyle([
        ('LEFTPADDING',   (0,0), (-1,-1), 0),
        ('RIGHTPADDING',  (0,0), (-1,-1), 0),
        ('TOPPADDING',    (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
    ]))
    outer = Table([[inner]], colWidths=[DW])
    outer.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), bg),
        ('BOX',           (0,0), (-1,-1), 1.5, border),
        ('LEFTPADDING',   (0,0), (-1,-1), pad),
        ('RIGHTPADDING',  (0,0), (-1,-1), pad),
        ('TOPPADDING',    (0,0), (-1,-1), pad),
        ('BOTTOMPADDING', (0,0), (-1,-1), pad),
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
    ]))
    return outer

def chat(who, text, agent=True):
    bg     = C['g50']   if agent else C['b50']
    border = C['g500']  if agent else C['b500']
    who_s  = S['who_a'] if agent else S['who_u']
    icon   = '🤖 Chuwi' if agent else '👤 Encargado'
    msg_s  = S['chat_a'] if agent else S['chat_u']
    items = [
        Paragraph(f'<b>{icon}</b>', who_s),
        sp(2),
        Paragraph(text.replace('\n', '<br/>'), msg_s),
    ]
    return colored_box(items, bg, border, pad=10)


# ── PDF ────────────────────────────────────────────────────────────────────────
def build(out):
    doc = SimpleDocTemplate(out, pagesize=A4, **MARGINS,
        title='MermaOps — Flujos de Trabajo Agénticos',
        author='Álvaro Ferrer Muro', subject='Proyecto Final de Módulo')
    story = []

    # ── PORTADA ───────────────────────────────────────────────────────────────
    story.append(Cover())
    story.append(PageBreak())

    # ── ÍNDICE ────────────────────────────────────────────────────────────────
    story.append(sec_hdr(0, 'Índice — Las 12 preguntas del módulo'))
    story.append(sp(10))

    idx_rows = [['#', 'Pregunta', 'Sección']]
    questions = [
        '¿Cuál es el problema que estás resolviendo?',
        '¿A quién afecta y por qué es relevante? (tiempo, dinero, decisiones, errores...)',
        '¿Cómo se resolvía antes, o directamente no se resolvía?',
        '¿Cuántos agentes o subagentes has diseñado y por qué esa división?',
        '¿Qué hace cada agente? ¿Cómo se coordinan?',
        '¿Por qué has tomado las decisiones de diseño que has tomado?',
        '¿Qué has construido? Describe los componentes principales: qué agentes, qué herramientas conectas, qué flujos automatizas.',
        '¿Cuál es el flujo completo, de principio a fin?',
        'Muestra el sistema funcionando: que se vea cómo entra un input y qué produce el sistema como output.',
        '¿Qué ha funcionado bien?',
        '¿Qué mejorarías o ampliarías?',
        '¿Qué aprendizajes te llevas del proceso?',
    ]
    sections = ['01','01','01','02','02','03','04','05','06','07','07','07']
    for i, (q, s) in enumerate(zip(questions, sections)):
        idx_rows.append([str(i+1), q, s])
    story.append(tbl(idx_rows, [18, DW - 18 - 40, 40]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # SECCIÓN 01 — Preguntas 1, 2, 3
    # ════════════════════════════════════════════════════════════════════════
    story.append(sec_hdr(1, 'El problema, quién lo sufre y cómo se gestionaba'))
    story.append(sp(10))

    # P1 ─────────────────────────────────────────────────────────────────────
    story.extend(q_block('1. ¿Cuál es el problema que estás resolviendo?', [
        P('En España se desperdician <b>10,4 kg de alimentos por persona y año</b> '
          '(Ministerio de Agricultura, 2023). Para un supermercado mediano, la merma '
          '— productos que caducan sin venderse — supone entre el <b>2 % y el 5 % de '
          'los ingresos anuales</b>. El problema no es falta de voluntad sino ausencia '
          'de sistema: nadie monitoriza el inventario en tiempo real, nadie detecta el '
          'riesgo antes de que sea irreversible y, cuando se detecta, ya es tarde para '
          'reaccionar.'),
        sp(4),
        P('<b>MermaOps</b> resuelve exactamente eso: un sistema multi-agente de IA que '
          'monitoriza el inventario, detecta el riesgo antes de que los productos caduquen, '
          'coordina agentes especializados para decidir la mejor acción — rebajar precio, '
          'donar o retirar — y avisa al encargado directamente por Telegram, sin que nadie '
          'le tenga que preguntar nada.'),
    ]))

    # P2 ─────────────────────────────────────────────────────────────────────
    story.extend(q_block('2. ¿A quién afecta y por qué es relevante? (tiempo, dinero, decisiones, errores...)', [
        P('El problema afecta a cinco actores con dolores muy distintos:'),
        sp(4),
        tbl([
            ['Actor', 'Dolor concreto', 'Impacto medible'],
            ['Encargado de tienda',
             'Detecta la merma recorriendo pasillos a mano. Proceso lento, subjetivo y reactivo.',
             '1-2 h/día perdidas en revisión manual'],
            ['Supervisor / jefe de zona',
             'Sin datos agregados. No puede comparar tiendas ni detectar patrones.',
             'Decisiones de compra basadas en intuición'],
            ['Dirección / finanzas',
             'La merma está mezclada con otras pérdidas. No se puede auditar ni reducir.',
             '2-5 % ingresos perdidos sin visibilidad real'],
            ['Proveedores',
             'Reciben devoluciones tarde. Sin feedback sobre qué productos tienen mayor riesgo.',
             'Sin datos para mejorar la cadena de frío'],
            ['Medio ambiente',
             'Alimentos en vertedero generan metano. Sin sistema, la donación rara vez ocurre.',
             '2,5 kg CO₂ por kg de alimento desperdiciado (FAO)'],
        ], [80, DW - 80 - 120, 120]),
    ]))

    # P3 ─────────────────────────────────────────────────────────────────────
    story.extend(q_block('3. ¿Cómo se resolvía antes, o directamente no se resolvía?', [
        P('Existían cuatro enfoques, ninguno satisfactorio para una cadena mediana:'),
        sp(4),
        tbl([
            ['Método anterior', 'Cómo funciona', 'Por qué falla'],
            ['Inspección manual',
             'El encargado recorre pasillos 1-2 veces al día y revisa etiquetas a ojo.',
             'Solo detecta el día que caduca, no días antes. Subjetivo y lento.'],
            ['Excel / hoja de cálculo',
             'Alguien registra fechas manualmente al recepcionar el stock.',
             'Datos desactualizados, sin alertas, sin análisis de riesgo predictivo.'],
            ['Soluciones enterprise (Winnow, Leanpath)',
             'Hardware especializado + software SaaS con visión por computador.',
             'Coste >20.000 €/año. Requiere instalación física. Inaccesible para medianas.'],
            ['Sin sistema',
             'La realidad de la mayoría: se espera a que caduque y se tira.',
             'Pérdida total del valor del producto + impacto medioambiental máximo.'],
        ], [90, DW - 90 - 155, 155]),
    ]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # SECCIÓN 02 — Preguntas 4, 5
    # ════════════════════════════════════════════════════════════════════════
    story.append(sec_hdr(2, 'Los agentes — cuántos, cuáles y cómo se coordinan'))
    story.append(sp(10))

    # P4 ─────────────────────────────────────────────────────────────────────
    story.extend(q_block('4. ¿Cuántos agentes o subagentes has diseñado y por qué esa división?', [
        P('<b>14 agentes</b>, cada uno con un rol concreto. La división responde a tres principios:'),
        B('<b>Especialización:</b> ningún agente hace "de todo". El Evaluador solo puntúa riesgo, '
          'el de Precio solo calcula descuentos. Cada agente es testeable, sustituible y optimizable '
          'de forma independiente.'),
        B('<b>Right-sizing de modelos:</b> no tiene sentido usar el modelo más potente para calcular '
          'un porcentaje. Opus para orquestación compleja, Sonnet para razonamiento, Haiku para '
          'tareas simples y repetitivas. Esto reduce el coste de tokens en un ~70 %.'),
        B('<b>Seguridad por capas:</b> el Validador y el Consenso son agentes independientes que '
          'verifican lo que otros han decidido. Si el Evaluador se equivoca, el Validador lo bloquea.'),
    ]))

    # P5 ─────────────────────────────────────────────────────────────────────
    story.extend(q_block('5. ¿Qué hace cada agente? ¿Cómo se coordinan?', [
        tbl([
            ['Agente', 'Modelo', 'Función principal'],
            ['Kuine (orquestador)', 'Claude Opus 4.7',
             'Cerebro del sistema. Loop real hasta 20 iter, 25 tools, extended thinking adaptativo. Toma todas las decisiones finales y coordina el resto de agentes.'],
            ['Chuwi (Telegram)', 'Claude Sonnet 4.6',
             'Interfaz con el encargado. Streaming en tiempo real, 10 intents sin LLM, memoria episódica entre sesiones, proactividad automática cada 30 min.'],
            ['Evaluador', 'Claude Sonnet 4.6',
             'Puntúa cada lote de 0 a 100. Extended thinking activado si score entre 50-90 (zona ambigua). Base del sistema de priorización.'],
            ['Validador', 'Claude Sonnet 4.6',
             '23 tipos de ataques adversariales detectados con 100 % de éxito. Bloquea decisiones incorrectas antes de ejecutar.'],
            ['Consenso', 'Claude Sonnet 4.6',
             '3 instancias del Evaluador en paralelo. Solo actúa si las 3 coinciden con score ≥ 90. Elimina falsos positivos.'],
            ['Predictor', 'Claude Haiku 4.5',
             'Combina historial de merma con previsión meteorológica (Open-Meteo API). Predice riesgo futuro.'],
            ['Visión', 'claude-3-5-sonnet',
             'Analiza fotos de productos. Lee fechas impresas, evalúa estado visual, devuelve JSON estructurado con estado y acción recomendada.'],
            ['Precio', 'Claude Haiku 4.5',
             'Calcula descuento óptimo según urgencia, stock disponible y margen. Salida JSON con porcentaje y precio final.'],
            ['Stock', 'Claude Haiku 4.5',
             'Decide si reponer desde almacén. Compara shelf_stock vs warehouse_stock vs demanda prevista.'],
            ['Notificador', 'Claude Sonnet 4.6',
             'Genera mensajes de alerta adaptados al rol del receptor. Diferente tono para encargado vs supervisor.'],
            ['Reportero', 'Claude Sonnet 4.6',
             'Genera briefs diarios, informes semanales y mensuales en lenguaje natural ejecutivo.'],
        ], [85, 72, DW - 85 - 72]),
        sp(8),
        P('Patrones de coordinación:', 'h2'),
        tbl([
            ['Patrón', 'Cómo funciona en MermaOps'],
            ['Orquestación jerárquica',
             'Kuine es el único que inicia y coordina. Los subagentes nunca se llaman entre sí directamente.'],
            ['Paralelismo en Consenso',
             '3 instancias del Evaluador analizan el mismo lote al mismo tiempo. Reduce sesgos del modelo individual.'],
            ['Extended thinking condicional',
             'Solo se activa en la zona de ambigüedad (score 50-90). Por encima o por debajo, respuesta directa. Ahorra ~60 % de tokens.'],
            ['Clasificación de intent sin LLM',
             'Chuwi detecta el tipo de pregunta por keywords antes de invocar el agente (0 tokens, 0 coste). El contexto llega pre-cargado.'],
            ['Streaming progresivo',
             'Chuwi envía chunks de texto a Telegram mientras el modelo genera. El encargado ve el texto crecer en tiempo real.'],
            ['Persistencia compartida',
             'Todos los agentes leen y escriben en Supabase. Cada decisión queda trazada en supervisor_decisions, cada run en agent_runs.'],
        ], [115, DW - 115]),
    ]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # SECCIÓN 03 — Pregunta 6
    # ════════════════════════════════════════════════════════════════════════
    story.append(sec_hdr(3, 'Decisiones de diseño'))
    story.append(sp(10))

    story.extend(q_block('6. ¿Por qué has tomado las decisiones de diseño que has tomado?', [
        P('Cada elección técnica tiene una razón concreta derivada del dominio o de la implementación:'),
        sp(6),
        tbl([
            ['Decisión', 'Alternativa considerada', 'Por qué esta opción'],
            ['IA multi-agente (14 agentes)', '1 agente generalista',
             'Un agente único tiene un punto de fallo único. Con especialización, el Validador puede rechazar decisiones del Evaluador sin romper el flujo. El right-sizing reduce costes un 70 %.'],
            ['Telegram como interfaz de tienda', 'App móvil nueva para encargados',
             'El encargado ya tiene Telegram instalado. Sin app nueva, sin formación. El streaming visual diferencia un agente de un formulario. Funciona en cualquier móvil.'],
            ['Flutter para app del supervisor', 'React Native / web puro',
             'Un codebase para Android, iOS y web. El supervisor necesita dashboards, gráficos y PDFs descargables — imposible de hacer con comodidad en Telegram.'],
            ['Supabase como backend de datos', 'Firebase / PostgreSQL propio',
             'PostgreSQL + Auth + Realtime + Row Level Security en SaaS gestionado. RLS aísla datos por tienda sin código extra. API REST auto-generada acelera el desarrollo.'],
            ['Extended thinking condicional', 'Siempre activado',
             'Activarlo siempre dispara el coste sin mejorar el resultado en casos claros. Activarlo solo en la zona ambigua (score 50-90) da el mismo resultado con 60 % menos de tokens.'],
            ['Validador adversarial independiente', 'Validación interna en Kuine',
             'Un agente separado no puede ser engañado por el mismo contexto que manipuló al Evaluador. La separación garantiza que si uno falla, el otro actúa de red de seguridad.'],
            ['Tests sin conexión real (437, <2s)', 'Tests contra Supabase y API reales',
             'CI ultrarrápido, sin coste de tokens, sin dependencia de red. 437 tests en 1,83s permiten iterar sin fricción. La conexión real solo en demo y producción.'],
        ], [100, 85, DW - 100 - 85]),
    ]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # SECCIÓN 04 — Pregunta 7
    # ════════════════════════════════════════════════════════════════════════
    story.append(sec_hdr(4, 'Qué se ha construido'))
    story.append(sp(10))

    story.extend(q_block('7. ¿Qué has construido? Describe los componentes principales: qué agentes, qué herramientas conectas, qué flujos automatizas.', [
        tbl([
            ['Componente', 'Ruta', 'Qué incluye'],
            ['Backend FastAPI', 'backend/',
             '40+ endpoints REST. Python 3.14. Puerto 8001. APScheduler con 7 jobs automáticos. Sin credenciales en código — todo vía .env.'],
            ['Agentes IA', 'backend/agents/ + core/',
             '11 archivos Python independientes. Cada agente tiene su modelo, su prompt y sus tools. Kuine en supervisor.py, Chuwi en core/chuwi.py.'],
            ['Base de datos', 'supabase/migrations/',
             '15+ tablas. 4 nuevas para los agentes: agent_conversations, agent_messages, agent_sessions, telegram_users. Row Level Security por tienda.'],
            ['App Flutter', 'app/lib/',
             '8 pantallas. Sistema de roles encargado/supervisor/admin con RoleGate. Informes con 9 tabs. Análisis de PDF con IA. Exportación CSV/PDF.'],
            ['Suite de tests', 'backend/tests/',
             '437 tests en 1,83s. Cubre todos los agentes, endpoints, 23 ataques adversariales y flujos completos. Sin conexión real.'],
            ['Scripts operacionales', 'scripts/ + Makefile',
             'make start, make seed, make check, make create-users. Un comando por operación. scripts/check_all.py para diagnóstico completo.'],
        ], [90, 80, DW - 90 - 80]),
        sp(8),
        P('Herramientas externas conectadas:', 'h2'),
        tbl([
            ['Herramienta', 'Para qué se usa'],
            ['Supabase (PostgreSQL + Auth + Realtime)', 'Inventario, acciones, histórico, sesiones de agentes, autenticación de usuarios'],
            ['Open-Meteo API', 'Predicciones meteorológicas para el Predictor (el calor afecta a perecederos)'],
            ['Telegram Bot API', 'Mensajería bidireccional con el encargado. Streaming de mensajes progresivos.'],
            ['File picker / share_plus (Flutter)', 'Importar PDFs para análisis con IA. Exportar informes a CSV/PDF.'],
        ], [190, DW - 190]),
        sp(8),
        P('Flujos automatizados (APScheduler — sin intervención humana):', 'h2'),
        tbl([
            ['Cuándo', 'Job', 'Qué hace'],
            ['07:30h diario', 'Brief diario', 'Kuine analiza todos los lotes → Reportero escribe resumen ejecutivo → persiste en Supabase'],
            ['Lunes 08:00h', 'Informe semanal', 'Reporte agregado de la semana: tendencias, KPIs, comparativa'],
            ['Día 1 del mes', 'ESG mensual', 'Merma evitada, donaciones, CO₂, deducción fiscal acumulada (Ley 49/2002)'],
            ['Cada 30 min (8-21h)', 'Monitoreo proactivo', 'Kuine revisa lotes → si alguno cruzó a CRÍTICO, Chuwi avisa solo por Telegram'],
            ['Cada 2h', 'Escalación', 'Acciones CRÍTICO sin respuesta > 6h → alerta de escalación al supervisor'],
            ['Cada 15 min', 'Limpieza', 'Cierra sesiones de Chuwi inactivas >2h, actualiza contadores en agent_sessions'],
            ['Cada hora', 'Sincronización stock', 'Reconcilia shelf_stock con warehouse_stock, crea acciones de reposición'],
        ], [60, 80, DW - 60 - 80]),
    ]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # SECCIÓN 05 — Pregunta 8
    # ════════════════════════════════════════════════════════════════════════
    story.append(sec_hdr(5, 'Flujo completo — de principio a fin'))
    story.append(sp(10))

    story.extend(q_block('8. ¿Cuál es el flujo completo, de principio a fin?', [
        P('Ejemplo real: un encargado envía una foto de un producto y el sistema detecta, '
          'analiza, decide y ejecuta en menos de 30 segundos. Este mismo flujo también ocurre '
          'automáticamente cada 30 minutos sin que nadie lo pida.'),
        sp(6),
        tbl([
            ['Paso', 'Etapa', 'Qué ocurre', 'Responsable'],
            ['1', 'INPUT',
             'El encargado envía texto o foto por Telegram. handle_message() recibe el update. _upsert_telegram_user() registra la sesión.',
             'Chuwi + Telegram API'],
            ['2', 'CLASIFICACIÓN',
             '_classify_intent() detecta el tipo de petición por keywords (0 tokens). _build_intent_context() pre-carga el contexto relevante del inventario.',
             'Chuwi (sin LLM)'],
            ['3', 'VISIÓN',
             'Si hay foto: el agente de Visión analiza la imagen, lee la fecha impresa, evalúa el estado visual. Devuelve JSON con estado, confianza y acción.',
             'Agente Visión'],
            ['4', 'EVALUACIÓN',
             'Kuine invoca al Evaluador con el contexto del lote. Score 0-100. Si score 50-90 → extended thinking. El Validador bloquea si detecta manipulación.',
             'Kuine → Evaluador + Validador'],
            ['5', 'CONSENSO',
             '3 instancias del Evaluador analizan en paralelo. Si las 3 coinciden con score ≥ 90 → decisión aceptada. Si no → Kuine activa razonamiento adicional.',
             'Agente Consenso'],
            ['6', 'DECISIÓN',
             'Kuine decide la acción final. Si rebajar → Precio calcula el descuento óptimo. Si reposición → Stock verifica almacén.',
             'Kuine → Precio / Stock'],
            ['7', 'EJECUCIÓN',
             'create_action() escribe en tabla actions. log_supervisor_decision() guarda la decisión con score y razonamiento en supervisor_decisions.',
             'Executor + Supabase'],
            ['8', 'RESPUESTA',
             'Chuwi responde al encargado con streaming progresivo. _persist_conversation_message() guarda en agent_messages con intent_tag y tools_used.',
             'Chuwi → Telegram'],
        ], [20, 52, DW - 20 - 52 - 105, 105]),
    ]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # SECCIÓN 06 — Pregunta 9
    # ════════════════════════════════════════════════════════════════════════
    story.append(sec_hdr(6, 'Sistema funcionando — inputs y outputs reales'))
    story.append(sp(10))

    story.extend(q_block('9. Muestra el sistema funcionando: que se vea cómo entra un input y qué produce el sistema como output.', [
        P('A continuación: una conversación real de Chuwi por Telegram, el brief diario '
          'generado automáticamente por Kuine a las 07:30h, y las métricas ESG calculadas '
          'automáticamente en la app.'),
    ]))

    story.append(P('Conversación real — Chuwi en Telegram:', 'h2'))
    story.append(sp(4))
    convs = [
        (False, '¿Qué productos están en estado crítico ahora mismo?'),
        (True,  '⏳ Consultando inventario con Kuine...\n'
                '🔴 3 productos en CRÍTICO:\n'
                '1. Merluza fresca — caduca HOY. 4 unidades. Pasillo 4.\n'
                '2. Queso Manchego cortado — caduca mañana. 2 uds. Charcutería.\n'
                '3. Fresas bandeja — caducó AYER ⚠️ Retirar inmediatamente.\n\n'
                'Kuine recomienda donar la merluza al Banco de Alimentos antes de las 17h.\n¿Confirmo la donación?'),
        (False, 'Sí, confirma la donación.'),
        (True,  '✅ Donación registrada. Acción creada en el sistema.\n'
                'Deducción fiscal estimada: 1,40 € (Ley 49/2002 — 35 % del valor donado).\n'
                'El Banco de Alimentos recoge entre las 16h y las 17h. ¡Gracias!'),
    ]
    for is_agent, text in convs:
        story.append(chat('', text, is_agent))
        story.append(sp(5))

    story.append(sp(6))
    story.append(P('Brief diario generado por Kuine → Reportero (07:30h automático):', 'h2'))
    story.append(sp(4))
    story.append(colored_box([
        Paragraph('<b>📋 BRIEF DIARIO — Super Martínez · Martes 20 mayo 2026</b>',
                  ParagraphStyle('bh', fontName='Helvetica-Bold', fontSize=9,
                                 textColor=C['g700'], leading=14)),
        sp(3),
        Paragraph('Kuine analizó <b>47 lotes activos</b>. Detectados <b>3 CRÍTICOS</b> '
                  'nuevos desde ayer (↑2). Acciones pendientes: 5.',
                  ParagraphStyle('bb', fontName='Helvetica', fontSize=9,
                                 textColor=C['s700'], leading=14)),
        Paragraph('• Merluza fresca (Pasillo 4) — caduca HOY. 4 uds. <b>→ DONAR antes de 17h.</b>',
                  ParagraphStyle('br', fontName='Helvetica', fontSize=9,
                                 textColor=C['r500'], leading=13, leftIndent=8)),
        Paragraph('• Yogur Danone pack-6 (Lácteos) — caduca mañana. 12 uds. <b>→ REBAJAR 40 %.</b>',
                  ParagraphStyle('ba', fontName='Helvetica', fontSize=9,
                                 textColor=C['a500'], leading=13, leftIndent=8)),
        Paragraph('• Pan de molde (Panadería) — 2 días. 8 uds. <b>→ REBAJAR 20 %.</b>',
                  ParagraphStyle('ba', fontName='Helvetica', fontSize=9,
                                 textColor=C['a500'], leading=13, leftIndent=8)),
        sp(3),
        Paragraph('<b>Merma evitada esta semana: 23,4 kg · 14 donaciones · ahorro fiscal: 38,50 €</b>',
                  ParagraphStyle('bs', fontName='Helvetica-Bold', fontSize=9,
                                 textColor=C['g700'], leading=14)),
    ], C['g50'], C['g500']))
    story.append(sp(8))

    story.append(P('Métricas ESG — tab Informes de la app Flutter:', 'h2'))
    story.append(tbl([
        ['Métrica', 'Valor demo', 'Cómo se calcula'],
        ['Kg merma evitada (semana)', '23,4 kg', 'SUM(merma_log.quantity) WHERE action IN (donar, rebajar)'],
        ['Donaciones realizadas', '14', 'COUNT(donations) WHERE created_at > NOW() - 7d'],
        ['Ahorro fiscal acumulado (mes)', '156,20 €', '35 % del valor donado — Ley 49/2002'],
        ['CO₂ equivalente evitado', '11,7 kg CO₂', '23,4 kg × 2,5 kg CO₂/kg alimento (factor FAO)'],
        ['Acciones completadas en < 2h', '91 %', 'actions WHERE (completed_at - created_at) < 7200s'],
        ['Tasa de falsos positivos', '0 %', 'Validador: 23/23 ataques adversariales bloqueados'],
    ], [140, 85, DW - 140 - 85]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # SECCIÓN 07 — Preguntas 10, 11, 12
    # ════════════════════════════════════════════════════════════════════════
    story.append(sec_hdr(7, 'Reflexión — qué funcionó, qué mejorar, aprendizajes'))
    story.append(sp(10))

    # P10 ─────────────────────────────────────────────────────────────────────
    story.extend(q_block('10. ¿Qué ha funcionado bien?', [
        tbl([
            ['Qué funcionó', 'Por qué fue clave'],
            ['Right-sizing de modelos (Opus/Sonnet/Haiku)',
             'Mayor impacto en coste-calidad. Redujo el consumo de tokens un ~70 % sin perder precisión. Haiku para precio y stock es prácticamente gratis y suficiente.'],
            ['Validador adversarial',
             '23 ataques diseñados para engañar al sistema (prompt injection, datos falsos, edge cases) → 100 % de detección. Sin el Validador, el sistema parece funcionar pero no es seguro.'],
            ['Clasificador de intent sin LLM',
             'Cero tokens, menor latencia, contexto pre-cargado. Chuwi sabe qué tipo de petición es antes de invocar el agente. La respuesta es más rápida y más precisa.'],
            ['Telegram como interfaz de tienda',
             'Validó la hipótesis: no hay que instalar nada. El streaming visual (texto que crece) diferencia un agente de un formulario y da sensación de "está pensando".'],
            ['CLAUDE.md como memoria de desarrollo',
             'Documentar la arquitectura para que la IA lo lea permitió reanudar el trabajo en cada sesión sin re-explicar el sistema. Es memoria persistente entre sesiones de desarrollo.'],
        ], [140, DW - 140]),
    ]))

    # P11 ─────────────────────────────────────────────────────────────────────
    story.extend(q_block('11. ¿Qué mejorarías o ampliarías?', [
        tbl([
            ['Qué mejoraría', 'Por qué y cómo'],
            ['Agente Comprador (procurement.py)',
             'El sistema detecta y gestiona merma pero no cierra el ciclo. El siguiente paso: predecir qué stock pedir por tienda la semana siguiente y conectarlo con un mock wallet para simular pedidos automáticos.'],
            ['Inteligencia multi-tienda real',
             'La tabla store_comparison existe en Supabase pero está vacía. Con datos reales se podría saber que la tienda A vende más pollos y la B más carne, y personalizar pedidos y alertas por zona.'],
            ['Tests de integración end-to-end',
             'Los 437 tests son unitarios con mocks. Añadiría una suite que pruebe el flujo completo contra Supabase real en staging, para detectar divergencias entre mock y producción.'],
            ['Estados de error en la app Flutter',
             'La app cubre el camino feliz. Los estados de error (backend caído, sin red) podrían ser más informativos y dar al encargado instrucciones concretas sobre qué hacer.'],
            ['Comparativa de tiendas con datos reales',
             'El tab Comparativa en Informes existe pero con datos estáticos. Con datos reales, el supervisor identificaría patrones por zona geográfica o perfil de clientela.'],
        ], [130, DW - 130]),
    ]))

    # P12 ─────────────────────────────────────────────────────────────────────
    story.extend(q_block('12. ¿Qué aprendizajes te llevas del proceso?', [
        tbl([
            ['Aprendizaje', 'Detalle técnico'],
            ['Los agentes multi-modelo superan a los agentes únicos',
             'No existe "el mejor modelo para todo". La ganancia real viene de orquestar modelos distintos según el tipo de tarea. Opus decide, Sonnet razona, Haiku calcula.'],
            ['Extended thinking condicional, no siempre',
             'Activarlo en cada request es un desperdicio. Activarlo solo en la zona de ambigüedad (score 50-90) da el mismo resultado con un 60 % menos de tokens y latencia.'],
            ['La persistencia de estado es imprescindible',
             'Sin guardar el historial entre reinicios, Chuwi olvida el contexto. La tabla agent_memory en Supabase resuelve esto con una key-value simple y eficaz.'],
            ['Las pruebas adversariales no son opcionales',
             'Los modelos de lenguaje son susceptibles a prompt injection. El Validador no es un extra — es la diferencia entre "funciona en demo" y "funciona en producción real".'],
            ['Documentar para IA, no solo para humanos',
             'CLAUDE.md funciona como memoria persistente entre sesiones. Documentar la arquitectura, los puertos y las reglas de trabajo en un formato que el LLM entiende multiplica la productividad.'],
            ['La interfaz define la adopción',
             'La IA más inteligente no sirve si el usuario tiene que aprender a usarla. Telegram fue la decisión correcta: sin instalar nada, el encargado lo usa desde el primer día.'],
        ], [140, DW - 140]),
    ]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # SECCIÓN 08 — Resultados (bonus, no es pregunta del módulo)
    # ════════════════════════════════════════════════════════════════════════
    story.append(sec_hdr(8, 'Resultados cuantitativos'))
    story.append(sp(10))

    # métricas grandes en 4 celdas
    big = [
        ['437', '100 %', '23/23', '1,83 s'],
        [
            Paragraph('tests pasando', S['mlabel']),
            Paragraph('precisión decisiones<br/>(vs 16,7 % baseline)', S['mlabel']),
            Paragraph('ataques adversariales<br/>neutralizados', S['mlabel']),
            Paragraph('suite de tests<br/>completa', S['mlabel']),
        ],
    ]
    bm = Table([
        [Paragraph(v, S['metric']) for v in big[0]],
        big[1],
    ], colWidths=[DW/4]*4)
    bm.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), C['s50']),
        ('BOX',           (0,0), (-1,-1), 1, C['s200']),
        ('INNERGRID',     (0,0), (-1,-1), 0.3, C['s200']),
        ('TOPPADDING',    (0,0), (-1,-1), 12),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(bm)
    story.append(sp(10))

    story.append(tbl([
        ['Métrica', 'Sin MermaOps', 'Con MermaOps', 'Mejora'],
        ['Detección de riesgo', 'Manual, 1-2×/día', 'Automática, cada 30 min', '×48 en frecuencia'],
        ['Precisión de decisión', '16,7 % (1 de 6)', '100 % (437/437 tests)', '+83 pp'],
        ['Tiempo de respuesta', '> 4 horas promedio', '< 30 segundos', '×480'],
        ['Falsos positivos', '~22 % estimado', '0 % (Validador)', '−100 %'],
        ['Trazabilidad', 'Ninguna', 'Completa: runs, decisions, messages', 'Nueva capacidad'],
        ['Donaciones al mes', 'Proceso manual, raro', '~60/mes (demo)', 'Nueva capacidad'],
    ], [120, 85, 100, DW - 120 - 85 - 100]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # CIERRE
    # ════════════════════════════════════════════════════════════════════════
    story.append(sp(30))
    story.append(hr(C['g500'], 2))
    story.append(sp(18))
    story.append(P('MermaOps', 'close'))
    story.append(sp(8))
    story.append(P('Un sistema que percibe, razona, decide y actúa.', 'closesub'))
    story.append(sp(4))
    story.append(Paragraph(
        'No un chatbot. No un dashboard. Un sistema operativo para la gestión de merma alimentaria.',
        ParagraphStyle('c2', fontName='Helvetica-Oblique', fontSize=10,
                       textColor=C['s500'], leading=16, alignment=TA_CENTER)))
    story.append(sp(24))
    story.append(Paragraph(
        'Álvaro Ferrer Muro · TFM 2025-2026<br/>'
        'Módulo: Flujos de Trabajo Agénticos · Mayo 2026',
        ParagraphStyle('ca', fontName='Helvetica', fontSize=9,
                       textColor=C['s500'], leading=16, alignment=TA_CENTER)))

    doc.multiBuild(story, canvasmaker=HFCanvas)
    print(f'PDF generado: {out}')


if __name__ == '__main__':
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'docs', 'modulo_flujos_agenticos.pdf')
    build(out)
