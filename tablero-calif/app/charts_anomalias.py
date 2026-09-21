"""Figuras de la página de anomalías: qué se movió este mes.

Incluye la matriz segmento × producto (que Panorama también usa) y el puente
de la base, porque los tres responden la misma pregunta con distinto grano:
qué cambió respecto del mes anterior y dónde.

NO es un semáforo. Con 96 celdas moviéndose cada mes por razones normales, un
panel de alertas binarias se vuelve ruido y deja de mirarse; esto es un
RANKING de lo que más se movió, que siempre muestra sus primeras filas aunque
ninguna sea grave.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import theme
from theme import aplicar_template as _t
from charts_base import _sin_datos, mes_comparacion


# ===========================================================================
# MATRIZ SEGMENTO x PRODUCTO
# ===========================================================================

MODOS_MATRIZ = {
    "cantidad": "Clientes calificados",
    "cobertura": "% sobre la base del segmento",
    "variacion": "Variación contra el mes anterior",
}


def _pivote_cobertura(df: pd.DataFrame, segs: list[str],
                      prods: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cubiertos y base sobre la grilla segs x prods.

    Recibe los dos ejes POR PARÁMETRO. Antes era una cerradura dentro de
    matriz_segmento_producto que capturaba `segs` y `prods` del scope de
    afuera, y ese patrón es justo el que hace imposible ver de un vistazo si
    lo que se pivota está alineado con lo que se dibuja.
    """
    g = df.groupby(["segmento", "producto"], as_index=False)[
        ["cubiertos", "clientes"]].sum()
    g["segmento"] = g["segmento"].map(theme._cod)
    cnt = (g.pivot(index="segmento", columns="producto", values="cubiertos")
           .reindex(index=segs, columns=prods))
    base = (g.pivot(index="segmento", columns="producto", values="clientes")
            .reindex(index=segs, columns=prods))
    return cnt, base


def matriz_segmento_producto(cob: pd.DataFrame, idx_mes: int,
                             modo: str = "cantidad") -> go.Figure:
    """Segmentos (por valor de negocio) x productos (orden canónico).

    Los tres modos NO son redundantes, y la diferencia importa: si un mes
    desaparecen filas enteras en vez de quedar con grupo nulo, la COBERTURA no
    se mueve -- bajan numerador y denominador a la vez -- pero la CANTIDAD sí.

    Dos cosas que parecen detalle y no lo son:

    EL EJE VA POR CÓDIGO, no por nombre. Los nombres pueden repetirse (un
    código sin mapear cae a su valor crudo) y Plotly colapsa dos categorías
    con la misma etiqueta en una sola fila, mostrando el valor de un segmento
    bajo el nombre de otro, sin error. El código es único por definición; el
    nombre va solo en ticktext.

    LOS EJES SALEN DE LA UNIÓN DE LOS DOS MESES, no solo del actual. Si un
    producto o un segmento deja de calificarse por completo, armando los ejes
    con el mes actual simplemente desaparecería de la matriz -- y esa
    desaparición es exactamente la anomalía que hay que ver. Con la unión la
    celda queda, y se muestra su caída a cero.
    """
    if cob.empty:
        return _sin_datos()
    idx_base, dist = mes_comparacion(cob["idx_mes"], idx_mes)
    act = cob[cob["idx_mes"] == idx_mes]
    prev = (cob[cob["idx_mes"] == idx_base] if idx_base is not None
            else cob.iloc[0:0])
    if act.empty and prev.empty:
        return _sin_datos()
    if modo == "variacion" and idx_base is None:
        return _sin_datos(
            f"no hay ningún mes anterior a {theme.etiqueta_mes_idx(idx_mes)} "
            f"en los datos: no hay contra qué comparar")

    universo = pd.concat([act, prev]) if not prev.empty else act
    segs = theme.segmentos_ordenados(universo["segmento"])
    prods = [x for x in theme.PRODUCTOS_ORDENADOS
             if x in set(universo["producto"])]
    if not segs or not prods:
        return _sin_datos()

    if act.empty:
        vacia = pd.DataFrame(float("nan"), index=segs, columns=prods)
        cnt, base = vacia.copy(), vacia.copy()
    else:
        cnt, base = _pivote_cobertura(act, segs, prods)
    cob_pct = cnt / base.where(base > 0)

    if modo == "variacion":
        cnt0, _ = _pivote_cobertura(prev, segs, prods)
        # fillna(0) de los dos lados: una celda que aparece o que desaparece
        # es información, no un hueco.
        a, b = cnt.fillna(0).values.astype(float), cnt0.fillna(0).values.astype(float)
        z = np.divide(a - b, np.abs(b), out=np.full_like(a, np.nan), where=b != 0)
        # Existía y se fue a cero: -100%, no NaN. Es el caso a ver.
        z = np.where((b != 0) & (a == 0), -1.0, z)
        texto = np.where(np.isnan(z), "",
                         np.vectorize(lambda v: "" if v != v else f"{v * 100:+.0f}%")(z))
        lim = float(np.nanmax(np.abs(z))) if np.isfinite(z).any() else 1.0
        lim = max(0.05, min(lim, 1.0))
        escala, zmin, zmax, zmid = theme.ESCALA_DIVERGENTE, -lim, lim, 0
        barra = dict(title=dict(text="baja &#8592; &#8594; sube",
                                font=dict(size=10, color=theme.INK_MUTED)),
                     tickformat="+.0%", thickness=12, len=0.75, outlinewidth=0)
        hover = ("<b>%{y}</b> · %{x}<br>%{z:+.1%}<br>%{customdata[0]:,.0f} en "
                 + theme.etiqueta_mes_idx(idx_mes) + ", %{customdata[1]:,.0f} en "
                 + theme.etiqueta_mes_idx(idx_base) + "<extra></extra>")
        extra = np.stack([a, b], axis=-1)
    elif modo == "cobertura":
        z = cob_pct.values.astype(float)
        texto = np.where(np.isnan(z), "",
                         np.vectorize(lambda v: "" if v != v else f"{v * 100:.0f}")(z))
        escala, zmin, zmax, zmid = theme.ESCALA_SECUENCIAL, 0, None, None
        barra = dict(title=dict(text="% del<br>segmento", font=dict(size=10)),
                     tickformat=".0%", thickness=12, len=0.75, outlinewidth=0)
        hover = ("<b>%{y}</b> · %{x}<br>%{z:.1%} de la base del segmento"
                 "<br>%{customdata[0]:,.0f} de %{customdata[1]:,.0f}<extra></extra>")
        extra = np.stack([cnt.fillna(0).values, base.fillna(0).values], axis=-1)
    else:
        z = cnt.values.astype(float)
        texto = np.where(np.isnan(z), "", np.vectorize(theme.fmt_compacto)(z))
        escala, zmin, zmax, zmid = theme.ESCALA_SECUENCIAL, 0, None, None
        barra = dict(title=dict(text="clientes", font=dict(size=10)),
                     thickness=12, len=0.75, outlinewidth=0)
        hover = ("<b>%{y}</b> · %{x}<br>%{z:,.0f} clientes calificados"
                 "<br>%{customdata[0]:.1%} de la base del segmento<extra></extra>")
        extra = np.stack([cob_pct.fillna(0).values], axis=-1)

    etiquetas_y = theme.etiquetas_segmento(segs)   # falla si dos se repiten
    heat = dict(z=z, x=prods, y=segs, colorscale=escala, xgap=3, ygap=3,
                customdata=extra, colorbar=barra, hovertemplate=hover)
    for k, v in (("zmin", zmin), ("zmax", zmax), ("zmid", zmid)):
        if v is not None:
            heat[k] = v
    fig = go.Figure(go.Heatmap(**heat))

    limite = float(np.nanmax(np.abs(z))) if np.isfinite(z).any() else 1.0
    for i, seg in enumerate(segs):
        for j, pr in enumerate(prods):
            if not texto[i][j]:
                continue
            fuerte = limite > 0 and abs(z[i][j]) > 0.55 * limite
            fig.add_annotation(
                x=pr, y=seg, text=texto[i][j], showarrow=False,
                font=dict(size=9, family=theme.FONT,
                          color="#ffffff" if fuerte else theme.INK))

    aparte = [c for c in segs if theme.fuera_de_escala(c)]
    if aparte and len(aparte) < len(segs):
        fig.add_hline(y=len(segs) - len(aparte) - 0.5,
                      line=dict(color=theme.INK_MUTED, width=1, dash="dot"))
        fig.add_annotation(
            x=1, y=-0.16, xref="paper", yref="paper", xanchor="right",
            showarrow=False,
            text="Debajo de la línea, los segmentos que no forman parte de la "
                 "escala de valor y no se comparan con ella.",
            font=dict(size=11, color=theme.INK_MUTED, family=theme.FONT))

    if modo == "variacion":
        aviso = (f"{theme.etiqueta_mes_idx(idx_mes)} contra "
                 f"{theme.etiqueta_mes_idx(idx_base)}")
        if dist > 1:
            aviso += (f" — falta la partición del mes inmediatamente anterior, "
                      f"así que la comparación es a {dist} meses")
        fig.add_annotation(
            x=0, y=-0.16, xref="paper", yref="paper", xanchor="left",
            showarrow=False, text=aviso,
            font=dict(size=11, family=theme.FONT,
                      color=theme.ESTADO_ALERTA if dist > 1 else theme.INK_SOFT))

    fig.update_layout(height=max(340, 44 * len(segs) + 200))
    fig.update_xaxes(title_text="", side="top", showline=False, ticks="",
                     type="category", categoryorder="array", categoryarray=prods,
                     tickangle=-40)
    # Eje por CÓDIGO; el nombre legible solo en ticktext.
    fig.update_yaxes(title_text="", showgrid=False, showline=False, ticks="",
                     type="category", categoryorder="array",
                     categoryarray=list(reversed(segs)),
                     tickmode="array", tickvals=segs, ticktext=etiquetas_y)
    return _t(fig)


# ===========================================================================
# RANKING DE ANOMALIAS
# ===========================================================================
# No es un semáforo. Con 96 celdas moviéndose cada mes por razones normales, un
# panel de alertas binarias se vuelve ruido y deja de mirarse. Esto es un
# RANKING de lo que más se movió, que siempre muestra sus primeras filas
# aunque ninguna sea grave.

PISO_VARIACION = 0.03    # 3%


BASE_MINIMA = 500


MESES_MINIMOS = 6


_MAD_A_SIGMA = 1.4826    # escala la MAD para que sea comparable a un desvío


@dataclass
class Anomalias:
    """Resultado del ranking, con el contexto necesario para poder leerlo.

    Los meses viajan acá y no se recalculan en cada página: quien pinta la
    tabla tiene que poder decir contra qué mes se compara sin volver a
    suponerlo.
    """
    ranking: pd.DataFrame            # celdas con baseline, por puntaje
    sin_variabilidad: pd.DataFrame   # MAD nula: se movieron y nunca se movían
    sin_baseline: pd.DataFrame       # menos de MESES_MINIMOS de historia
    idx_mes: int
    idx_base: int | None
    distancia: int                   # meses entre idx_base e idx_mes
    col_base: str = ""               # nombre de la columna del mes de base
    col_act: str = ""                # nombre de la columna del mes actual

    @property
    def mes(self) -> str:
        return theme.etiqueta_mes_idx(self.idx_mes)

    @property
    def base(self) -> str:
        return (theme.etiqueta_mes_idx(self.idx_base)
                if self.idx_base is not None else "—")

    @property
    def hay_hueco(self) -> bool:
        """Falta el mes inmediatamente anterior: la comparación se estiró."""
        return self.idx_base is not None and self.distancia > 1


def _variaciones_consecutivas(serie: pd.Series) -> pd.Series:
    """Variaciones relativas SOLO entre meses consecutivos.

    `pct_change()` sobre la serie cruda no mira el índice: si falta un mes,
    trata un salto de dos meses como si fuera de uno. Esa variación entra a la
    mediana y a la MAD inflándolas, el baseline queda más ancho de lo que
    corresponde, y una anomalía real deja de destacarse. Los huecos se
    descartan: mejor un baseline con menos puntos que uno con puntos que miden
    otra cosa.

    El índice del resultado es el mes POSTERIOR de cada par.
    """
    s = serie.sort_index()
    if len(s) < 2:
        return pd.Series(dtype=float)
    meses = pd.Series(s.index, index=s.index)
    ant_v, ant_i = s.shift(1), meses.shift(1)
    var = (s - ant_v) / ant_v.abs()
    vale = (meses - ant_i == 1) & ant_v.notna() & (ant_v != 0) & s.notna()
    return var[vale]


def ranking_anomalias(cob: pd.DataFrame, idx_mes: int, metrica: str = "cantidad",
                      tope: int = 15) -> Anomalias:
    """Celdas segmento x producto ordenadas por cuánto se salieron de SU propia
    historia.

    El baseline usa MEDIANA y MAD, no promedio y desvío. La razón es concreta:
    los incidentes pasados están DENTRO de la historia, y con promedio/desvío
    un incidente infla su propia variabilidad, con lo cual el siguiente igual
    parece normal. La mediana no se mueve por unos pocos valores extremos.

    Tres guardas, todas necesarias:

      PISO_VARIACION  una celda que nunca se mueve tiene MAD casi cero, y ahí
                      un cambio de 0,3% da un puntaje enorme. Sin este piso el
                      ranking se llena de ruido irrelevante.
      BASE_MINIMA     una celda de 40 clientes salta de 40 a 60 sin que
                      signifique nada.
      MESES_MINIMOS   con menos historia el baseline no es baseline. Esas
                      celdas NO reciben puntaje: van a la lista aparte con su
                      variación cruda, para no fingir una precisión que no hay.

    Las celdas con MAD nula tampoco reciben puntaje. Antes se les daba 99,0,
    un centinela que ordenaba junto a puntajes calculados y por construcción
    encabezaba el ranking siempre, empujando hacia abajo anomalías reales. Un
    número inventado no compite con uno medido: van a su propia tabla.

    `metrica` es 'cantidad' (clientes calificados) o 'cobertura' (% sobre la
    base). Son problemas distintos: desaparecer de la tabla no es lo mismo que
    quedar sin grupo, y por eso el ranking se calcula sobre las dos.
    """
    vacio = Anomalias(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                      idx_mes, None, 0)
    if cob.empty:
        return vacio
    idx_base, dist = mes_comparacion(cob["idx_mes"], idx_mes)
    if idx_base is None:
        return vacio
    col_base = theme.etiqueta_mes_idx(idx_base)
    col_act = theme.etiqueta_mes_idx(idx_mes)

    col = "cubiertos" if metrica == "cantidad" else "cobertura"
    d = cob.copy()
    d["segmento"] = d["segmento"].map(theme._cod)
    g = d.groupby(["segmento", "producto", "idx_mes"], as_index=False).agg(
        cubiertos=("cubiertos", "sum"), clientes=("clientes", "sum"))
    g["cobertura"] = g["cubiertos"] / g["clientes"].where(g["clientes"] > 0)

    filas, sin_var, sin_base = [], [], []
    for (seg, prod), sub in g.groupby(["segmento", "producto"]):
        sub = sub.sort_values("idx_mes")
        serie = sub.set_index("idx_mes")[col]
        base_cli = sub.set_index("idx_mes")["cubiertos"]
        if idx_mes not in serie.index or idx_base not in serie.index:
            continue
        ant, act = serie.loc[idx_base], serie.loc[idx_mes]
        if base_cli.loc[idx_base] < BASE_MINIMA:
            continue
        if ant != ant or ant == 0:
            continue
        var_rel = (act - ant) / abs(ant)

        # Solo pares de meses consecutivos, y solo historia previa al mes.
        historia = _variaciones_consecutivas(serie)
        historia = historia[historia.index < idx_mes]
        comun = {
            "segmento": theme.etiqueta_segmento(seg), "_cod_seg": seg,
            "producto": prod, col_base: ant, col_act: act,
            "var_abs": act - ant, "var_rel": var_rel,
            "meses_historia": len(historia),
            "serie": serie.reindex(sorted(serie.index)).tolist(),
        }
        if len(historia) < MESES_MINIMOS:
            sin_base.append(comun)
            continue
        if abs(var_rel) < PISO_VARIACION:
            continue
        mediana = float(historia.median())
        mad = float((historia - mediana).abs().median()) * _MAD_A_SIGMA
        if mad <= 1e-9:
            # La celda nunca se movió en toda su historia. Con el piso de
            # variación ya superado el salto es real, pero no hay escala
            # contra la cual medirlo: cualquier puntaje sería inventado.
            sin_var.append({**comun, "mediana_historica": mediana})
            continue
        filas.append({**comun, "puntaje": abs(var_rel - mediana) / mad})

    def _por_variacion(registros):
        df = pd.DataFrame(registros)
        if df.empty:
            return df
        return (df.reindex(df["var_rel"].abs().sort_values(ascending=False).index)
                .reset_index(drop=True))

    rk = pd.DataFrame(filas)
    if not rk.empty:
        # SOLO por magnitud del puntaje. Sin ponderar por valor de segmento: el
        # orden de valor ya se ve en la columna, que lleva el nombre.
        rk = (rk.sort_values("puntaje", ascending=False)
              .head(tope).reset_index(drop=True))
    return Anomalias(rk, _por_variacion(sin_var), _por_variacion(sin_base),
                     idx_mes, idx_base, dist, col_base, col_act)


def mini_serie(valores: list, ancho: int = 150, alto: int = 34) -> go.Figure:
    """Sparkline de la historia de una celda: distingue un salto de una
    tendencia, que es la pregunta que sigue a ver el puntaje."""
    fig = go.Figure(go.Scatter(
        y=valores, mode="lines", line=dict(color=theme.SERIES[0], width=1.6),
        hoverinfo="skip"))
    if valores:
        fig.add_scatter(x=[len(valores) - 1], y=[valores[-1]], mode="markers",
                        marker=dict(size=5, color=theme.ESTADO_CRITICO),
                        hoverinfo="skip")
    fig.update_layout(
        height=alto, width=ancho, margin=dict(l=0, r=0, t=2, b=2),
        showlegend=False, paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# ===========================================================================
# PUENTE DE LA BASE
# ===========================================================================

def puente_base(df: pd.DataFrame, idx_mes: int,
                segmento: str | None = None) -> go.Figure:
    """Cascada: base del mes anterior, entradas, salidas, base del mes.

    Sabemos que la base cae, pero no por qué. Esto lo separa: si la caída viene
    de que se van clientes se ve en la barra de salidas, y si viene de que
    dejan de calificar, la base no se mueve pero sí la cobertura.
    """
    if df.empty:
        return _sin_datos()
    d = df.copy()
    d["segmento"] = d["segmento"].map(theme._cod)
    if segmento and segmento != "todos":
        d = d[d["segmento"] == theme._cod(segmento)]
    act = d[d["idx_mes"] == idx_mes]
    if act.empty:
        return _sin_datos("no hay datos del puente para este mes")

    def _c(cat):
        return float(act[act["categoria"] == cat]["clientes"].sum())

    permanece, entrada, salida = _c("permanece"), _c("entrada"), _c("salida")
    anterior = permanece + salida
    actual = permanece + entrada

    # Sin mes de referencia, el full outer join de 11_puente_base.sql deja TODO
    # como entrada: la cascada arrancaría en cero y se leería como si la base
    # se hubiera creado ese mes. Es el caso que antes pasaba en silencio.
    if permanece == 0 and salida == 0:
        meses = sorted(int(m) for m in set(df["idx_mes"].dropna()))
        motivo = ("es el primer mes de la ventana"
                  if meses and idx_mes <= meses[0]
                  else f"falta la partición de "
                       f"{theme.etiqueta_mes_idx(idx_mes - 1)}")
        return _sin_datos(
            f"{theme.etiqueta_mes_idx(idx_mes)} no tiene mes anterior contra "
            f"el cual armar el puente ({motivo}): todos los clientes entran "
            f"como entrada y la cascada no significa nada.")

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "relative", "total"],
        x=[theme.etiqueta_mes_idx(idx_mes - 1), "Entradas", "Salidas",
           theme.etiqueta_mes_idx(idx_mes)],
        y=[anterior, entrada, -salida, actual],
        text=[theme.fmt_miles(anterior), f"+{theme.fmt_miles(entrada)}",
              f"-{theme.fmt_miles(salida)}", theme.fmt_miles(actual)],
        textposition="outside",
        textfont=dict(size=11, color=theme.INK_SOFT, family=theme.FONT),
        connector=dict(line=dict(color=theme.AXIS, width=1)),
        increasing=dict(marker=dict(color=theme.DIV_MEJORA)),
        decreasing=dict(marker=dict(color=theme.DIV_DETERIORO)),
        totals=dict(marker=dict(color=theme.INK_MUTED)),
        hovertemplate="%{x}<br>%{y:,.0f} clientes<extra></extra>",
    ))
    neto = actual - anterior
    fig.add_annotation(
        x=0, y=-0.18, xref="paper", yref="paper", xanchor="left",
        showarrow=False,
        text=(f"{theme.etiqueta_mes_idx(idx_mes)} contra "
              f"{theme.etiqueta_mes_idx(idx_mes - 1)}"),
        font=dict(size=11, color=theme.INK_SOFT, family=theme.FONT))
    fig.add_annotation(
        x=1, y=-0.18, xref="paper", yref="paper", xanchor="right",
        showarrow=False,
        text=(f"Neto {'+' if neto >= 0 else ''}{theme.fmt_miles(neto)} "
              f"({(neto / anterior * 100) if anterior else 0:+.1f}%)"),
        font=dict(size=11, family=theme.FONT,
                  color=theme.ESTADO_OK if neto >= 0 else theme.ESTADO_CRITICO))
    fig.update_layout(height=400, showlegend=False)
    fig.update_xaxes(title_text="", type="category")
    fig.update_yaxes(title_text="Clientes en la base", tickformat=",.0f",
                     rangemode="tozero")
    return _t(fig)


def puente_por_segmento(df: pd.DataFrame, idx_mes: int) -> go.Figure:
    """Entradas y salidas por segmento, en el orden de valor de negocio.

    Es la vista que dice de dónde viene la caída: un neto negativo concentrado
    en un segmento no es lo mismo que uno repartido.
    """
    if df.empty:
        return _sin_datos()
    d = df[df["idx_mes"] == idx_mes].copy()
    if d.empty:
        return _sin_datos("no hay datos del puente para este mes")
    d["segmento"] = d["segmento"].map(theme._cod)
    segs = theme.segmentos_ordenados(d["segmento"])
    piv = (d.pivot_table(index="segmento", columns="categoria", values="clientes",
                         aggfunc="sum").reindex(segs).fillna(0))
    for c in ("entrada", "salida"):
        if c not in piv.columns:
            piv[c] = 0
    # El eje va por CÓDIGO; el nombre solo en ticktext.
    etiquetas = theme.etiquetas_segmento(segs)

    fig = go.Figure()
    fig.add_bar(y=segs, x=piv["entrada"].values, name="Entradas",
                orientation="h",
                marker=dict(color=theme.DIV_MEJORA,
                            line=dict(color=theme.SURFACE, width=2)),
                hovertemplate="%{y}<br>+%{x:,.0f} entradas<extra></extra>")
    fig.add_bar(y=segs, x=-piv["salida"].values, name="Salidas",
                orientation="h",
                marker=dict(color=theme.DIV_DETERIORO,
                            line=dict(color=theme.SURFACE, width=2)),
                customdata=piv["salida"].values,
                hovertemplate="%{y}<br>-%{customdata:,.0f} salidas<extra></extra>")
    fig.add_vline(x=0, line=dict(color=theme.AXIS, width=1))
    sin_ref = float(piv["salida"].sum()) == 0
    fig.add_annotation(
        x=0, y=-0.20, xref="paper", yref="paper", xanchor="left",
        showarrow=False,
        text=(f"Entradas y salidas entre "
              f"{theme.etiqueta_mes_idx(idx_mes - 1)} y "
              f"{theme.etiqueta_mes_idx(idx_mes)}"
              + (" — sin salidas en ningún segmento: no hay mes de "
                 "referencia, todo entra como entrada" if sin_ref else "")),
        font=dict(size=11, family=theme.FONT,
                  color=theme.ESTADO_ALERTA if sin_ref else theme.INK_SOFT))
    fig.update_layout(barmode="relative", height=max(320, 46 * len(segs) + 150),
                      legend_traceorder="normal")
    fig.update_xaxes(title_text="Clientes (entradas a la derecha, salidas a la izquierda)",
                     tickformat=",.0f")
    fig.update_yaxes(title_text="", type="category", categoryorder="array",
                     categoryarray=list(reversed(segs)),
                     tickmode="array", tickvals=segs, ticktext=etiquetas)
    return _t(fig)
