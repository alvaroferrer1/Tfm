"""
pdf_generator.py — Genera PDFs profesionales de briefs e informes con fpdf2.

Uso:
    pdf_bytes = generate_brief_pdf(brief_text, date_str, critical_count, ...)
    # Devuelve bytes — enviar como response HTTP o adjunto Telegram.
"""
from __future__ import annotations
import io
from datetime import date as _date

import unicodedata
from fpdf import FPDF, XPos, YPos


def _safe(text: str) -> str:
    """Convierte texto a latin-1 compatible para fpdf2 con Helvetica."""
    text = str(text)
    # Reemplazos explícitos antes de normalizar
    replacements = {
        "€": "EUR", "°": "o", "·": "-", "—": "-", "–": "-",
        "—": "-", "–": "-", "·": "-",
        "🔴": "[CRITICO]", "🟡": "[ALTO]", "📋": "[>>]",
        "📊": "[>>]", "📈": "[>>]", "✅": "[OK]", "❌": "[X]",
        "⚠": "[!]", "🚨": "[!!]",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    # Normalizar acentos compuestos: á→a, é→e, etc.
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if ord(c) < 128)

# Colores corporativos MermaOps
_GREEN_DARK = (4, 80, 60)
_GREEN_MID = (6, 148, 100)
_GREEN_LIGHT = (209, 250, 229)
_RED = (220, 38, 38)
_AMBER = (217, 119, 6)
_BLUE = (37, 99, 235)
_GREY_LIGHT = (245, 247, 250)
_GREY_BORDER = (229, 231, 235)
_TEXT_DARK = (17, 24, 39)
_TEXT_MID = (75, 85, 99)
_WHITE = (255, 255, 255)


class _MermaPDF(FPDF):
    _store_name: str = "Super Martínez"

    def header(self) -> None:
        self.set_fill_color(*_GREEN_DARK)
        self.rect(0, 0, 210, 18, style="F")
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*_WHITE)
        self.set_xy(10, 4)
        self.cell(120, 10, "MermaOps", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(180, 240, 210)
        self.set_xy(130, 6)
        self.cell(70, 7, "Sistema multi-agente de merma alimentaria",
                  align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.ln(14)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_fill_color(*_GREY_LIGHT)
        self.rect(0, self.get_y(), 210, 14, style="F")
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*_TEXT_MID)
        self.cell(95, 10, f"Generado por Kuine - {_date.today().isoformat()}", align="L")
        self.cell(15, 10, f"Pag. {self.page_no()}", align="C")
        self.cell(95, 10, _safe(self._store_name), align="R")

    def section_header(self, title: str, color: tuple = _GREEN_DARK) -> None:
        self.set_fill_color(*color)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 8, _safe(f"  {title}"), fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*_TEXT_DARK)
        self.ln(2)

    def kpi_row(self, kpis: list[tuple[str, str, tuple]]) -> None:
        """Fila de KPIs: lista de (label, value, color)."""
        w = 190 / len(kpis)
        x_start = self.get_x()
        y_start = self.get_y()
        for idx, (label, value, color) in enumerate(kpis):
            self.set_fill_color(*_GREY_LIGHT)
            self.rect(self.get_x(), y_start, w - 2, 22, style="F")
            self.set_xy(self.get_x() + 3, y_start + 2)
            self.set_font("Helvetica", "B", 14)
            self.set_text_color(*color)
            self.cell(w - 8, 8, _safe(str(value)), new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.set_xy(x_start + idx * w + 3, y_start + 12)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*_TEXT_MID)
            self.cell(w - 8, 6, _safe(label))
            self.set_xy(x_start + (idx + 1) * w, y_start)
        self.set_xy(x_start, y_start + 24)
        self.ln(2)

    def body_text(self, text: str) -> None:
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*_TEXT_DARK)
        for line in text.split("\n"):
            stripped = _safe(line.strip())
            if not stripped:
                self.ln(3)
                continue
            if stripped.isupper() or stripped.startswith("CRITICO") or stripped.startswith("ACCION"):
                self.set_font("Helvetica", "B", 10)
            else:
                self.set_font("Helvetica", "", 10)
            self.multi_cell(0, 5, stripped, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def product_row(
        self, name: str, pasillo: str, action: str,
        days_left, score: int, level: str = "CRITICO"
    ) -> None:
        color = _RED if "CRIT" in level.upper() else (_AMBER if level.upper() == "ALTO" else _BLUE)
        self.set_fill_color(*color)
        self.rect(self.get_x(), self.get_y(), 3, 12, style="F")
        x = self.get_x() + 5
        y = self.get_y()
        self.set_xy(x, y)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*_TEXT_DARK)
        self.cell(80, 6, _safe(name[:35]), new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*_TEXT_MID)
        self.cell(30, 6, f"Pasillo {_safe(pasillo)}", new_x=XPos.RIGHT, new_y=YPos.TOP)
        days_str = "HOY" if days_left == 0 else (f"{days_left}d" if days_left is not None else "?")
        self.cell(25, 6, days_str, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_fill_color(*color)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 8)
        self.cell(30, 6, _safe(action[:12]).upper(), fill=True, align="C",
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_fill_color(*_GREY_LIGHT)
        self.set_text_color(*_TEXT_MID)
        self.set_font("Helvetica", "", 8)
        self.cell(20, 6, f"{score}/100", fill=True, align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)


def _make_pdf(store_name: str = "Super Martínez") -> _MermaPDF:
    pdf = _MermaPDF()
    pdf._store_name = store_name
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(10, 22, 10)
    return pdf


# ── Brief diario ──────────────────────────────────────────────────────────────

def generate_brief_pdf(
    brief_text: str,
    brief_date: str = "",
    critical_count: int = 0,
    high_count: int = 0,
    value_at_risk: float = 0.0,
    actions_count: int = 0,
    route_minutes: int = 0,
    store_name: str = "Super Martínez",
    critical_actions: list[dict] | None = None,
    high_actions: list[dict] | None = None,
) -> bytes:
    pdf = _make_pdf(store_name)
    pdf.add_page()

    fecha = brief_date or _date.today().isoformat()

    # Title block
    pdf.set_fill_color(*_GREEN_DARK)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 14, f"BRIEF DE APERTURA", fill=True, align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_fill_color(*_GREEN_MID)
    pdf.cell(0, 8, _safe(f"{store_name}  |  {fecha}"), fill=True, align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    # KPIs
    sem_label = "ALERTA" if critical_count >= 3 else "NORMAL"
    sem_color = _RED if critical_count >= 3 else (_AMBER if critical_count >= 1 else _GREEN_MID)
    pdf.kpi_row([
        ("Semáforo", sem_label, sem_color),
        ("Críticos", str(critical_count), _RED),
        ("Altos", str(high_count), _AMBER),
        ("Acciones", str(actions_count), _BLUE),
        ("En riesgo", f"{value_at_risk:.0f}€", _GREEN_DARK),
        ("Ruta", f"{route_minutes}min", _TEXT_MID),
    ])

    # Critical products table
    if critical_actions:
        from datetime import date as dt
        pdf.section_header("🔴  PRODUCTOS CRÍTICOS — acción inmediata requerida", _RED)
        for a in critical_actions[:10]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            name = p.get("name", "Producto")
            pasillo = str(p.get("pasillo", "?"))
            action_type = a.get("action_type", "revisar")
            score = a.get("priority_score", 0)
            exp = b.get("expiry_date", "")
            try:
                days_left = (dt.fromisoformat(exp) - dt.today()).days if exp else None
            except Exception:
                days_left = None
            pdf.product_row(name, pasillo, action_type, days_left, score, "CRÍTICO")
        pdf.ln(4)

    if high_actions:
        from datetime import date as dt
        pdf.section_header("🟡  PRODUCTOS DE ATENCIÓN — antes del mediodía", _AMBER)
        for a in high_actions[:8]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            name = p.get("name", "Producto")
            pasillo = str(p.get("pasillo", "?"))
            action_type = a.get("action_type", "revisar")
            score = a.get("priority_score", 0)
            exp = b.get("expiry_date", "")
            try:
                days_left = (dt.fromisoformat(exp) - dt.today()).days if exp else None
            except Exception:
                days_left = None
            pdf.product_row(name, pasillo, action_type, days_left, score, "ALTO")
        pdf.ln(4)

    # Brief text body
    pdf.section_header("📋  ANÁLISIS DE KUINE", _GREEN_DARK)
    pdf.body_text(brief_text)

    # Footer note
    pdf.ln(6)
    pdf.set_fill_color(*_GREEN_LIGHT)
    pdf.set_text_color(*_GREEN_DARK)
    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(0, 5,
        "Este brief ha sido generado automáticamente por Kuine (MermaOps) "
        "usando análisis de IA sobre el inventario actual. "
        "Las decisiones finales son responsabilidad del encargado.",
        fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


# ── Informe semanal ───────────────────────────────────────────────────────────

def generate_weekly_pdf(
    report_text: str,
    week_start: str = "",
    merma_eur: float = 0.0,
    merma_qty: int = 0,
    merma_evitada_eur: float = 0.0,
    donated_qty: int = 0,
    donated_value: float = 0.0,
    store_name: str = "Super Martínez",
) -> bytes:
    pdf = _make_pdf(store_name)
    pdf.add_page()

    # Title
    pdf.set_fill_color(*_BLUE)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 14, "INFORME SEMANAL DE MERMA", fill=True, align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_fill_color(37, 120, 235)
    week_label = f"Semana del {week_start}" if week_start else f"Semana - {_date.today().isoformat()}"
    pdf.cell(0, 8, _safe(f"{store_name}  |  {week_label}"), fill=True, align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    roi = round(merma_evitada_eur / merma_eur, 1) if merma_eur > 0 else 0

    pdf.kpi_row([
        ("Merma real", f"{merma_eur:.2f}€", _RED),
        ("Merma evitada", f"{merma_evitada_eur:.2f}€", _GREEN_MID),
        ("ROI sistema", f"{roi}x", _BLUE),
        ("Unidades merma", str(merma_qty), _AMBER),
        ("Donado", f"{donated_value:.2f}€", _GREEN_DARK),
        ("Uds donadas", str(donated_qty), _GREEN_MID),
    ])

    pdf.section_header("📊  ANÁLISIS SEMANAL — Kuine", _BLUE)
    pdf.body_text(report_text)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


# ── Informe mensual ───────────────────────────────────────────────────────────

def generate_monthly_pdf(
    report_text: str,
    month: str = "",
    merma_eur: float = 0.0,
    merma_evitada_eur: float = 0.0,
    donated_value: float = 0.0,
    store_name: str = "Super Martínez",
) -> bytes:
    pdf = _make_pdf(store_name)
    pdf.add_page()

    # Title
    pdf.set_fill_color(109, 40, 217)  # purple
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 14, "INFORME MENSUAL PARA EL PROPIETARIO", fill=True, align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_fill_color(130, 60, 240)
    month_label = month or _date.today().strftime("%B %Y")
    pdf.cell(0, 8, _safe(f"{store_name}  |  {month_label}"), fill=True, align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    roi_pct = round(merma_evitada_eur / (merma_eur + merma_evitada_eur) * 100, 1) \
        if (merma_eur + merma_evitada_eur) > 0 else 0

    pdf.kpi_row([
        ("Merma real", f"{merma_eur:.2f}€", _RED),
        ("Merma evitada", f"{merma_evitada_eur:.2f}€", _GREEN_MID),
        ("% recuperado", f"{roi_pct}%", (109, 40, 217)),
        ("Valor donado", f"{donated_value:.2f}€", _GREEN_DARK),
    ])

    pdf.section_header("📈  ANÁLISIS MENSUAL — Kuine", (109, 40, 217))
    pdf.body_text(report_text)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
