"""Construcción de figuras. NINGUNA función de este módulo renderiza.

Cada figura se define UNA vez acá y tiene dos salidas: main.py la pinta con
st.plotly_chart y export.py la escribe con write_html. Si un gráfico se ve
distinto en el HTML que en la app, es un bug de este archivo, no de dos
implementaciones que se separaron.

Las funciones que devuelven tablas (`tabla_*`) devuelven DataFrames, no
figuras: son alertas de calidad, no gráficos.
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


def composicion_grupo(df: pd.DataFrame, familia: str | None = None,
                      orden_productos: list[str] | None = None) -> go.Figure:
    """Composición de grupo por producto, barra apilada 100%.

    Apilada por grupo_orden ascendente: la barra lee de menor a mayor riesgo de
    izquierda a derecha, y el gradiente de la rampa hace de leyenda.

    `orden_productos` fija el eje explícitamente. Sirve para el comparador de
    dos meses: si cada panel ordena por sus propios datos, un producto cambia
    de fila entre meses y la comparación visual deja de servir.
    """
    if df.empty:
        return _sin_datos()
    d = df.copy()
    if familia and familia != "todas":
        d = d[d["producto"].map(_FAM) == familia]
    if d.empty:
        return _sin_datos()

    piv = (d.groupby(["producto", "grupo", "grupo_orden"], as_index=False)["clientes"].sum())
    tot = piv.groupby("producto")["clientes"].transform("sum")
    piv["share"] = piv["clientes"] / tot
    if orden_productos is not None:
        presentes = set(piv["producto"])
        orden_prod = [p for p in orden_productos if p in presentes]
    else:
        # Productos ordenados por su masa en los grupos peores: el ojo baja por
        # una lista que ya está rankeada por riesgo, no por alfabeto.
        peor = (piv[piv["grupo_orden"] >= 60].groupby("producto")["share"].sum()
                .reindex(piv["producto"].unique()).fillna(0).sort_values())
        orden_prod = peor.index.tolist()

    fig = go.Figure()
    for grupo in _grupos_ordenados(piv["grupo"]):
        s = piv[piv["grupo"] == grupo].set_index("producto").reindex(orden_prod)
        fig.add_bar(
            y=orden_prod, x=s["share"].values, name=grupo, orientation="h",
            marker=dict(color=theme.COLOR_GRUPO.get(grupo, theme.INK_MUTED),
                        line=dict(color=theme.SURFACE, width=2)),  # gap de 2px
            customdata=np.stack([s["clientes"].fillna(0).values], axis=-1),
            hovertemplate=("<b>%{y}</b> · " + grupo +
                           "<br>%{x:.1%} de la cartera del producto"
                           "<br>%{customdata[0]:,.0f} clientes<extra></extra>"),
        )
    # traceorder normal: la leyenda sigue el orden de apilado (G1 primero), no
    # el invertido que Plotly usa por defecto en barras apiladas.
    fig.update_layout(barmode="stack", legend_traceorder="normal",
                      height=max(360, 34 * len(orden_prod) + 130))
    fig.update_xaxes(title_text="Participación en la cartera del producto",
                     tickformat=".0%", range=[0, 1])
    # categoryorder explícito: el eje NO se ordena por los datos.
    fig.update_yaxes(title_text="", categoryorder="array",
                     categoryarray=list(reversed(orden_prod)))
    return _t(fig)


def heatmap_segmento_grupo(df: pd.DataFrame, producto: str | None = None,
                           normalizar: bool = True) -> go.Figure:
    """Segmento × grupo.

    Con `normalizar=True` (el default) cada FILA suma 100% y el color dice el
    porcentaje dentro de ese segmento. Es lo que hace falta para comparar: sin
    normalizar, los segmentos grandes se llevan todo el color y los chicos se
    ven vacíos, aunque su reparto interno sea peor.

    Con `normalizar=False` el color es el conteo absoluto, para cuando la
    pregunta es de volumen y no de reparto. El otro valor viaja siempre en el
    hover, así que no hay que cambiar de vista para leerlo.
    """
    if df.empty:
        return _sin_datos()
    d = df if not producto or producto == "todos" else df[df["producto"] == producto]
    if d.empty:
        return _sin_datos()

    d = d.copy()
    # A string ANTES de agrupar: si el segmento es un código numérico, Plotly
    # trata el eje como escala continua y las filas salen como una banda sin
    # celdas, con ticks 2,3,4,5 en vez de categorías.
    d["segmento"] = d["segmento"].map(theme.etiqueta_segmento)
    g = d.groupby(["segmento", "grupo"], as_index=False)["clientes"].sum()
    g["share"] = g["clientes"] / g.groupby("segmento")["clientes"].transform("sum")
    cols = _grupos_ordenados(g["grupo"])
    piv = g.pivot(index="segmento", columns="grupo", values="share").reindex(columns=cols)
    cnt = g.pivot(index="segmento", columns="grupo", values="clientes").reindex(columns=cols)
    # Segmentos por tamaño: el más grande arriba, para que la lectura no
    # dependa del alfabeto.
    orden_seg = [str(v) for v in
                 g.groupby("segmento")["clientes"].sum()
                  .sort_values(ascending=False).index]
    piv, cnt = piv.reindex(orden_seg), cnt.reindex(orden_seg)

    if normalizar:
        z, extra, fmt, titulo = piv.values, cnt.values, ".0%", "% del<br>segmento"
        linea_z = "%{z:.1%} del segmento<br>%{customdata:,.0f} clientes"
    else:
        z, extra, fmt, titulo = cnt.values, piv.values, ",.0f", "clientes"
        linea_z = "%{z:,.0f} clientes<br>%{customdata:.1%} del segmento"

    fig = go.Figure(go.Heatmap(
        z=z, x=cols, y=[str(v) for v in piv.index],
        colorscale=theme.ESCALA_SECUENCIAL, zmin=0,
        xgap=3, ygap=3, customdata=extra,
        colorbar=dict(title=dict(text=titulo, font=dict(size=11)),
                      tickformat=fmt, thickness=12, len=0.75, outlinewidth=0),
        hovertemplate=("Segmento <b>%{y}</b> · grupo <b>%{x}</b><br>"
                       + linea_z + "<extra></extra>"),
    ))
    # El número dentro de la celda: con pocos segmentos entra y se lee sin
    # pasar el mouse.
    for i, seg in enumerate(piv.index):
        for j, gr in enumerate(cols):
            v = piv.values[i][j]
            if v is None or (isinstance(v, float) and v != v):
                continue
            fig.add_annotation(
                x=gr, y=str(seg), showarrow=False,
                text=(f"{v:.0%}" if normalizar else theme.fmt_miles(cnt.values[i][j])),
                font=dict(size=10, family=theme.FONT,
                          color="#ffffff" if v > (0.55 if normalizar else 0) and
                          (normalizar or cnt.values[i][j] > 0.55 * float(cnt.values.max()))
                          else theme.INK))

    fig.update_layout(height=max(320, 46 * len(piv.index) + 150))
    # type="category" explícito: sin eso Plotly infiere numérico cuando los
    # segmentos son códigos. categoryorder="array" en los dos ejes, para que
    # ni el grupo ni el segmento dependan del orden en que llegan los datos.
    fig.update_xaxes(title_text="Grupo de riesgo", showline=False, ticks="",
                     type="category", categoryorder="array", categoryarray=cols)
    fig.update_yaxes(title_text="", showgrid=False, showline=False, ticks="",
                     type="category", categoryorder="array",
                     categoryarray=[str(v) for v in reversed(orden_seg)])
    return _t(fig)


def cobertura(df: pd.DataFrame, segmento: str | None = None) -> go.Figure:
    """Cobertura por producto. La baja de comercial/micro/sobregiro es
    estructural, no una falla: va anotada en el propio gráfico."""
    if df.empty:
        return _sin_datos()
    d = df if not segmento or segmento == "todos" else df[df["segmento"] == segmento]
    if d.empty:
        return _sin_datos()

    g = d.groupby("producto", as_index=False)[["cubiertos", "clientes"]].sum()
    g["cobertura"] = g["cubiertos"] / g["clientes"].where(g["clientes"] > 0)
    g = g.sort_values("cobertura")
    negocio = {"comercial", "micro", "sobregiro"}
    colores = [theme.INK_MUTED if p in negocio else theme.SERIES[0] for p in g["producto"]]

    fig = go.Figure(go.Bar(
        y=g["producto"], x=g["cobertura"], orientation="h",
        marker=dict(color=colores, line=dict(color=theme.SURFACE, width=2)),
        text=[theme.fmt_pct(v) for v in g["cobertura"]],
        textposition="outside", textfont=dict(size=11, color=theme.INK_SOFT),
        customdata=np.stack([g["cubiertos"], g["clientes"]], axis=-1),
        hovertemplate=("<b>%{y}</b><br>%{x:.1%} de cobertura"
                       "<br>%{customdata[0]:,.0f} de %{customdata[1]:,.0f} clientes"
                       "<extra></extra>"),
    ))
    fig.add_annotation(
        x=1, y=-0.16, xref="paper", yref="paper", xanchor="right", showarrow=False,
        text="En gris, los productos de pequeño negocio: su cobertura baja es estructural",
        font=dict(size=11, color=theme.INK_MUTED, family=theme.FONT))
    fig.update_layout(height=max(360, 30 * len(g) + 150))
    fig.update_xaxes(title_text="Clientes con calificación, sobre la base del mes",
                     tickformat=".0%", range=[0, max(0.05, g["cobertura"].max() * 1.18)])
    fig.update_yaxes(title_text="")
    return _t(fig)


# ===========================================================================
# EVOLUCION
# ===========================================================================

def mezcla_riesgo(df: pd.DataFrame, producto: str) -> go.Figure:
    """Mezcla de riesgo en el tiempo, área apilada al 100%.

    En porcentaje y no en conteo: la base cae 9% en la ventana, y apilar
    conteos haría leer la contracción como mejora del riesgo.
    """
    if df.empty:
        return _sin_datos()
    d = df[df["producto"] == producto] if producto and producto != "todos" else df
    if d.empty:
        return _sin_datos()

    g = d.groupby(["idx_mes", "grupo"], as_index=False)["clientes"].sum()
    g["share"] = g["clientes"] / g.groupby("idx_mes")["clientes"].transform("sum")
    meses = sorted(g["idx_mes"].unique())
    etiquetas = [theme.etiqueta_mes_idx(m) for m in meses]

    fig = go.Figure()
    for grupo in _grupos_ordenados(g["grupo"]):
        s = g[g["grupo"] == grupo].set_index("idx_mes").reindex(meses)
        fig.add_scatter(
            x=etiquetas, y=s["share"].values, name=grupo,
            mode="lines", stackgroup="riesgo", groupnorm="fraction",
            line=dict(width=0.5, color=theme.SURFACE),
            fillcolor=theme.COLOR_GRUPO.get(grupo, theme.INK_MUTED),
            hovertemplate=grupo + " · %{y:.1%}<extra></extra>",
        )
    # traceorder normal: la leyenda sigue el orden de apilado (G1 abajo).
    fig.update_layout(height=430, legend_traceorder="normal")
    fig.update_xaxes(title_text="", categoryorder="array", categoryarray=etiquetas)
    fig.update_yaxes(title_text="Participación de la cartera", tickformat=".0%",
                     range=[0, 1])
    return _t(fig, unified=True)


def base_clientes_tiempo(df: pd.DataFrame) -> go.Figure:
    """Base por mes y segmento. Es el visual que evita malinterpretar la
    composición: acá se ve la contracción en conteo absoluto."""
    if df.empty:
        return _sin_datos()
    g = df.groupby(["idx_mes", "segmento"], as_index=False)["clientes"].sum()
    meses = sorted(g["idx_mes"].unique())
    etiquetas = [theme.etiqueta_mes_idx(m) for m in meses]

    top = (g.groupby("segmento")["clientes"].sum().sort_values(ascending=False))
    segmentos = top.index.tolist()[:4]   # máximo 4 series distinguibles
    otros = [s for s in top.index if s not in segmentos]

    fig = go.Figure()
    for i, seg in enumerate(segmentos):
        s = g[g["segmento"] == seg].set_index("idx_mes").reindex(meses)
        fig.add_scatter(
            x=etiquetas, y=s["clientes"].values, name=seg, mode="lines",
            line=dict(color=theme.SERIES[i], width=2, dash=theme.SERIES_DASH[i]),
            hovertemplate=seg + " · %{y:,.0f} clientes<extra></extra>",
        )
    if otros:
        s = (g[g["segmento"].isin(otros)].groupby("idx_mes")["clientes"].sum()
             .reindex(meses))
        fig.add_scatter(
            x=etiquetas, y=s.values, name=f"otros ({len(otros)})", mode="lines",
            line=dict(color=theme.INK_MUTED, width=1.5, dash="dot"),
            hovertemplate="otros · %{y:,.0f} clientes<extra></extra>",
        )
    fig.update_layout(height=400)
    fig.update_xaxes(title_text="")
    fig.update_yaxes(title_text="Clientes en la base del mes", tickformat=",.0f",
                     rangemode="tozero")
    return _t(fig, unified=True)


def vigencia_modelos(df: pd.DataFrame) -> go.Figure:
    """% de población por modelo en el tiempo. Un escalón acá explica saltos en
    las otras páginas."""
    if df.empty:
        return _sin_datos()
    d = df.copy()
    d["modelo"] = d["modelo"].fillna("sin modelo")
    g = d.groupby(["idx_mes", "modelo"], as_index=False)["clientes"].sum()
    g["share"] = g["clientes"] / g.groupby("idx_mes")["clientes"].transform("sum")
    meses = sorted(g["idx_mes"].unique())
    etiquetas = [theme.etiqueta_mes_idx(m) for m in meses]

    top = g.groupby("modelo")["share"].mean().sort_values(ascending=False)
    principales = top.index.tolist()[:4]
    resto = [m for m in top.index if m not in principales]

    fig = go.Figure()
    for i, mod in enumerate(principales):
        s = g[g["modelo"] == mod].set_index("idx_mes").reindex(meses)
        fig.add_scatter(
            x=etiquetas, y=s["share"].values, name=mod, mode="lines",
            line=dict(color=theme.SERIES[i], width=2, dash=theme.SERIES_DASH[i]),
            hovertemplate=mod + " · %{y:.1%} de la población<extra></extra>",
        )
    if resto:
        s = (g[g["modelo"].isin(resto)].groupby("idx_mes")["share"].sum().reindex(meses))
        fig.add_scatter(
            x=etiquetas, y=s.values, name=f"otros ({len(resto)})", mode="lines",
            line=dict(color=theme.INK_MUTED, width=1.5, dash="dot"),
            hovertemplate="otros · %{y:.1%}<extra></extra>",
        )
    fig.update_layout(height=400)
    fig.update_xaxes(title_text="")
    fig.update_yaxes(title_text="Participación de la población calificada",
                     tickformat=".0%", rangemode="tozero")
    return _t(fig, unified=True)


# ===========================================================================
# MIGRACION
# ===========================================================================

_FUERA = ["entrada", "ganancia_elegibilidad", "salida", "perdida_elegibilidad"]


def matriz_migracion(df: pd.DataFrame, producto: str, solo_mismo_segmento: bool = True
                     ) -> go.Figure:
    """Matriz 8x8 sobre grupo_base, con entradas y salidas al margen.

    El color es DIVERGENTE y centrado en la diagonal: el tono dice la dirección
    (azul mejora, rojo deterioro) y la intensidad dice el volumen, como
    participación de la fila de origen. La diagonal queda neutra por
    construcción, sin importar su masa: es estabilidad, no señal.

    Entradas, salidas y elegibilidad van en gris, FUERA de la escala: no son un
    grupo de riesgo, son cambios de población o decisiones del modelo.
    """
    if df.empty:
        return _sin_datos()
    d = df[df["producto"] == producto] if producto and producto != "todos" else df.copy()
    if solo_mismo_segmento and "segmento_anterior" in d.columns:
        d = d[d["segmento_anterior"] == d["segmento_actual"]]
    if d.empty:
        return _sin_datos()

    ejes = theme.GRUPOS_BASE_ORDENADOS
    mov = d[d["categoria"] == "movimiento"]
    m = (mov.groupby(["grupo_base_origen", "grupo_base_destino"], as_index=False)["clientes"]
         .sum().pivot(index="grupo_base_origen", columns="grupo_base_destino",
                      values="clientes").reindex(index=ejes, columns=ejes))
    cnt = m.fillna(0).values
    fila = cnt.sum(axis=1, keepdims=True)
    share = np.divide(cnt, fila, out=np.zeros_like(cnt, dtype=float), where=fila > 0)

    # z firmado: negativo = mejora, positivo = deterioro, 0 = diagonal.
    idx = np.arange(len(ejes))
    signo = np.sign(idx[None, :] - idx[:, None])
    z = share * signo

    texto = np.where(cnt > 0, np.vectorize(theme.fmt_miles)(cnt), "")
    # Tinta legible sobre cada celda: la escala se oscurece hacia los extremos.
    tinta = np.where(np.abs(z) > 0.45, "#ffffff", theme.INK)

    fig = go.Figure(go.Heatmap(
        z=z, x=ejes, y=ejes, zmid=0, zmin=-1, zmax=1,
        colorscale=theme.ESCALA_DIVERGENTE, xgap=2, ygap=2,
        customdata=np.stack([cnt, share], axis=-1),
        colorbar=dict(
            title=dict(text="mejora  <->  deterioro<br>(% de la fila)",
                       font=dict(size=10, color=theme.INK_MUTED)),
            tickvals=[-1, -0.5, 0, 0.5, 1], ticktext=["100%", "50%", "0", "50%", "100%"],
            thickness=12, len=0.7, outlinewidth=0),
        hovertemplate=("<b>%{y} &#8594; %{x}</b><br>%{customdata[0]:,.0f} clientes"
                       "<br>%{customdata[1]:.1%} de los que estaban en %{y}<extra></extra>"),
    ))
    for i, yv in enumerate(ejes):
        for j, xv in enumerate(ejes):
            if cnt[i, j] > 0:
                fig.add_annotation(x=xv, y=yv, text=texto[i, j], showarrow=False,
                                   font=dict(size=10, color=tinta[i, j], family=theme.FONT))

    # Margen gris con lo que no es movimiento.
    fuera = (d[d["categoria"].isin(_FUERA)].groupby("categoria")["clientes"].sum()
             .reindex(_FUERA).fillna(0))
    etiquetas = {"entrada": "entrada", "ganancia_elegibilidad": "ganancia elegib.",
                 "salida": "salida", "perdida_elegibilidad": "pérdida elegib."}
    partes = [f"{etiquetas[k]}  <b>{theme.fmt_miles(v)}</b>" for k, v in fuera.items() if v > 0]
    if partes:
        fig.add_annotation(
            x=0, y=-0.20, xref="paper", yref="paper", xanchor="left", showarrow=False,
            align="left", text="Fuera de la matriz &nbsp;·&nbsp; " + " &nbsp;&nbsp; ".join(partes),
            font=dict(size=11, color=theme.GRIS_FUERA_ESCALA, family=theme.FONT))

    fig.update_layout(height=560)
    fig.update_xaxes(title_text="Grupo en el mes destino", side="top",
                     showline=False, ticks="")
    fig.update_yaxes(title_text="Grupo en el mes origen", autorange="reversed",
                     showgrid=False, showline=False, ticks="")
    return _t(fig)


def flujo_modelos(df: pd.DataFrame, producto: str | None = None) -> go.Figure:
    """Clientes que cambiaron de modelo entre los dos meses comparados.

    Es lo que separa reasignación de deriva. Si el PSI de un modelo sube y acá
    se ve un flujo grande hacia él, la población que le entró es nueva: el
    modelo no cambió, cambió a quién califica. La diagonal son los que se
    quedaron en el mismo modelo.
    """
    if df.empty or "modelo_anterior" not in df.columns:
        return _sin_datos("la tabla de migración no trae modelo_anterior; "
                          "hay que reconstruirla")
    d = df[df["categoria"] == "movimiento"].copy()
    if producto and producto != "todos":
        d = d[d["producto"] == producto]
    d = d[d["modelo_anterior"].notna() & d["modelo_actual"].notna()]
    if d.empty:
        return _sin_datos()

    m = (d.groupby(["modelo_anterior", "modelo_actual"], as_index=False)["clientes"]
         .sum())
    ejes = sorted(set(m["modelo_anterior"]) | set(m["modelo_actual"]))
    piv = (m.pivot(index="modelo_anterior", columns="modelo_actual",
                   values="clientes").reindex(index=ejes, columns=ejes))
    cnt = piv.fillna(0).values
    fila = cnt.sum(axis=1, keepdims=True)
    share = np.divide(cnt, fila, out=np.zeros_like(cnt, dtype=float), where=fila > 0)
    # Fuera de la diagonal es lo que interesa: la diagonal se apaga para que no
    # domine la escala, porque casi todos se quedan en su modelo.
    z = np.where(np.eye(len(ejes), dtype=bool), np.nan, share)

    fig = go.Figure(go.Heatmap(
        z=z, x=ejes, y=ejes, colorscale=theme.ESCALA_SECUENCIAL, zmin=0,
        xgap=3, ygap=3, customdata=cnt,
        colorbar=dict(title=dict(text="% del modelo<br>de origen",
                                 font=dict(size=10, color=theme.INK_MUTED)),
                      tickformat=".0%", thickness=12, len=0.7, outlinewidth=0),
        hovertemplate=("<b>%{y} &#8594; %{x}</b><br>%{customdata:,.0f} clientes"
                       "<br>%{z:.1%} de los que estaban en %{y}<extra></extra>"),
    ))
    for i, yv in enumerate(ejes):
        for j, xv in enumerate(ejes):
            if cnt[i, j] <= 0:
                continue
            diag = i == j
            fig.add_annotation(
                x=xv, y=yv, showarrow=False,
                text=theme.fmt_miles(cnt[i, j]),
                font=dict(size=9, family=theme.FONT,
                          color=theme.INK_MUTED if diag else
                          ("#ffffff" if share[i, j] > 0.55 else theme.INK)))
    fig.update_layout(height=max(380, 44 * len(ejes) + 190))
    fig.update_xaxes(title_text="Modelo en el mes actual", side="top",
                     showline=False, ticks="", type="category")
    fig.update_yaxes(title_text="Modelo en el mes anterior", autorange="reversed",
                     showgrid=False, showline=False, ticks="", type="category")
    fig.add_annotation(
        x=0, y=-0.14, xref="paper", yref="paper", xanchor="left", showarrow=False,
        text="La diagonal (los que no cambiaron de modelo) va sin color para "
             "que no domine la escala; el conteo sigue anotado.",
        font=dict(size=11, color=theme.INK_MUTED, family=theme.FONT))
    return _t(fig)


def estabilidad_deterioro(df: pd.DataFrame, producto: str) -> go.Figure:
    """Estabilidad (traza de la matriz) y deterioro neto en el tiempo."""
    if df.empty:
        return _sin_datos()
    s = serie_estabilidad(df, producto)
    if s.empty:
        return _sin_datos()
    etiquetas = [theme.etiqueta_mes_idx(m) for m in s["idx_mes"]]

    fig = go.Figure()
    fig.add_scatter(x=etiquetas, y=s["estabilidad"], name="Estabilidad (diagonal)",
                    mode="lines", line=dict(color=theme.SERIES[0], width=2, dash="solid"),
                    hovertemplate="Estabilidad · %{y:.1%}<extra></extra>")
    fig.add_scatter(x=etiquetas, y=s["deterioro_neto"], name="Deterioro neto",
                    mode="lines", line=dict(color=theme.SERIES[1], width=2, dash="dash"),
                    hovertemplate="Deterioro neto · %{y:.1%}<extra></extra>")
    fig.add_hline(y=0, line=dict(color=theme.AXIS, width=1))
    fig.update_layout(height=380)
    fig.update_xaxes(title_text="")
    fig.update_yaxes(title_text="Sobre los clientes con grupo en ambos meses",
                     tickformat=".0%")
    return _t(fig, unified=True)


def serie_estabilidad(df: pd.DataFrame, producto: str) -> pd.DataFrame:
    """Traza de la matriz y masa bajo menos masa sobre la diagonal, por mes."""
    if df.empty:
        return pd.DataFrame()
    d = df[df["producto"] == producto] if producto and producto != "todos" else df
    d = d[d["categoria"] == "movimiento"]
    if d.empty:
        return pd.DataFrame()
    o = d["grupo_base_origen"].map(theme.GRUPO_ORDEN)
    dst = d["grupo_base_destino"].map(theme.GRUPO_ORDEN)
    d = d.assign(_diag=(o == dst), _peor=(dst > o), _mejor=(dst < o))
    g = d.groupby("idx_mes").apply(
        lambda x: pd.Series({
            "estabilidad": x.loc[x["_diag"], "clientes"].sum() / x["clientes"].sum(),
            "deterioro_neto": (x.loc[x["_peor"], "clientes"].sum()
                               - x.loc[x["_mejor"], "clientes"].sum()) / x["clientes"].sum(),
        }), include_groups=False).reset_index()
    return g.sort_values("idx_mes")


def matriz_migracion_pd(df: pd.DataFrame, serie: str) -> go.Figure:
    """Matriz 10x10 de deciles de PD. Mismo color divergente que la de grupo,
    pero OJO: esto es reordenamiento del ranking, no desplazamiento de la
    distribución. Una diagonal fuerte acá no dice que la PD no se movió."""
    if df.empty:
        return _sin_datos()
    d = df[df["serie_pd"] == serie] if serie else df
    d = d[d["categoria"] == "movimiento"]
    if d.empty:
        return _sin_datos()

    ejes = list(range(1, 11))
    m = (d.groupby(["decil_origen", "decil_destino"], as_index=False)["clientes"].sum()
         .pivot(index="decil_origen", columns="decil_destino", values="clientes")
         .reindex(index=ejes, columns=ejes))
    cnt = m.fillna(0).values
    fila = cnt.sum(axis=1, keepdims=True)
    share = np.divide(cnt, fila, out=np.zeros_like(cnt, dtype=float), where=fila > 0)
    idx = np.arange(10)
    z = share * np.sign(idx[None, :] - idx[:, None])
    tinta = np.where(np.abs(z) > 0.45, "#ffffff", theme.INK)

    fig = go.Figure(go.Heatmap(
        z=z, x=ejes, y=ejes, zmid=0, zmin=-1, zmax=1,
        colorscale=theme.ESCALA_DIVERGENTE, xgap=2, ygap=2,
        customdata=np.stack([cnt, share], axis=-1),
        colorbar=dict(title=dict(text="baja  <->  sube<br>(% de la fila)",
                                 font=dict(size=10, color=theme.INK_MUTED)),
                      tickvals=[-1, 0, 1], ticktext=["100%", "0", "100%"],
                      thickness=12, len=0.7, outlinewidth=0),
        hovertemplate=("<b>decil %{y} &#8594; %{x}</b><br>%{customdata[0]:,.0f} clientes"
                       "<br>%{customdata[1]:.1%} del decil de origen<extra></extra>"),
    ))
    for i, yv in enumerate(ejes):
        for j, xv in enumerate(ejes):
            if share[i, j] >= 0.005:
                fig.add_annotation(x=xv, y=yv, text=f"{share[i, j]*100:.0f}", showarrow=False,
                                   font=dict(size=9, color=tinta[i, j], family=theme.FONT))
    fig.update_layout(height=540)
    fig.update_xaxes(title_text="Decil de PD en el mes destino", side="top",
                     showline=False, ticks="", dtick=1)
    fig.update_yaxes(title_text="Decil de PD en el mes origen", autorange="reversed",
                     showgrid=False, showline=False, ticks="", dtick=1)
    return _t(fig)


# ===========================================================================
# MODELOS
# ===========================================================================

def histograma_pd(df: pd.DataFrame, escala: str) -> go.Figure:
    """Histograma de PD por modelo, eje X logarítmico.

    Una traza por modelo, y las dos escalas NUNCA en el mismo eje: un modelo de
    puntaje 0-999 y uno de probabilidad no comparten unidad.
    """
    if df.empty:
        return _sin_datos()
    d = df[df["escala"] == escala]
    if d.empty:
        return _sin_datos(f"no hay modelos en escala {escala} en este mes")

    g = d.groupby(["modelo", "bin", "bin_min", "bin_max"], as_index=False)["clientes"].sum()
    g["share"] = g["clientes"] / g.groupby("modelo")["clientes"].transform("sum")
    modelos = g.groupby("modelo")["clientes"].sum().sort_values(ascending=False).index.tolist()

    fig = go.Figure()
    for i, mod in enumerate(modelos[:4]):
        s = g[g["modelo"] == mod].sort_values("bin_min")
        fig.add_scatter(
            x=s["bin_min"], y=s["share"], name=mod, mode="lines",
            line=dict(color=theme.SERIES[i % 4], width=2,
                      dash=theme.SERIES_DASH[i % 4], shape="hv"),
            customdata=np.stack([s["clientes"], s["bin_max"]], axis=-1),
            hovertemplate=(mod + "<br>PD %{x:.4f} a %{customdata[1]:.4f}"
                           "<br>%{y:.1%} de la población · %{customdata[0]:,.0f} clientes"
                           "<extra></extra>"),
        )
    unidad = "Puntaje (0 a 999)" if escala == "puntaje_0_999" else "Probabilidad de default"
    fig.update_layout(height=400)
    fig.update_xaxes(title_text=f"{unidad} — escala logarítmica", type="log")
    fig.update_yaxes(title_text="Participación de la población del modelo",
                     tickformat=".1%", rangemode="tozero")
    return _t(fig)


# ---------------------------------------------------------------------------
# PSI -- tres niveles
# ---------------------------------------------------------------------------
# El PSI que había era uno solo, sobre bins de PD y partido por modelo. Medía
# algo distinto de lo que parecía: si un modelo se lleva la población de otro,
# el PSI de los dos se dispara sin que ninguno haya cambiado. Eso es
# REASIGNACIÓN de población entre modelos, no deriva de un modelo.
#
# La estructura de tres niveles separa las preguntas:
#
#   1. General     PSI de grupos G1-G8 sobre toda la población, por producto.
#                  ¿Se está moviendo el riesgo del banco? Es el que decide.
#   2. Por modelo  El mismo PSI de grupos, filtrado a un modelo.
#                  ¿Qué población le está entrando a este modelo?
#   3. PD          PSI sobre bins de PD. ¿Se movió la PD sin cruzar cortes?
#
# El nivel 1 es el que dispara acción; 2 y 3 explican, no deciden.

MIN_PESO_BIN = 0.001   # 0,1% -- ver psi_pd()


def _psi_par(base: pd.Series, act: pd.Series) -> float:
    """PSI entre dos distribuciones ya normalizadas y alineadas."""
    return float(((act - base) * np.log(act / base)).sum())


def psi_grupos(df: pd.DataFrame, producto: str | None = None,
               modelo: str | None = None, columna: str = "grupo_base",
               base_movil: bool = False) -> pd.DataFrame:
    """PSI sobre la distribución de GRUPOS, que es la unidad con la que se
    oferta. Sale de distribucion_grupo.

    `base_movil=False` compara contra el primer mes de la ventana (deriva
    acumulada); `True`, contra el mes anterior (cambio mensual).
    """
    if df.empty or columna not in df.columns:
        return pd.DataFrame()
    d = df
    if producto and producto != "todos":
        d = d[d["producto"] == producto]
    if modelo and modelo != "todos":
        d = d[d["modelo"] == modelo]
    d = d[d[columna].notna()]
    if d.empty:
        return pd.DataFrame()

    g = d.groupby(["idx_mes", columna], as_index=False)["clientes"].sum()
    g["p"] = g["clientes"] / g.groupby("idx_mes")["clientes"].transform("sum")
    meses = sorted(g["idx_mes"].unique())
    if len(meses) < 2:
        return pd.DataFrame()

    filas = []
    for k, m in enumerate(meses[1:], start=1):
        ref = meses[k - 1] if base_movil else meses[0]
        b = g[g["idx_mes"] == ref].set_index(columna)["p"]
        a = g[g["idx_mes"] == m].set_index(columna)["p"]
        idx = b.index.union(a.index)
        # Los grupos son pocos y estables: un epsilon acá no distorsiona como
        # sí lo hace en los bins de PD.
        b2 = b.reindex(idx).fillna(0).clip(lower=1e-6)
        a2 = a.reindex(idx).fillna(0).clip(lower=1e-6)
        filas.append({"idx_mes": m, "idx_base": ref, "psi": _psi_par(b2, a2)})
    return pd.DataFrame(filas)


def aporte_psi_grupo(df: pd.DataFrame, idx_mes: int, producto: str | None = None,
                     modelo: str | None = None, columna: str = "grupo_base",
                     base_movil: bool = False) -> pd.DataFrame:
    """Cuánto aporta cada grupo al PSI de un mes.

    Convierte "el PSI subió a 0,31" en "subió porque G5 pasó de 8% a 14%".
    """
    if df.empty or columna not in df.columns:
        return pd.DataFrame()
    d = df
    if producto and producto != "todos":
        d = d[d["producto"] == producto]
    if modelo and modelo != "todos":
        d = d[d["modelo"] == modelo]
    d = d[d[columna].notna()]
    if d.empty:
        return pd.DataFrame()
    g = d.groupby(["idx_mes", columna], as_index=False)["clientes"].sum()
    g["p"] = g["clientes"] / g.groupby("idx_mes")["clientes"].transform("sum")
    meses = sorted(g["idx_mes"].unique())
    if idx_mes not in meses or len(meses) < 2:
        return pd.DataFrame()
    k = meses.index(idx_mes)
    if k == 0:
        return pd.DataFrame()
    ref = meses[k - 1] if base_movil else meses[0]
    b = g[g["idx_mes"] == ref].set_index(columna)["p"]
    a = g[g["idx_mes"] == idx_mes].set_index(columna)["p"]
    idx = _grupos_ordenados(b.index.union(a.index))
    b2 = b.reindex(idx).fillna(0).clip(lower=1e-6)
    a2 = a.reindex(idx).fillna(0).clip(lower=1e-6)
    ap = (a2 - b2) * np.log(a2 / b2)
    return pd.DataFrame({
        "grupo": idx,
        "% en la base": [b.reindex(idx).fillna(0).loc[x] for x in idx],
        "% en el mes": [a.reindex(idx).fillna(0).loc[x] for x in idx],
        "aporte al PSI": [ap.loc[x] for x in idx],
    }).sort_values("aporte al PSI", ascending=False).reset_index(drop=True)


def psi_pd(df: pd.DataFrame, serie: str, base_movil: bool = False
           ) -> tuple[pd.DataFrame, int]:
    """PSI sobre bins de PD. Devuelve (serie, bins_descartados).

    Descarta los bins con menos de MIN_PESO_BIN de población en CUALQUIERA de
    los dos meses y renormaliza sobre los que quedan.

    La versión anterior metía un epsilon de 1e-6 en los bins vacíos, y eso
    inflaba el resultado: ln(p/1e-6) es enorme, y con 20 bins por década hay
    muchos bins de cola con poblaciones diminutas. Un puñado de clientes
    moviéndose entre dos bins irrelevantes producía un PSI de 1,5 sostenido,
    que es el valor irreal que se veía.
    """
    if df.empty:
        return pd.DataFrame(), 0
    d = df[df["serie_pd"] == serie] if serie else df
    if d.empty:
        return pd.DataFrame(), 0
    g = d.groupby(["modelo", "idx_mes", "bin"], as_index=False)["clientes"].sum()
    g["p"] = g["clientes"] / g.groupby(["modelo", "idx_mes"])["clientes"].transform("sum")

    filas, descartados = [], 0
    for mod, sub in g.groupby("modelo"):
        meses = sorted(sub["idx_mes"].unique())
        if len(meses) < 2:
            continue
        for k, m in enumerate(meses[1:], start=1):
            ref = meses[k - 1] if base_movil else meses[0]
            b = sub[sub["idx_mes"] == ref].set_index("bin")["p"]
            a = sub[sub["idx_mes"] == m].set_index("bin")["p"]
            idx = b.index.union(a.index)
            b = b.reindex(idx).fillna(0)
            a = a.reindex(idx).fillna(0)
            vivos = (b >= MIN_PESO_BIN) & (a >= MIN_PESO_BIN)
            descartados += int((~vivos).sum())
            if vivos.sum() < 2:
                continue
            b2, a2 = b[vivos], a[vivos]
            b2, a2 = b2 / b2.sum(), a2 / a2.sum()   # renormalizar
            filas.append({"modelo": mod, "idx_mes": m, "idx_base": ref,
                          "psi": _psi_par(b2, a2), "bins": int(vivos.sum())})
    return pd.DataFrame(filas), descartados


def _grafico_psi(s: pd.DataFrame, columna_serie: str, titulo_y: str,
                 max_series: int = 4) -> tuple[go.Figure, int, int]:
    """Líneas de PSI con los umbrales. Devuelve (fig, mostradas, totales)."""
    if s.empty:
        return _sin_datos("hacen falta al menos dos meses para calcular PSI"), 0, 0
    meses = sorted(s["idx_mes"].unique())
    etiquetas = [theme.etiqueta_mes_idx(m) for m in meses]
    orden = s.groupby(columna_serie)["psi"].max().sort_values(ascending=False)
    todas = len(orden)
    elegidas = orden.index.tolist()[:max_series]

    fig = go.Figure()
    for i, nombre in enumerate(elegidas):
        sub = s[s[columna_serie] == nombre].set_index("idx_mes").reindex(meses)
        fig.add_scatter(
            x=etiquetas, y=sub["psi"].values, name=str(nombre),
            mode="lines+markers",
            line=dict(color=theme.SERIES[i % 4], width=2,
                      dash=theme.SERIES_DASH[i % 4]),
            marker=dict(size=8, line=dict(color=theme.SURFACE, width=2)),
            hovertemplate=f"{nombre} · PSI %{{y:.3f}}<extra></extra>")
    for val, txt, col in ((0.10, "0,10  revisar", theme.ESTADO_ALERTA),
                          (0.25, "0,25  severo", theme.ESTADO_CRITICO)):
        fig.add_hline(y=val, line=dict(color=col, width=1, dash="dot"), opacity=0.55)
        fig.add_annotation(x=1, y=val, xref="paper", yref="y", xanchor="left",
                           xshift=6, showarrow=False, text=txt,
                           font=dict(size=10, color=col, family=theme.FONT))
    fig.update_layout(height=400, margin=dict(r=140))
    fig.update_xaxes(title_text="", categoryorder="array", categoryarray=etiquetas)
    fig.update_yaxes(title_text=titulo_y, rangemode="tozero")
    return _t(fig, unified=True), len(elegidas), todas


def psi_grupos_grafico(df, producto=None, modelo=None, columna="grupo_base",
                       base_movil=False):
    s = psi_grupos(df, producto, modelo, columna, base_movil)
    if s.empty:
        return _sin_datos("hacen falta al menos dos meses"), 0, 0
    s = s.assign(_serie=producto or "todos")
    return _grafico_psi(s, "_serie", "PSI sobre la distribución de grupos", 1)


def psi_pd_grafico(df, serie, base_movil=False, max_series=4):
    s, desc = psi_pd(df, serie, base_movil)
    fig, n, tot = _grafico_psi(s, "modelo", "PSI sobre bins de PD", max_series)
    return fig, n, tot, desc


def sensibilidad_cortes(df: pd.DataFrame, modelo: str | None = None) -> go.Figure:
    """Dónde cae cada frontera G1-G8, por producto, sobre la PD en escala log.

    Es el visual que motivó salir de Power BI. Cada producto es una fila; cada
    grupo, una banda entre su pd_min y su pd_max, coloreada por la rampa de
    riesgo. Como todos los productos traducen la MISMA PD, las bandas se pueden
    comparar verticalmente: un corte desplazado se ve como una banda corrida
    respecto de la fila de al lado.

    Donde dos grupos consecutivos se solapan hay un marcador rojo: dos clientes
    con la misma PD quedaron en grupos distintos, así que el corte no depende
    solo de la PD.
    """
    if df.empty:
        return _sin_datos()
    d = df.copy()
    if modelo and modelo != "todos":
        d = d[d["modelo"] == modelo]
    d = d[(d["pd_min"] > 0) & d["pd_max"].notna()]
    if d.empty:
        return _sin_datos()

    d = d.sort_values(["producto", "pd_min"])
    productos = sorted(d["producto"].unique(),
                       key=lambda p: (_FAM.get(p, "zz"), p), reverse=True)
    ypos = {p: i for i, p in enumerate(productos)}

    fig = go.Figure()
    # Se recorre por GRUPO en orden canónico, no por fila. Iterando el
    # DataFrame, la leyenda salía en el orden en que aparecía cada grupo por
    # primera vez -- que depende del producto que estuviera arriba -- y las G
    # quedaban desordenadas.
    for grupo in _grupos_ordenados(d["grupo"]):
        sub = d[d["grupo"] == grupo]
        primera = True
        for _, r in sub.iterrows():
            y = ypos[r["producto"]]
            fig.add_scatter(
                x=[r["pd_min"], r["pd_max"]], y=[y, y], mode="lines",
                line=dict(color=theme.COLOR_GRUPO.get(grupo, theme.INK_MUTED),
                          width=11),
                opacity=0.95, name=grupo, legendgroup=grupo,
                showlegend=primera,
                hovertemplate=(f"<b>{r['producto']}</b> · {grupo}"
                               f"<br>PD de {theme.fmt_pd(r['pd_min'])} "
                               f"a {theme.fmt_pd(r['pd_max'])}"
                               f"<br>{theme.fmt_miles(r['clientes'])} clientes"
                               f"<extra></extra>"),
            )
            primera = False

    sol = d[d["solapa"].fillna(False).astype(bool)]
    if not sol.empty:
        fig.add_scatter(
            x=sol["pd_min"], y=[ypos[p] for p in sol["producto"]], mode="markers",
            name="corte solapado", legendgroup="solapa",
            marker=dict(symbol="x", size=9, color=theme.ESTADO_CRITICO,
                        line=dict(width=1.5, color=theme.SURFACE)),
            customdata=np.stack([sol["producto"], sol["grupo"]], axis=-1),
            hovertemplate=("<b>solapamiento</b><br>%{customdata[0]} · %{customdata[1]}"
                           "<br>arranca por debajo del máximo del grupo anterior"
                           "<extra></extra>"),
        )

    fig.update_layout(height=max(420, 30 * len(productos) + 170),
                      legend_traceorder="normal")
    fig.update_xaxes(title_text="Probabilidad de default — escala logarítmica", type="log")
    fig.update_yaxes(title_text="", tickmode="array",
                     tickvals=list(ypos.values()), ticktext=list(ypos.keys()),
                     showgrid=False, showline=False, ticks="")
    return _t(fig)


# ===========================================================================
# TABLAS -- alertas de calidad, no gráficos
# ===========================================================================

def tabla_solapamientos(df: pd.DataFrame) -> pd.DataFrame:
    """Cortes cuyo rango se cruza con el del grupo anterior.

    No es necesariamente un error: puede ser una regla de negocio. Pero cambia
    cómo se lee todo el tablero, así que tiene que ser una decisión conocida.
    """
    if df.empty or "solapa" not in df.columns:
        return pd.DataFrame()
    s = df[df["solapa"].fillna(False).astype(bool)].copy()
    if s.empty:
        return pd.DataFrame()
    s["solapamiento"] = s["pd_max_grupo_previo"] - s["pd_min"]
    out = s[["mes", "producto", "modelo", "grupo", "pd_min", "pd_max",
             "pd_max_grupo_previo", "solapamiento", "clientes"]]
    return out.sort_values(["solapamiento"], ascending=False).reset_index(drop=True)


def tabla_peores_saltos(df: pd.DataFrame, minimo: int = 3) -> pd.DataFrame:
    """Combinaciones origen -> destino con caída de `minimo` grupos o más,
    ordenadas por volumen."""
    if df.empty:
        return pd.DataFrame()
    d = df[df["categoria"] == "movimiento"].copy()
    if d.empty:
        return pd.DataFrame()
    d["_o"] = d["grupo_base_origen"].map(theme.GRUPO_ORDEN) // 10
    d["_d"] = d["grupo_base_destino"].map(theme.GRUPO_ORDEN) // 10
    d["saltos"] = d["_d"] - d["_o"]
    d = d[d["saltos"] >= minimo]
    if d.empty:
        return pd.DataFrame()
    g = (d.groupby(["mes", "producto", "grupo_base_origen", "grupo_base_destino", "saltos"],
                   as_index=False)["clientes"].sum())
    return g.sort_values("clientes", ascending=False).reset_index(drop=True)


# ===========================================================================
# SALUD DEL DATO -- estado de las consultas de sql/00_perfilado/
# ===========================================================================
# Cada chequeo devuelve un `Chequeo`: verde o rojo, una línea de explicación y
# la tabla completa, que la UI solo despliega si el chequeo falla. Viven acá y
# no en la página para que el export los reuse tal cual: mismo veredicto en la
# app y en el HTML.

@dataclass
class Chequeo:
    """Resultado de un chequeo. El estado es de TRES valores, no de dos.

    `ejecutado=False` es distinto de `ok=False`: un chequeo que no corrió no
    afirma nada. Antes esto se marcaba con un centinela en `nota`, que el
    banner global no miraba, así que un chequeo sin ejecutar contaba como
    aprobado. Es un campo propio justamente para que no se pueda ignorar.
    """
    nombre: str
    ok: bool
    resumen: str
    detalle: pd.DataFrame | None = None
    nota: str = ""
    ejecutado: bool = True

    @property
    def estado(self) -> str:
        if not self.ejecutado:
            return "SIN EJECUTAR"
        return "OK" if self.ok else "REVISAR"

    @property
    def color(self) -> str:
        if not self.ejecutado:
            return theme.INK_MUTED
        return theme.ESTADO_OK if self.ok else theme.ESTADO_CRITICO

    @property
    def icono(self) -> str:
        if not self.ejecutado:
            return "○"
        return "●" if self.ok else "▲"


def resumen_global(chequeos: list[Chequeo]) -> tuple[str, str, bool]:
    """Cuenta los tres estados por separado y arma el mensaje del banner.

    Devuelve (nivel, mensaje, todo_verde). El nivel es 'ok', 'alerta' o
    'aviso'. **Solo es verde si los cuatro se ejecutaron y los cuatro
    pasaron**: un archivo que afirma que todo está bien sin haber corrido un
    chequeo está diciendo algo que no verificó.
    """
    total = len(chequeos)
    fallan = [c for c in chequeos if c.ejecutado and not c.ok]
    sin_correr = [c for c in chequeos if not c.ejecutado]
    pasan = total - len(fallan) - len(sin_correr)

    if fallan:
        partes = [f"{len(fallan)} de {total} chequeos piden revisión"]
        if sin_correr:
            partes.append(f"{len(sin_correr)} sin ejecutar")
        return ("alerta", ", ".join(partes) + ". Los números de las otras "
                "páginas pueden no significar lo que parecen.", False)
    if sin_correr:
        return ("aviso",
                f"{pasan} de {total} chequeos pasan, {len(sin_correr)} sin "
                f"ejecutar ({', '.join(c.nombre for c in sin_correr)}). "
                f"Mientras no corra, no hay nada verificado sobre ese punto.",
                False)
    return ("ok", f"Los {total} chequeos pasan. Los supuestos sobre los que se "
            f"apoya el resto del tablero se sostienen en esta ventana.", True)


def chequeo_ingestion_day(df: pd.DataFrame) -> Chequeo:
    """1. Un solo ingestion_day por mes.

    Todo el repo asume una fila por cliente + mes: sin eso, cada `count(*)`
    duplica en silencio. Ver CLAUDE.md, "La deduplicación por ingestion_day NO
    se hace en SQL".
    """
    if df.empty:
        return Chequeo("Un solo ingestion_day por mes", False,
                       "La consulta no devolvió filas: no se pudo verificar.")
    malos = df[df["dias_distintos"] > 1]
    if malos.empty:
        return Chequeo(
            "Un solo ingestion_day por mes", True,
            f"Los {len(df)} meses de la ventana traen una sola ingestión. "
            f"La premisa de una fila por cliente y mes se sostiene.")
    return Chequeo(
        "Un solo ingestion_day por mes", False,
        f"{len(malos)} de {len(df)} meses traen más de una ingestión. Los "
        f"conteos de esos meses están duplicados: hay que borrar la ingestión "
        f"sobrante antes de mirar cualquier otro número.",
        malos[["mes", "dias_distintos", "primer_dia", "ultimo_dia"]])


def chequeo_mapeo(df: pd.DataFrame) -> Chequeo:
    """2. El mapeo idx -> columna del unpivot está alineado.

    Un CASE desalineado no da error: etiqueta los datos con el producto
    equivocado. Contar por los dos caminos y comparar es la única forma de
    atraparlo.
    """
    nota = ("Es la consulta más lenta de la página: el lado ancho son 16 "
            "agregados, uno por producto, sobre la misma partición. Se corre "
            "sobre un solo mes por eso.")
    if df.empty:
        return Chequeo("Mapeo idx → columna alineado", False,
                       "La consulta no devolvió filas: no se pudo verificar.",
                       nota=nota)
    malos = df[df["diferencia"] != 0]
    if malos.empty:
        return Chequeo(
            "Mapeo idx → columna alineado", True,
            f"Los {len(df)} productos cuadran exactamente entre la tabla ancha "
            f"y la larga. El unpivot está etiquetando bien.", nota=nota)
    return Chequeo(
        "Mapeo idx → columna alineado", False,
        f"{len(malos)} de {len(df)} productos NO cuadran. Hay un CASE "
        f"desalineado en el unpivot: los datos están bien contados pero mal "
        f"etiquetados, así que todo el tablero atribuye clientes al producto "
        f"equivocado.", malos, nota=nota)


def chequeo_dominio(grupos: pd.DataFrame, modelos: pd.DataFrame,
                    conocidos: set[str]) -> Chequeo:
    """3. Dominio de grupos y modelos sin novedades."""
    esperados = set(theme.GRUPOS_ORDENADOS)
    g_raros = pd.DataFrame()
    if not grupos.empty:
        g_raros = grupos[~grupos["grupo"].isin(esperados)]

    m_raros = pd.DataFrame()
    if not modelos.empty:
        m = modelos.copy()
        m["modelo"] = m["modelo"].fillna("").str.strip()
        # El modelo vacío es conocido: es ausencia de modelo, no una novedad.
        m_raros = (m[(m["modelo"] != "") & (~m["modelo"].isin(conocidos))]
                   .groupby("modelo", as_index=False)
                   .agg(productos=("producto", "nunique"),
                        pd_min=("pd_min", "min"), pd_max=("pd_max", "max"),
                        desde=("mes", "first")))

    if g_raros.empty and m_raros.empty:
        return Chequeo(
            "Dominio de grupos y modelos sin novedades", True,
            f"Los grupos caen todos dentro de G1–G8 y las seis aperturas de "
            f"sufi. Los modelos son los {len(conocidos)} conocidos.")

    # Los modelos desconocidos se listan SIEMPRE en el resumen, no solo en el
    # detalle desplegable: son el dato accionable. Al 2026-09-01 ya se vieron
    # T2_HIP, T3_HIP, T3_SOCIAL y T2_SOCIAL en las leyendas, que no están en la
    # lista de ocho de CLAUDE.md. Pendiente de confirmar cuáles son los reales.
    nombres_raros = sorted(m_raros["modelo"].tolist()) if not m_raros.empty else []

    partes, detalle = [], []
    if not g_raros.empty:
        partes.append(f"{g_raros['grupo'].nunique()} valores de grupo fuera de "
                      f"G1–G8 y las aperturas conocidas")
        detalle.append(g_raros.assign(hallazgo="grupo desconocido"))
    if not m_raros.empty:
        escala = m_raros[m_raros["pd_max"] > 1]
        partes.append(f"{len(m_raros)} modelos que no están en la lista")
        if not escala.empty:
            partes.append(
                f"y {len(escala)} de ellos vienen en escala de PUNTAJE "
                f"(pd_max > 1): hay que agregarlos a la lista de "
                f"pd_por_modelo.sql o sus bins salen mal sin dar síntoma")
        detalle.append(m_raros.assign(hallazgo="modelo desconocido"))

    resumen = "Aparecieron " + ", ".join(partes) + "."
    if nombres_raros:
        resumen += (" Los modelos fuera de la lista son: "
                    + ", ".join(f"**{m}**" for m in nombres_raros) + ".")
    resumen += (" Un modelo nuevo no es un error en sí: es una novedad que hay "
                "que mirar antes de confiar en el histograma de PD, y que hay "
                "que reflejar en la lista de CLAUDE.md.")
    return Chequeo(
        "Dominio de grupos y modelos sin novedades", False, resumen,
        pd.concat(detalle, ignore_index=True) if detalle else None)


def chequeo_pd_grupo(df: pd.DataFrame) -> Chequeo:
    """4. PD y grupo concuerdan.

    Las filas con pd nula y grupo poblado existen (~726 en un mes) y no son un
    error: el filtro del tablero es por grupo. Lo que importa es que no
    crezcan, porque eso indicaría que la replicación de PD se está degradando.
    """
    if df.empty:
        return Chequeo("PD y grupo concuerdan", False,
                       "La consulta no devolvió filas: no se pudo verificar.")
    por_mes = (df.groupby(["idx_mes", "mes"], as_index=False)["pd_nulo_grupo_no_nulo"]
               .sum().sort_values("idx_mes"))
    ultimo = por_mes.iloc[-1]
    n = int(ultimo["pd_nulo_grupo_no_nulo"])
    if len(por_mes) < 2:
        return Chequeo(
            "PD y grupo concuerdan", True,
            f"{theme.fmt_miles(n)} filas con PD nula y grupo poblado en "
            f"{ultimo['mes']}. Con un solo mes en la ventana no hay contra qué "
            f"comparar la tendencia.")
    previo = int(por_mes.iloc[-2]["pd_nulo_grupo_no_nulo"])
    if n <= previo:
        return Chequeo(
            "PD y grupo concuerdan", True,
            f"{theme.fmt_miles(n)} filas con PD nula y grupo poblado en "
            f"{ultimo['mes']}, contra {theme.fmt_miles(previo)} el mes "
            f"anterior. No crece: la replicación de PD se sostiene.")
    return Chequeo(
        "PD y grupo concuerdan", False,
        f"La discordancia CRECIÓ: {theme.fmt_miles(n)} filas en "
        f"{ultimo['mes']} contra {theme.fmt_miles(previo)} el mes anterior "
        f"(+{theme.fmt_miles(n - previo)}). Que existan no es un problema; que "
        f"aumenten sugiere que el proceso que replica la PD se está degradando.",
        (df[df["idx_mes"] == ultimo["idx_mes"]]
         [["mes", "producto", "filas_totales", "pd_nulo_grupo_no_nulo",
           "pd_no_nulo_grupo_nulo"]]
         .sort_values("pd_nulo_grupo_no_nulo", ascending=False)))


def discordancia_pd_grupo(df: pd.DataFrame) -> go.Figure:
    """Filas con PD nula y grupo poblado, por mes y producto.

    Es el único de los cuatro chequeos donde la tendencia dice algo: los otros
    tres son binarios. Si esta línea sube, la replicación de PD se degrada.

    Va SIEMPRE abierto por producto, nunca agregado en una sola serie. Hoy la
    discordancia está concentrada en un producto: si mañana aparece en otro, un
    total agregado podría no moverse lo suficiente para que se note, que es
    justo el caso que este gráfico existe para detectar.

    Solo entran los productos con algún valor distinto de cero en la ventana.
    Los que están en cero todo el tiempo quedan fuera de la leyenda, para que
    el gráfico no se llene de líneas planas donde no hay nada que mirar.
    """
    if df.empty:
        return _sin_datos()
    meses = sorted(df["idx_mes"].unique())
    etiquetas = [theme.etiqueta_mes_idx(m) for m in meses]

    # Productos con discordancia en ALGÚN mes. El filtro es sobre el total de
    # la ventana, no fila a fila: así un producto que tiene meses en cero
    # conserva esos ceros en su línea, en vez de quedar con huecos.
    total = (df.groupby("producto")["pd_nulo_grupo_no_nulo"].sum()
             .sort_values(ascending=False))
    activos = total[total > 0].index.tolist()
    if not activos:
        return _sin_datos("ningún producto con PD nula y grupo poblado "
                          "en esta ventana")

    principales, resto = activos[:4], activos[4:]
    fig = go.Figure()
    for i, prod in enumerate(principales):
        s = (df[df["producto"] == prod].groupby("idx_mes")["pd_nulo_grupo_no_nulo"]
             .sum().reindex(meses).fillna(0))
        fig.add_scatter(
            x=etiquetas, y=s.values, name=prod, mode="lines+markers",
            line=dict(color=theme.SERIES[i], width=2, dash=theme.SERIES_DASH[i]),
            marker=dict(size=7, line=dict(color=theme.SURFACE, width=2)),
            hovertemplate=prod + " · %{y:,.0f} filas<extra></extra>")
    if resto:
        # Más de cuatro productos con discordancia ya es de por sí una señal:
        # se agregan para no salir de la paleta, pero el gráfico lo dice.
        s = (df[df["producto"].isin(resto)].groupby("idx_mes")["pd_nulo_grupo_no_nulo"]
             .sum().reindex(meses).fillna(0))
        fig.add_scatter(x=etiquetas, y=s.values,
                        name=f"otros {len(resto)} productos", mode="lines",
                        line=dict(color=theme.INK_MUTED, width=1.5, dash="dot"),
                        hovertemplate="otros · %{y:,.0f} filas<extra></extra>")
        fig.add_annotation(
            x=0, y=-0.22, xref="paper", yref="paper", xanchor="left",
            showarrow=False,
            text=f"Hay {len(activos)} productos con discordancia: "
                 f"{len(resto)} van agregados en «otros».",
            font=dict(size=11, color=theme.ESTADO_ALERTA, family=theme.FONT))

    fig.update_layout(height=360)
    fig.update_xaxes(title_text="")
    fig.update_yaxes(title_text="Filas con PD nula y grupo poblado",
                     tickformat=",.0f", rangemode="tozero")
    return _t(fig, unified=True)


_FAM = {
    "consumo": "consumo", "tdc": "consumo", "libranza": "consumo",
    "rotativo": "consumo", "calm": "consumo",
    "hip_vis": "vivienda", "hip_novis": "vivienda",
    "lea_hab_vis": "vivienda", "lea_hab_novis": "vivienda",
    "comercial": "comercial", "micro": "comercial", "sobregiro": "comercial",
    "sufi_veh": "sufi", "sufi_moto": "sufi", "sufi_cpe": "sufi", "sufi_con": "sufi",
}
