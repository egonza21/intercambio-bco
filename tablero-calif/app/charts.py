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
    """Los grupos presentes, ordenados por grupo_orden. Nunca por el orden en
    que llegaron los datos ni alfabéticamente: G7_A iría antes que G7_B."""
    return sorted(set(valores), key=lambda g: theme.GRUPO_ORDEN.get(g, 999))


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

    g = d.groupby(["segmento", "grupo"], as_index=False)["clientes"].sum()
    g["share"] = g["clientes"] / g.groupby("segmento")["clientes"].transform("sum")
    cols = _grupos_ordenados(g["grupo"])
    piv = g.pivot(index="segmento", columns="grupo", values="share").reindex(columns=cols)
    cnt = g.pivot(index="segmento", columns="grupo", values="clientes").reindex(columns=cols)
    # Segmentos por tamaño: el más grande arriba, para que la lectura no
    # dependa del alfabeto.
    orden_seg = (g.groupby("segmento")["clientes"].sum().sort_values(ascending=False)
                 .index.tolist())
    piv, cnt = piv.reindex(orden_seg), cnt.reindex(orden_seg)

    if normalizar:
        z, extra, fmt, titulo = piv.values, cnt.values, ".0%", "% del<br>segmento"
        linea_z = "%{z:.1%} del segmento<br>%{customdata:,.0f} clientes"
    else:
        z, extra, fmt, titulo = cnt.values, piv.values, ",.0f", "clientes"
        linea_z = "%{z:,.0f} clientes<br>%{customdata:.1%} del segmento"

    fig = go.Figure(go.Heatmap(
        z=z, x=cols, y=piv.index.tolist(),
        colorscale=theme.ESCALA_SECUENCIAL, zmin=0,
        xgap=2, ygap=2, customdata=extra,
        colorbar=dict(title=dict(text=titulo, font=dict(size=11)),
                      tickformat=fmt, thickness=12, len=0.75, outlinewidth=0),
        hovertemplate=("Segmento <b>%{y}</b> · grupo <b>%{x}</b><br>"
                       + linea_z + "<extra></extra>"),
    ))
    fig.update_layout(height=max(320, 40 * len(piv.index) + 150))
    # categoryorder explícito en los dos ejes: ni el grupo ni el segmento se
    # ordenan por el orden en que llegan los datos.
    fig.update_xaxes(title_text="Grupo de riesgo", showline=False, ticks="",
                     categoryorder="array", categoryarray=cols)
    fig.update_yaxes(title_text="", showgrid=False, showline=False, ticks="",
                     categoryorder="array", categoryarray=list(reversed(orden_seg)))
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


def psi_series(df: pd.DataFrame, serie: str) -> pd.DataFrame:
    """PSI por modelo contra el primer mes de la ventana.

    Los bins vienen de ancho fijo desde el SQL, que es la condición para que el
    PSI signifique algo: si los bordes se recalcularan por período, daría ~0
    siempre.
    """
    if df.empty:
        return pd.DataFrame()
    d = df[df["serie_pd"] == serie] if serie else df
    if d.empty:
        return pd.DataFrame()
    g = d.groupby(["modelo", "idx_mes", "bin"], as_index=False)["clientes"].sum()
    g["p"] = g["clientes"] / g.groupby(["modelo", "idx_mes"])["clientes"].transform("sum")

    filas = []
    for mod, sub in g.groupby("modelo"):
        meses = sorted(sub["idx_mes"].unique())
        if len(meses) < 2:
            continue
        base = sub[sub["idx_mes"] == meses[0]].set_index("bin")["p"]
        for m in meses[1:]:
            act = sub[sub["idx_mes"] == m].set_index("bin")["p"]
            bins = base.index.union(act.index)
            # Epsilon en los bins vacíos: sin él, un bin nuevo da división por
            # cero y el PSI sale infinito.
            eps = 1e-6
            b = base.reindex(bins).fillna(0).clip(lower=eps)
            a = act.reindex(bins).fillna(0).clip(lower=eps)
            filas.append({"modelo": mod, "idx_mes": m,
                          "psi": float(((a - b) * np.log(a / b)).sum())})
    return pd.DataFrame(filas)


def psi_tiempo(df: pd.DataFrame, serie: str) -> go.Figure:
    """PSI por modelo con los umbrales de 0,1 y 0,25 como líneas tenues
    anotadas al extremo derecho, no como series de la leyenda."""
    s = psi_series(df, serie)
    if s.empty:
        return _sin_datos("hacen falta al menos dos meses para calcular PSI")
    meses = sorted(s["idx_mes"].unique())
    etiquetas = [theme.etiqueta_mes_idx(m) for m in meses]

    fig = go.Figure()
    for i, mod in enumerate(s.groupby("modelo")["psi"].max().sort_values(ascending=False)
                            .index.tolist()[:4]):
        sub = s[s["modelo"] == mod].set_index("idx_mes").reindex(meses)
        fig.add_scatter(
            x=etiquetas, y=sub["psi"].values, name=mod, mode="lines+markers",
            line=dict(color=theme.SERIES[i], width=2, dash=theme.SERIES_DASH[i]),
            marker=dict(size=8, line=dict(color=theme.SURFACE, width=2)),
            hovertemplate=mod + " · PSI %{y:.3f}<extra></extra>",
        )
    for val, txt, col in ((0.10, "0,10  cambio moderado", theme.ESTADO_ALERTA),
                          (0.25, "0,25  cambio severo", theme.ESTADO_CRITICO)):
        fig.add_hline(y=val, line=dict(color=col, width=1, dash="dot"), opacity=0.55)
        fig.add_annotation(x=1, y=val, xref="paper", yref="y", xanchor="left",
                           xshift=6, showarrow=False, text=txt,
                           font=dict(size=10, color=col, family=theme.FONT))
    fig.update_layout(height=400, margin=dict(r=150))
    fig.update_xaxes(title_text="")
    fig.update_yaxes(title_text="PSI contra el primer mes de la ventana",
                     rangemode="tozero")
    return _t(fig, unified=True)


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
    vistos: set[str] = set()
    for _, r in d.iterrows():
        y = ypos[r["producto"]]
        color = theme.COLOR_GRUPO.get(r["grupo"], theme.INK_MUTED)
        fig.add_scatter(
            x=[r["pd_min"], r["pd_max"]], y=[y, y], mode="lines",
            line=dict(color=color, width=11), opacity=0.95,
            name=r["grupo"], legendgroup=r["grupo"],
            showlegend=r["grupo"] not in vistos,
            hovertemplate=(f"<b>{r['producto']}</b> · {r['grupo']}"
                           f"<br>PD de {theme.fmt_pd(r['pd_min'])} "
                           f"a {theme.fmt_pd(r['pd_max'])}"
                           f"<br>{theme.fmt_miles(r['clientes'])} clientes<extra></extra>"),
        )
        vistos.add(r["grupo"])

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

    return Chequeo(
        "Dominio de grupos y modelos sin novedades", False,
        "Aparecieron " + ", ".join(partes) + ". Un modelo nuevo no es un error "
        "en sí: es una novedad que hay que mirar antes de confiar en el "
        "histograma de PD.",
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
