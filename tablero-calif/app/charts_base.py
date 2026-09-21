"""Helpers compartidos por los módulos de figuras.

Acá vive lo que usan todas las páginas: la figura de "sin datos", el orden
canónico de grupos y las funciones que dicen contra qué mes se compara algo.

`mes_comparacion` y `leyenda_comparacion` están juntas y en la base a
propósito: la regla del tablero es que ningún visual que compare meses deje
implícito contra cuál, y una regla que vale para todos no puede vivir dentro
de uno.
"""
from __future__ import annotations

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
