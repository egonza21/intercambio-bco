"""Helpers compartidos por los módulos de figuras.

Acá vive lo que usan todas las páginas: la figura de "sin datos", el orden
canónico de grupos y las funciones que dicen contra qué mes se compara algo.

`mes_comparacion` y `leyenda_comparacion` están juntas y en la base a
propósito: la regla del tablero es que ningún visual que compare meses deje
implícito contra cuál, y una regla que vale para todos no puede vivir dentro
de uno.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import theme
from theme import aplicar_template as _t


VACIO = "sin datos para esta combinación de filtros"


def _sin_datos(msg: str = VACIO) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False,
                       font=dict(size=13, color=theme.INK_MUTED, family=theme.FONT))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _t(fig)


def mes_comparacion(meses, idx_mes: int) -> tuple[int | None, int]:
    """Contra qué mes se compara `idx_mes`, y a cuántos meses de distancia.

    Devuelve (idx_base, distancia); idx_base es None si no hay ningún mes
    anterior en los datos.

    Existe porque el mes anterior puede faltar. Con `idx_mes - 1` a ciegas, si
    la partición no llegó el visual salía vacío o saltaba el punto en
    silencio; acá se cae al mes disponible más cercano y la distancia viaja al
    que llama para que la pueda decir.
    """
    previos = sorted(int(m) for m in set(meses) if m < idx_mes)
    if not previos:
        return None, 0
    return previos[-1], idx_mes - previos[-1]


def _rezago(df: pd.DataFrame) -> int:
    """El rezago que trae el agregado. `data.migracion()` lo deja como columna
    justamente para que los visuales no supongan que es 1."""
    if "rezago" in df.columns and len(df):
        return int(df["rezago"].iloc[0])
    return 1


def leyenda_comparacion(df: pd.DataFrame) -> str:
    """Contra qué mes está comparado lo que se mira, con los meses concretos y
    no con la palabra "anterior".

    Con un solo mes en pantalla nombra los dos. Con varios apilados dice el
    rango y el salto, porque cada fila se comparó contra SU propio mes previo
    y nombrar uno solo sería mentir sobre las demás.
    """
    if df.empty or "idx_mes" not in df.columns:
        return ""
    rez = _rezago(df)
    meses = sorted(int(m) for m in set(df["idx_mes"].dropna()))
    if not meses:
        return ""
    salto = "el mes anterior" if rez == 1 else f"{rez} meses antes"
    if len(meses) == 1:
        return (f"{theme.etiqueta_mes_idx(meses[0])} contra "
                f"{theme.etiqueta_mes_idx(meses[0] - rez)}")
    return (f"{len(meses)} meses acumulados, de "
            f"{theme.etiqueta_mes_idx(meses[0])} a "
            f"{theme.etiqueta_mes_idx(meses[-1])}; cada uno contra {salto}")


def _pie_comparacion(fig: go.Figure, df: pd.DataFrame, y: float = -0.22) -> None:
    """Anota al pie contra qué mes se compara. La regla del tablero es que
    ningún visual que compare meses lo deje implícito."""
    txt = leyenda_comparacion(df)
    if txt:
        fig.add_annotation(
            x=0, y=y, xref="paper", yref="paper", xanchor="left",
            showarrow=False, text=txt,
            font=dict(size=11, color=theme.INK_SOFT, family=theme.FONT))


# ===========================================================================
# PANORAMA
# ===========================================================================

def _grupos_ordenados(valores) -> list[str]:
    """Los grupos presentes, en el orden canónico de theme.GRUPOS_ORDENADOS.

    Se recorre la lista canónica y se filtra a lo presente, en vez de ordenar
    los valores que llegaron: así el resultado NO depende de los datos. Un
    valor desconocido (un grupo nuevo, o uno con espacios que se escapó del
    strip) va al final, visible, en vez de mezclarse en el medio.

    Esto hay que usarlo en los DOS lados: el categoryorder del eje Y el orden
    en que se agregan las trazas. En barras apiladas y áreas, el orden de
    apilado y el de la leyenda los define el orden de las TRAZAS, no el eje;
    poner solo categoryorder deja las G desordenadas igual.
    """
    presentes = {str(v).strip() for v in valores if v is not None}
    canon = [g for g in theme.GRUPOS_ORDENADOS if g in presentes]
    return canon + sorted(presentes - set(canon))


# ===========================================================================
# GUÍA DE LECTURA
# ===========================================================================
# Un bloque con tres partes para cada visual: qué muestra, cómo se lee, y qué
# es normal y qué debería llamar la atención. Una sola función produce el
# HTML, y la app (st.markdown) y el export (Doc.guia) lo pintan tal cual: el
# formato no puede divergir porque no hay dos implementaciones.
#
# Los textos viven al lado de cada figura, en su módulo, registrados en GUIAS
# con registrar_guia(). Pedir una clave que no existe revienta: una guía que
# falta tiene que notarse, no salir en blanco.

@dataclass(frozen=True)
class Guia:
    que: str
    como: str
    normal: str


GUIAS: dict[str, Guia] = {}


def registrar_guia(clave: str, que: str, como: str, normal: str) -> None:
    if clave in GUIAS:
        raise ValueError(f"guía registrada dos veces: {clave}")
    GUIAS[clave] = Guia(que, como, normal)


def guia(clave: str) -> str:
    """El bloque de guía como HTML con estilos en línea, para que se vea igual
    con el CSS de la app y con el del export."""
    g = GUIAS[clave]
    fila = ('<div style="margin:.12rem 0"><span style="font-weight:650;'
            f'color:{theme.INK}">{{t}}</span> {{v}}</div>')
    cuerpo = "".join(fila.format(t=t, v=v) for t, v in (
        ("Qué muestra.", g.que),
        ("Cómo se lee.", g.como),
        ("Qué es normal y qué llama la atención.", g.normal)))
    return (f'<div class="guia" style="border-left:3px solid {theme.BORDER};'
            f'padding:.4rem .9rem;margin:.2rem 0 .9rem;font-size:.8rem;'
            f'line-height:1.5;color:{theme.INK_SOFT};max-width:96ch">'
            f'{cuerpo}</div>')


# ===========================================================================
# BANDA DE LO NORMAL EN LAS SERIES DE TIEMPO
# ===========================================================================
# En una serie de tiempo "lo normal" no se escribe: se dibuja. Una banda con el
# percentil 10 a 90 de la PROPIA serie. Así el rango habitual sale del dato de
# esa serie y no de una frase fija que envejece.
#
# Se calcula SIN el último mes: si entrara, el punto que se quiere juzgar
# ayudaría a definir su propio rango. Con la historia previa, el último punto
# se ve adentro o afuera de la banda de un vistazo.

MIN_PUNTOS_BANDA = 6    # con menos historia, un percentil no es un rango
TEXTO_BANDA = "rango habitual: p10–p90 de la propia serie, sin el último mes"


def rango_historico(y) -> tuple[float, float] | None:
    """(p10, p90) de la serie sin su último punto, o None si no alcanza."""
    v = pd.to_numeric(pd.Series(list(y)), errors="coerce").to_numpy(dtype=float)
    hist = v[:-1]
    hist = hist[np.isfinite(hist)]
    if len(hist) < MIN_PUNTOS_BANDA:
        return None
    p10, p90 = np.percentile(hist, [10, 90])
    return float(p10), float(p90)


def banda_historica(fig: go.Figure, y, color: str) -> bool:
    """Sombrea el rango habitual de una serie. Devuelve si la dibujó."""
    r = rango_historico(y)
    if r is None:
        return False
    p10, p90 = r
    if p90 - p10 <= 0:
        # Serie plana en toda su historia: la banda tendría alto cero.
        fig.add_hline(y=p10, line=dict(color=color, width=6), opacity=0.12,
                      layer="below")
    else:
        fig.add_hrect(y0=p10, y1=p90, fillcolor=color, opacity=0.10,
                      line_width=0, layer="below")
    return True


def leyenda_banda(fig: go.Figure) -> None:
    """Una sola entrada de leyenda que explica el sombreado. Va una vez por
    figura aunque haya una banda por serie."""
    fig.add_scatter(x=[None], y=[None], mode="markers", name=TEXTO_BANDA,
                    marker=dict(symbol="square", size=13, color=theme.INK_MUTED,
                                opacity=0.28),
                    hoverinfo="skip", showlegend=True)
