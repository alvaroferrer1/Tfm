"""
Genera MermaOps_Hero.png — imagen hero para GitHub README.
2400 x 1260 px, fondo oscuro, diseño limpio tipo Linear/Notion.
"""
from PIL import Image, ImageDraw, ImageFont
import math, os

W, H = 2400, 1260
OUT = os.path.join(os.path.dirname(__file__), "..", "MermaOps_Hero.png")

# ── Colores ────────────────────────────────────────────────────────────────────
BG       = (5,   5,  15)
BG2      = (10,  4,  30)
GREEN    = (0,  200, 150)
GREEN_DIM= (0,  120,  90)
PURPLE   = (124, 58, 237)
BLUE     = (42, 171, 238)
RED      = (239,  68,  68)
ORANGE   = (245, 158,  11)
WHITE    = (240, 240, 240)
GREY     = (107, 114, 128)
DARK     = (20,  20,  35)
CARD_BG  = (15,  15,  28)

def rgba(color, a):
    return (*color, a)

img = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(img, "RGBA")

# ── Fondo degradado ────────────────────────────────────────────────────────────
for y in range(H):
    t = y / H
    r = int(BG[0] + (BG2[0]-BG[0]) * t)
    g = int(BG[1] + (BG2[1]-BG[1]) * t)
    b = int(BG[2] + (BG2[2]-BG[2]) * t)
    draw.line([(0, y), (W, y)], fill=(r, g, b))

# Glow verde arriba-izquierda
for i in range(300, 0, -10):
    alpha = int(12 * (1 - i/300))
    draw.ellipse((-i, -i, i*2, i*2), fill=(*GREEN, alpha))

# Glow púrpura arriba-derecha
for i in range(400, 0, -10):
    alpha = int(10 * (1 - i/400))
    draw.ellipse((W-i*2, -i, W+i, i*2), fill=(*PURPLE, alpha))

# ── Fuentes ────────────────────────────────────────────────────────────────────
def font(size, bold=False):
    faces = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    bold_faces = [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]
    for f in (bold_faces if bold else faces):
        try: return ImageFont.truetype(f, size)
        except: pass
    return ImageFont.load_default()

f_giant  = font(110, bold=True)
f_big    = font(48, bold=True)
f_med    = font(30)
f_small  = font(22)
f_xs     = font(18)
f_mono   = font(20)

# ── Helpers ────────────────────────────────────────────────────────────────────
def text(x, y, txt, fnt, color=WHITE, anchor="lt"):
    draw.text((x, y), txt, font=fnt, fill=color, anchor=anchor)

def pill(x, y, w, h, color, alpha=40, radius=16):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=radius,
                            fill=(*color, alpha), outline=(*color, 80), width=1)

def card(x, y, w, h, radius=20):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=radius,
                            fill=(*CARD_BG, 220), outline=(255,255,255,12), width=1)

def dot(x, y, r, color):
    draw.ellipse([x-r, y-r, x+r, y+r], fill=color)

def line_h(x1, y, x2, color=GREY, alpha=30):
    draw.line([(x1,y),(x2,y)], fill=(*color,alpha), width=1)

# ═══════════════════════════════════════════════════════════════════════════════
#  SECCIÓN IZQUIERDA — Título y tagline
# ═══════════════════════════════════════════════════════════════════════════════
# Badge "TFM 2026"
pill(80, 80, 200, 44, GREEN, alpha=25, radius=22)
text(180, 102, "TFM · 2026", font(18, bold=True), GREEN, anchor="mm")

# Logo
text(80, 152, "MermaOps", f_giant, WHITE)

# Tagline
text(80, 290, "Sistema multi-agente de IA para reducir la merma", font(32), GREY)
text(80, 336, "alimentaria en supermercados españoles", font(32), GREY)

# Separador
draw.rectangle([80, 405, 80+6, 405+80], fill=GREEN)

# Descripción
text(110, 412, "Kuine (Opus 4.7) analiza, decide y actúa.", font(28), WHITE)
text(110, 450, "Chuwi (Sonnet 4.6) habla con el encargado.", font(28), WHITE)
text(110, 488, "Sin hardware adicional. Sin comandos.", font(28), GREY)

# Stack pills
sx, sy = 80, 570
for label, color in [
    ("Claude API", GREEN),
    ("FastAPI", BLUE),
    ("Flutter", PURPLE),
    ("Supabase", (34,197,94)),
    ("Telegram", BLUE),
]:
    tw = draw.textlength(label, font=f_xs) + 32
    pill(sx, sy, int(tw), 38, color, alpha=18, radius=19)
    text(sx + int(tw)//2, sy+19, label, f_xs, color, anchor="mm")
    sx += int(tw) + 12

# ═══════════════════════════════════════════════════════════════════════════════
#  SECCIÓN CENTRO — Arquitectura animada (estática en imagen)
# ═══════════════════════════════════════════════════════════════════════════════
cx = 950

# Línea separadora izquierda
draw.line([(cx-60, 80), (cx-60, H-80)], fill=(255,255,255,8), width=1)

# Título sección
text(cx, 100, "Arquitectura del sistema", font(26), GREY)

# KUINE box
kx, ky = cx, 155
kw, kh = 420, 110
draw.rounded_rectangle([kx, ky, kx+kw, ky+kh], radius=18,
                        fill=(*PURPLE, 22), outline=(*PURPLE, 70), width=2)
# Glow
for i in range(5):
    alpha = 8 - i
    draw.rounded_rectangle([kx-i, ky-i, kx+kw+i, ky+kh+i],
                            radius=18+i, outline=(*PURPLE, alpha), width=1)
text(kx+kw//2, ky+28, "⚡  KUINE", font(32, bold=True), PURPLE, anchor="mt")
text(kx+kw//2, ky+68, "Orquestador · Opus 4.7 · 25 tools", font(19), (*PURPLE, 180), anchor="mt")
text(kx+kw//2, ky+92, "adaptive thinking · hasta 20 iteraciones", font(17), (*PURPLE, 120), anchor="mt")

# Flechas hacia subagentes
arrow_y = ky + kh + 10
for i, xpos in enumerate([kx+50, kx+160, kx+280, kx+360]):
    draw.line([(kx+kw//2, arrow_y), (xpos+60, arrow_y+50)],
              fill=(*PURPLE, 40), width=1)

# Subagentes grid
agents = [
    ("Evaluador", "Sonnet 4.6", BLUE),
    ("Validador", "Sonnet 4.6", ORANGE),
    ("Predictor", "Sonnet 4.6", GREEN),
    ("Reportero", "Opus 4.7", PURPLE),
    ("Visión", "Sonnet 4.6", BLUE),
    ("Precio", "Haiku 4.5", GREEN),
    ("Stock", "Haiku 4.5", GREEN),
]
cols = 4
ax_start = kx
ay = ky + kh + 50
aw, ah = 98, 68
gap = 8
for i, (name, model, color) in enumerate(agents):
    col = i % cols
    row = i // cols
    ax = ax_start + col * (aw + gap)
    aay = ay + row * (ah + gap)
    draw.rounded_rectangle([ax, aay, ax+aw, aay+ah], radius=10,
                            fill=(*color, 10), outline=(*color, 40), width=1)
    text(ax+aw//2, aay+18, name, font(14, bold=True), color, anchor="mt")
    text(ax+aw//2, aay+40, model, font(11), (*color, 140), anchor="mt")

# Flechas hacia CHUWI
chuwi_y = ay + 2*(ah+gap) + 30
mid_agents_y = ay + (ah+gap) + ah//2
draw.line([(kx+kw//2, mid_agents_y+ah//2), (kx+kw//2, chuwi_y)],
          fill=(*BLUE, 40), width=1)

# CHUWI box
cw_w = 420
draw.rounded_rectangle([kx, chuwi_y, kx+cw_w, chuwi_y+100], radius=18,
                        fill=(*BLUE, 15), outline=(*BLUE, 60), width=2)
for i in range(4):
    draw.rounded_rectangle([kx-i, chuwi_y-i, kx+cw_w+i, chuwi_y+100+i],
                            radius=18+i, outline=(*BLUE, 6-i), width=1)
text(kx+cw_w//2, chuwi_y+20, "💬  CHUWI", font(30, bold=True), BLUE, anchor="mt")
text(kx+cw_w//2, chuwi_y+58, "Agente Telegram · Sonnet 4.6 · streaming", font(19), (*BLUE, 170), anchor="mt")
text(kx+cw_w//2, chuwi_y+82, "@ChuwiMermaOpsBot · memoria episódica", font(16), (*BLUE, 110), anchor="mt")

# ═══════════════════════════════════════════════════════════════════════════════
#  SECCIÓN DERECHA — Métricas y features
# ═══════════════════════════════════════════════════════════════════════════════
rx = 1520
draw.line([(rx-40, 80), (rx-40, H-80)], fill=(255,255,255,8), width=1)

text(rx, 100, "Evaluación cuantitativa", font(26), GREY)

metrics = [
    ("432",  "tests · 100% passing · < 1.5 s", GREEN),
    ("100%", "precisión · +83 pp vs baseline", GREEN),
    ("23/23","ataques adversariales bloqueados", PURPLE),
    ("11",   "agentes especializados (Opus·Sonnet·Haiku)", PURPLE),
    ("7",    "jobs autónomos · 24 h / 7 días", BLUE),
]
my = 155
for num, desc, color in metrics:
    nw = int(draw.textlength(num, font=font(52, bold=True)))
    draw.text((rx, my), num, font=font(52, bold=True), fill=color)
    # Descripción debajo del número, no al lado
    text(rx + nw + 14, my + 10, desc, font(20), GREY)
    line_h(rx, my+68, W-80, GREY, alpha=12)
    my += 90

# Features destacados
my += 14
text(rx, my, "Técnicas de IA implementadas", font(22, bold=True), WHITE)
my += 38

features = [
    (GREEN,  "Extended + adaptive thinking en Kuine"),
    (PURPLE, "Multi-agent consensus — 3 instancias paralelas"),
    (BLUE,   "Streaming progresivo carácter a carácter"),
    (GREEN,  "Prompt caching — 90% ahorro en tokens"),
    (ORANGE, "Adversarial robustness · FEFO enforcement"),
    (PURPLE, "Intent classification — 0 tokens adicionales"),
    (BLUE,   "Observabilidad OTEL · Langfuse integrado"),
]
for color, txt in features:
    dot(rx+8, my+10, 4, color)
    text(rx+22, my, txt, font(19), WHITE)
    my += 32

# Footer con GitHub
my = H - 80
line_h(80, my-20, W-80, GREY, alpha=20)
text(80, my, "github.com/alvaroferrermarg/MermaOps", f_mono, GREY)
text(W//2, my, "Álvaro Ferrer Margarit · Máster IA Generativa · Evolve Business School 2026", f_mono, GREY, anchor="lt")
text(W-80, my, "Defensa 5 junio 2026", f_mono, GREEN, anchor="rt")

# ── Guardar ────────────────────────────────────────────────────────────────────
img.save(OUT, "PNG", dpi=(144, 144))
print(f"Hero guardado: {OUT}  ({W}x{H}px)")
