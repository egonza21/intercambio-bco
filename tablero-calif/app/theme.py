"""Paleta, template de Plotly y CSS. Una sola definición del look.

La paleta no se eligió a ojo: se validó con los checks computables de la guía
de visualización (banda de luminosidad OKLCH, piso de croma, separación bajo
simulación de daltonismo protan/deutan, piso de visión normal y contraste
contra la superficie). Las cifras de cada check están anotadas al lado de cada
grupo de valores.
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Superficies y tinta
# ---------------------------------------------------------------------------
SURFACE = "#fcfcfb"      # superficie del gráfico
PLANE = "#f7f7f5"        # plano de la página
INK = "#0b0b0b"          # tinta primaria
INK_SOFT = "#52514e"     # tinta secundaria
INK_MUTED = "#898781"    # ejes y etiquetas
GRID = "#e8e7e1"         # grilla horizontal, muy tenue
AXIS = "#c3c2b7"         # línea base
BORDER = "rgba(11,11,11,0.10)"

FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'

# ---------------------------------------------------------------------------
# Dimensión de grupo -- espejo de la tabla en CLAUDE.md, "Apertura de G7 y G8"
# ---------------------------------------------------------------------------
# grupo_orden NO viaja en los agregados a propósito (es presentacional, ver
# powerbi/notas_modelo.md). La app lo reconstruye acá con la MISMA aritmética
# que sql/_fragmentos/cte_productos.sql: decena = dígito del grupo, unidad =
# apertura (B=1, M=2, A=3). Si cambia la convención, cambia en los dos lados.
DIM_GRUPO: list[tuple[str, str, int]] = [
    ("G1", "G1", 10), ("G2", "G2", 20), ("G3", "G3", 30), ("G4", "G4", 40),
    ("G5", "G5", 50), ("G6", "G6", 60),
    ("G7", "G7", 70), ("G7_B", "G7", 71), ("G7_M", "G7", 72), ("G7_A", "G7", 73),
    ("G8", "G8", 80), ("G8_B", "G8", 81), ("G8_M", "G8", 82), ("G8_A", "G8", 83),
]
GRUPO_ORDEN = {g: o for g, _, o in DIM_GRUPO}
GRUPO_BASE = {g: b for g, b, _ in DIM_GRUPO}
GRUPOS_ORDENADOS = [g for g, _, _ in sorted(DIM_GRUPO, key=lambda r: r[2])]
GRUPOS_BASE_ORDENADOS = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]

_ORDEN_MIN, _ORDEN_MAX = 10, 83

# ---------------------------------------------------------------------------
# Rampa ordinal de riesgo -- un solo tono, claro (G1) a oscuro (G8)
# ---------------------------------------------------------------------------
# G1-G8 es una escala ORDINAL: la lectura correcta es de gradiente, así que va
# en un solo tono y nunca en colores categóricos. Los paradas son la rampa azul
# de la guía, extendida un paso hacia el extremo oscuro (#082852): la rampa
# documentada llega hasta L=0.338 y ocho niveles con separación mínima de
# dL=0.06 necesitan un span de 0.42, que no entraba por 0.006 una vez
# redondeado a sRGB.
#
# Validado como rampa ordinal en superficie clara:
#   Lightness monotone  PASS   Adjacent dL       PASS (todos >= 0.06)
#   Light-end contrast  PASS   (#86b6ef, 2.06:1, sobre el piso de 2:1)
#   Single hue          PASS   (spread 4°)
_RAMPA_STOPS = [
    (0.764, "#86b6ef"), (0.717, "#6da7ec"), (0.671, "#5598e7"), (0.622, "#3987e5"),
    (0.575, "#2a78d6"), (0.527, "#256abf"), (0.480, "#1c5cab"), (0.433, "#184f95"),
    (0.385, "#104281"), (0.338, "#0d366b"), (0.281, "#082852"),
]


def _hex_a_lin(h: str) -> list[float]:
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def _oklab(h: str) -> tuple[float, float, float]:
    r, g, b = _hex_a_lin(h)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _oklab_a_hex(L: float, a: float, b: float) -> str:
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
           -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
           -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)
    out = []
    for c in rgb:
        c = min(1.0, max(0.0, c))
        c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        out.append(round(c * 255))
    return "#%02x%02x%02x" % tuple(out)


def _rampa(t: float) -> str:
    """t en [0,1]: 0 = extremo claro (menor riesgo), 1 = oscuro (mayor)."""
    t = min(1.0, max(0.0, t))
    objetivo = _RAMPA_STOPS[0][0] + t * (_RAMPA_STOPS[-1][0] - _RAMPA_STOPS[0][0])
    for i in range(len(_RAMPA_STOPS) - 1):
        l0, h0 = _RAMPA_STOPS[i]
        l1, h1 = _RAMPA_STOPS[i + 1]
        if l1 - 1e-9 <= objetivo <= l0 + 1e-9:
            f = 0.0 if l0 == l1 else (l0 - objetivo) / (l0 - l1)
            _, a0, b0 = _oklab(h0)
            _, a1, b1 = _oklab(h1)
            return _oklab_a_hex(objetivo, a0 + f * (a1 - a0), b0 + f * (b1 - b0))
    return _RAMPA_STOPS[-1][1]


def color_grupo(grupo: str) -> str:
    """Color de un grupo por su posición ordinal. Las aperturas de sufi caen en
    tonos contiguos dentro del tramo de su grupo base, por construcción."""
    orden = GRUPO_ORDEN.get(grupo)
    if orden is None:
        return INK_MUTED
    return _rampa((orden - _ORDEN_MIN) / (_ORDEN_MAX - _ORDEN_MIN))


COLOR_GRUPO = {g: color_grupo(g) for g in GRUPOS_ORDENADOS}
COLOR_GRUPO_BASE = {g: color_grupo(g) for g in GRUPOS_BASE_ORDENADOS}

# Escala continua para heatmaps de magnitud (segmento x grupo, cobertura).
ESCALA_SECUENCIAL = [[i / 10, _rampa(i / 10)] for i in range(11)]

# ---------------------------------------------------------------------------
# Series categóricas -- máximo 4, en orden fijo, nunca cicladas
# ---------------------------------------------------------------------------
# Validado como categórica sobre pares adyacentes (líneas) en superficie clara:
#   Lightness band PASS · Chroma floor PASS
#   CVD separation PASS  (peor par dE 9.1 protan, sobre el objetivo de 8)
#   Normal-vision  PASS  (peor par dE 22.9, sobre el piso de 15)
#   Contraste      WARN  (#1baf7a 2.74:1 y #eda100 2.11:1, bajo 3:1)
# El WARN de contraste obliga a encoding secundario, que acá está de dos
# formas: el estilo de línea distinto por serie y la tabla descargable.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SERIES_DASH = ["solid", "dash", "dot", "longdash"]

# ---------------------------------------------------------------------------
# Divergente para la matriz de migración
# ---------------------------------------------------------------------------
# Centrada en la diagonal: mejora en azul, deterioro en rojo, estabilidad en
# gris neutro. El midpoint es gris y no un tono, para que "sin cambio" lea como
# ausencia de señal.
DIV_MEJORA = "#2a78d6"    # contraste 4.30:1
DIV_NEUTRO = "#f0efec"    # gris neutro
DIV_DETERIORO = "#d03b3b"  # contraste 4.68:1
ESCALA_DIVERGENTE = [
    [0.0, "#0d366b"], [0.25, DIV_MEJORA], [0.45, "#dce9f8"],
    [0.5, DIV_NEUTRO],
    [0.55, "#f7ddd9"], [0.75, DIV_DETERIORO], [1.0, "#7d1f1f"],
]

# Categorías fuera de la escala de riesgo (no son un grupo: son población).
GRIS_FUERA_ESCALA = "#898781"
CATEGORIAS_FUERA_ESCALA = {
    "entrada", "salida", "ganancia_elegibilidad", "perdida_elegibilidad",
    "ganancia_pd", "perdida_pd",
}

# Estados (nunca reutilizados como color de serie).
ESTADO_OK = "#0ca30c"
ESTADO_ALERTA = "#fab219"
ESTADO_CRITICO = "#d03b3b"

# ---------------------------------------------------------------------------
# Template de Plotly -- se aplica a TODA figura, en la app y en el export
# ---------------------------------------------------------------------------
_EJE = dict(
    showgrid=False, zeroline=False, showline=True, linecolor=AXIS, linewidth=1,
    ticks="outside", ticklen=4, tickcolor=AXIS,
    tickfont=dict(size=12, color=INK_MUTED, family=FONT),
    title=dict(font=dict(size=13, color=INK_SOFT, family=FONT), standoff=12),
    automargin=True,
)

TEMPLATE = dict(
    layout=dict(
        font=dict(family=FONT, size=13, color=INK_SOFT),
        paper_bgcolor=SURFACE,
        plot_bgcolor="rgba(0,0,0,0)",   # sin fondo de área de trazado
        colorway=SERIES,
        # Sin título dentro de la figura: el título lo pone el layout de la app
        # (y el <h2> del export), para que no se dupliquen.
        title=dict(text=""),
        margin=dict(l=72, r=32, t=56, b=64),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(size=12, color=INK_SOFT, family=FONT),
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
            title=dict(text=""),
        ),
        hoverlabel=dict(
            bgcolor=SURFACE, bordercolor=AXIS, font=dict(size=12, family=FONT, color=INK)
        ),
        # Grilla horizontal muy tenue, ninguna vertical.
        xaxis={**_EJE},
        yaxis={**_EJE, "showgrid": True, "gridcolor": GRID, "gridwidth": 1, "showline": False},
        colorscale=dict(sequential=ESCALA_SECUENCIAL, diverging=ESCALA_DIVERGENTE),
    )
)


def aplicar_template(fig, *, unified: bool = False):
    """Aplica el template. `unified` activa el hover de crosshair para series
    de tiempo (una sola caja con todas las series del mismo x)."""
    fig.update_layout(template=TEMPLATE)
    if unified:
        fig.update_layout(hovermode="x unified")
    return fig


# ---------------------------------------------------------------------------
# Formato -- ningún gráfico debe necesitar explicación
# ---------------------------------------------------------------------------
_MESES = ["ene", "feb", "mar", "abr", "may", "jun",
          "jul", "ago", "sep", "oct", "nov", "dic"]


def idx_mes(anio: int, mes: int) -> int:
    """Índice de mes corrido. Ver CLAUDE.md: year*12+month, no YYYYMM, porque
    el índice tiene que soportar aritmética (restar {REZAGO})."""
    return int(anio) * 12 + int(mes)


def desde_idx(idx: int) -> tuple[int, int]:
    idx = int(idx)
    anio = math.floor((idx - 1) / 12)
    return anio, idx - 12 * anio


def etiqueta_mes(anio: int, mes: int) -> str:
    """'ago 2026', nunca '2026-08'."""
    return f"{_MESES[int(mes) - 1]} {int(anio)}"


def etiqueta_mes_idx(idx: int) -> str:
    return etiqueta_mes(*desde_idx(idx))


def fmt_miles(n) -> str:
    """Separador de miles con punto, como se escribe en español."""
    if n is None:
        return "--"
    return f"{int(round(float(n))):,}".replace(",", ".")


def fmt_pct(x, decimales: int = 1) -> str:
    if x is None:
        return "--"
    return f"{float(x) * 100:.{decimales}f}%".replace(".", ",")


def fmt_pd(x) -> str:
    """PD con suficientes decimales para que no colapse a 0,00."""
    if x is None:
        return "--"
    x = float(x)
    return (f"{x:,.4f}" if x < 1 else f"{x:,.1f}").replace(",", "@").replace(".", ",").replace("@", ".")


# ---------------------------------------------------------------------------
# CSS de la app
# ---------------------------------------------------------------------------
CSS = f"""
<style>
  /* Oculta el menú y el footer de Streamlit, y recupera el espacio superior
     que el layout por defecto desperdicia. */
  #MainMenu, footer, header [data-testid="stStatusWidget"] {{ visibility: hidden; }}
  .block-container {{ padding-top: 2.2rem; padding-bottom: 3rem;
                      max-width: 1500px; }}

  html, body, [class*="css"] {{ font-family: {FONT}; }}
  .stApp {{ background: {PLANE}; }}

  h1 {{ font-size: 1.55rem !important; font-weight: 650; color: {INK};
       letter-spacing: -0.01em; margin-bottom: .15rem; }}
  h2 {{ font-size: 1.05rem !important; font-weight: 620; color: {INK};
       margin: 2.1rem 0 .2rem 0; letter-spacing: -0.005em; }}
  h3 {{ font-size: .92rem !important; font-weight: 600; color: {INK_SOFT};
       margin: 1.3rem 0 .2rem 0; }}
  .sub {{ color: {INK_SOFT}; font-size: .86rem; margin: 0 0 .3rem 0;
          line-height: 1.45; max-width: 76ch; }}
  .nota {{ color: {INK_MUTED}; font-size: .78rem; margin: .35rem 0 0 0;
           line-height: 1.5; max-width: 88ch; }}

  /* KPIs como tarjetas con borde sutil, no el st.metric plano. */
  div[data-testid="stMetric"] {{
      background: {SURFACE};
      border: 1px solid {BORDER};
      border-radius: 10px;
      padding: .85rem 1rem .8rem 1rem;
      box-shadow: 0 1px 2px rgba(11,11,11,0.04);
  }}
  div[data-testid="stMetricLabel"] p {{
      font-size: .76rem !important; color: {INK_MUTED} !important;
      font-weight: 550; letter-spacing: .02em; text-transform: uppercase;
  }}
  div[data-testid="stMetricValue"] {{
      font-size: 1.6rem !important; font-weight: 600; color: {INK};
      letter-spacing: -0.02em;
  }}
  div[data-testid="stMetricDelta"] {{ font-size: .8rem !important; }}

  /* Barra lateral */
  section[data-testid="stSidebar"] {{
      background: {SURFACE}; border-right: 1px solid {BORDER};
  }}
  section[data-testid="stSidebar"] .block-container {{ padding-top: 1.6rem; }}
  section[data-testid="stSidebar"] h2 {{
      font-size: .74rem !important; text-transform: uppercase;
      letter-spacing: .06em; color: {INK_MUTED}; font-weight: 600;
      margin: 1.5rem 0 .4rem 0;
  }}

  /* Contenedor de gráfico */
  div[data-testid="stPlotlyChart"] {{
      background: {SURFACE}; border: 1px solid {BORDER};
      border-radius: 10px; padding: .5rem .35rem .1rem .35rem;
  }}

  hr {{ border: none; border-top: 1px solid {BORDER}; margin: 2.2rem 0 0 0; }}
  div[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 8px; }}
</style>
"""
