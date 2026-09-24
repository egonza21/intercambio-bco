"""Figuras de Panorama del mes y de Evolución.

Las dos páginas son de negocio y leen los mismos agregados (composición por
grupo y base de clientes); separarlas dejaría dos módulos que se importan
entre sí para nada.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import theme
from theme import aplicar_template as _t
from charts_base import (
    _sin_datos, _grupos_ordenados, banda_historica, leyenda_banda,
    registrar_guia)


def composicion_grupo(df: pd.DataFrame, familia: str | None = None,
                      orden_productos: list[str] | None = None,
                      porcentaje: bool = True) -> go.Figure:
    """Composición de grupo por producto, barra apilada 100%.

    Apilada por grupo_orden ascendente: la barra lee de menor a mayor riesgo de
    izquierda a derecha, y el gradiente de la rampa hace de leyenda.

    `porcentaje=False` cambia a apilado ABSOLUTO. No es el mismo gráfico en
    otra unidad: en el 100% el porcentaje ES el gráfico y todas las barras
    miden igual; en absoluto las barras miden volumen y se pueden comparar
    entre productos, pero se pierde la lectura del reparto interno. Son dos
    preguntas distintas y la etiqueta de la página lo dice.

    `orden_productos` fija el eje explícitamente. Sirve para el comparador de
    dos meses: si cada panel ordena por sus propios datos, un producto cambia
    de fila entre meses y la comparación visual deja de servir.
    """
    if df.empty:
        return _sin_datos()
    d = df.copy()
    if familia and familia != "todas":
        d = d[d["producto"].map(theme.familia_de) == familia]
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
        # fillna(0) NO es cosmético: en una barra apilada Plotly trata el NaN
        # como HUECO, no como cero, y el apilado se corre. Un producto sin G1
        # ni G2 pero con G8 mostraba el G8 pegado al eje, como si fuera el
        # primer grupo. El customdata ya lo tenía; el share no.
        s = (piv[piv["grupo"] == grupo].set_index("producto")
             .reindex(orden_prod).fillna(0))
        fig.add_bar(
            y=orden_prod,
            x=(s["share"] if porcentaje else s["clientes"]).values,
            name=grupo, orientation="h",
            marker=dict(color=theme.COLOR_GRUPO.get(grupo, theme.INK_MUTED),
                        line=dict(color=theme.SURFACE, width=2)),  # gap de 2px
            customdata=np.stack([s["clientes"].fillna(0).values,
                                 s["share"].fillna(0).values], axis=-1),
            hovertemplate=("<b>%{y}</b> · " + grupo +
                           ("<br>%{x:.1%} de la cartera del producto"
                            "<br>%{customdata[0]:,.0f} clientes"
                            if porcentaje else
                            "<br>%{x:,.0f} clientes"
                            "<br>%{customdata[1]:.1%} del producto")
                           + "<extra></extra>"),
        )
    # traceorder normal: la leyenda sigue el orden de apilado (G1 primero), no
    # el invertido que Plotly usa por defecto en barras apiladas.
    fig.update_layout(barmode="stack", legend_traceorder="normal",
                      height=max(360, 34 * len(orden_prod) + 130))
    if porcentaje:
        fig.update_xaxes(title_text="Participación en la cartera del producto",
                         tickformat=".0%", range=[0, 1])
    else:
        fig.update_xaxes(title_text="Clientes con calificación",
                         tickformat=",.0f", rangemode="tozero")
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
    # Se agrupa por CÓDIGO, no por nombre. Agrupar por el nombre era peor que
    # un eje mal etiquetado: dos códigos con la misma etiqueta se SUMABAN en
    # el groupby y el resultado no dejaba rastro de que habían sido dos.
    d["segmento"] = d["segmento"].map(theme._cod)
    g = d.groupby(["segmento", "grupo"], as_index=False)["clientes"].sum()
    g["share"] = g["clientes"] / g.groupby("segmento")["clientes"].transform("sum")
    cols = _grupos_ordenados(g["grupo"])
    piv = g.pivot(index="segmento", columns="grupo", values="share").reindex(columns=cols)
    cnt = g.pivot(index="segmento", columns="grupo", values="clientes").reindex(columns=cols)
    # Por valor de negocio, no por volumen: el orden del eje no cambia porque
    # un segmento crezca. Los que no forman escala quedan al final.
    orden_seg = theme.segmentos_ordenados(g["segmento"])
    piv, cnt = piv.reindex(orden_seg), cnt.reindex(orden_seg)
    etiquetas_seg = theme.etiquetas_segmento(orden_seg)   # falla si se repiten

    if normalizar:
        z, extra, fmt, titulo = piv.values, cnt.values, ".0%", "% del<br>segmento"
        linea_z = "%{z:.1%} del segmento<br>%{customdata:,.0f} clientes"
    else:
        z, extra, fmt, titulo = cnt.values, piv.values, ",.0f", "clientes"
        linea_z = "%{z:,.0f} clientes<br>%{customdata:.1%} del segmento"

    fig = go.Figure(go.Heatmap(
        z=z, x=cols, y=list(piv.index),
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
                x=gr, y=seg, showarrow=False,
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
    # El eje va por CÓDIGO, que es único por definición; el nombre legible
    # entra solo como ticktext. Si el eje se construyera con nombres, dos
    # códigos que produzcan el mismo texto colapsarían en una sola fila.
    fig.update_yaxes(title_text="", showgrid=False, showline=False, ticks="",
                     type="category", categoryorder="array",
                     categoryarray=list(reversed(orden_seg)),
                     tickmode="array", tickvals=orden_seg,
                     ticktext=etiquetas_seg)
    return _t(fig)


def cobertura(df: pd.DataFrame, segmento: str | None = None) -> go.Figure:
    """Cobertura por producto. La baja de comercial/micro/sobregiro es
    estructural, no una falla: va anotada en el propio gráfico."""
    if df.empty:
        return _sin_datos()
    # Los dos lados por _cod: comparar el valor crudo contra el del selector
    # funciona solo mientras los dos lleguen con el mismo tipo, y cuando no,
    # el filtro no falla — devuelve cero filas y el visual sale vacío.
    d = (df if not segmento or segmento == "todos"
         else df[df["segmento"].map(theme._cod) == theme._cod(segmento)])
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
        # Misma razón que en composicion_grupo: es un área APILADA y el NaN
        # rompe la geometría del apilado. Un grupo ausente en un mes es 0%.
        s = (g[g["grupo"] == grupo].set_index("idx_mes")
             .reindex(meses).fillna(0))
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

    g["segmento"] = g["segmento"].map(theme._cod)
    # Por valor de negocio, no por volumen: qué segmento se ve como serie
    # propia no debe depender de cuál creció este mes.
    orden = theme.segmentos_ordenados(g["segmento"])
    segmentos = orden[:4]                # máximo 4 series distinguibles
    otros = [x for x in orden if x not in segmentos]

    fig = go.Figure()
    hubo_banda = False
    for i, seg in enumerate(segmentos):
        # Un segmento sin fila en un mes tiene 0 clientes, no un hueco: la
        # línea tiene que bajar a cero y verse.
        s = (g[g["segmento"] == seg].set_index("idx_mes")
             .reindex(meses).fillna(0))
        # El nombre es presentación y va solo acá; la serie se seleccionó por
        # código. Antes la leyenda mostraba el código crudo ("11").
        nombre = theme.etiqueta_segmento(seg)
        fig.add_scatter(
            x=etiquetas, y=s["clientes"].values, name=nombre, mode="lines",
            line=dict(color=theme.SERIES[i], width=2, dash=theme.SERIES_DASH[i]),
            hovertemplate=nombre + " · %{y:,.0f} clientes<extra></extra>",
        )
        hubo_banda = banda_historica(fig, s["clientes"].values,
                                     theme.SERIES[i]) or hubo_banda
    if otros:
        s = (g[g["segmento"].isin(otros)].groupby("idx_mes")["clientes"].sum()
             .reindex(meses).fillna(0))
        fig.add_scatter(
            x=etiquetas, y=s.values, name=f"otros ({len(otros)})", mode="lines",
            line=dict(color=theme.INK_MUTED, width=1.5, dash="dot"),
            hovertemplate="otros · %{y:,.0f} clientes<extra></extra>",
        )
    if hubo_banda:
        leyenda_banda(fig)
    fig.update_layout(height=400)
    fig.update_xaxes(title_text="")
    fig.update_yaxes(title_text="Clientes en la base del mes", tickformat=",.0f",
                     rangemode="tozero")
    return _t(fig, unified=True)


def vigencia_modelos(df: pd.DataFrame) -> go.Figure:
    """Reparto de la población entre modelos, área apilada. TODOS los modelos.

    Antes recortaba a los cuatro de mayor población y agrupaba el resto en
    "otros". Acá eso escondía justo lo que interesa: un modelo nuevo entra con
    poca población y quedaba invisible dentro de "otros".

    Como son ocho o nueve series y la paleta categórica tiene cuatro, el color
    sale de la rampa secuencial repartida entre los modelos ordenados por
    población. No identifica al modelo por sí solo -- para eso está la leyenda
    y el hover -- pero mantiene el apilado legible y ordenado.

    La pregunta "cuántos modelos hay vivos" la responde modelos_vivos(), que es
    otro gráfico: en el área apilada un modelo con 1% no se ve.
    """
    if df.empty:
        return _sin_datos()
    d = df.copy()
    d["modelo"] = d["modelo"].fillna("sin modelo")
    g = d.groupby(["idx_mes", "modelo"], as_index=False)["clientes"].sum()
    g["share"] = g["clientes"] / g.groupby("idx_mes")["clientes"].transform("sum")
    meses = sorted(g["idx_mes"].unique())
    etiquetas = [theme.etiqueta_mes_idx(m) for m in meses]
    modelos = (g.groupby("modelo")["share"].mean()
               .sort_values(ascending=False).index.tolist())

    fig = go.Figure()
    n = max(1, len(modelos) - 1)
    for i, mod in enumerate(modelos):
        s = (g[g["modelo"] == mod].set_index("idx_mes")
             .reindex(meses).fillna(0))
        fig.add_scatter(
            x=etiquetas, y=s["share"].values, name=mod,
            mode="lines", stackgroup="modelos", groupnorm="fraction",
            line=dict(width=0.5, color=theme.SURFACE),
            fillcolor=theme._rampa_secuencial(i / n),
            hovertemplate=mod + " · %{y:.1%}<extra></extra>")
    fig.update_layout(height=max(420, 22 * len(modelos) + 330),
                      legend_traceorder="normal")
    fig.update_xaxes(title_text="", categoryorder="array", categoryarray=etiquetas)
    fig.update_yaxes(title_text="Participación de la población calificada",
                     tickformat=".0%", range=[0, 1])
    return _t(fig, unified=True)


def modelos_vivos(df: pd.DataFrame) -> go.Figure:
    """Cuántos modelos distintos hay por mes. Una sola línea.

    Es la que detecta un despliegue o un retiro. El área apilada de reparto no
    la reemplaza: ahí un modelo nuevo con 1% de población es invisible, y acá
    es un escalón.
    """
    if df.empty:
        return _sin_datos()
    d = df[df["modelo"].notna()]
    if d.empty:
        return _sin_datos()
    g = d.groupby("idx_mes")["modelo"].nunique().sort_index()
    etiquetas = [theme.etiqueta_mes_idx(m) for m in g.index]
    fig = go.Figure(go.Scatter(
        x=etiquetas, y=g.values, mode="lines+markers",
        line=dict(color=theme.SERIES[0], width=2),
        marker=dict(size=8, line=dict(color=theme.SURFACE, width=2)),
        hovertemplate="%{y} modelos vivos<extra></extra>"))
    if banda_historica(fig, g.values, theme.SERIES[0]):
        leyenda_banda(fig)
    fig.update_layout(height=300)
    fig.update_xaxes(title_text="", categoryorder="array", categoryarray=etiquetas)
    fig.update_yaxes(title_text="Modelos distintos en el mes", rangemode="tozero",
                     dtick=1)
    return _t(fig)


# ===========================================================================
# GUÍAS DE LECTURA (ver charts_base.guia)
# ===========================================================================
registrar_guia(
    "composicion_grupo",
    "Cómo se reparte cada producto entre los grupos de riesgo en el mes.",
    "Una barra por producto que suma 100% (o el conteo, en modo absoluto), "
    "con los grupos de G1 a G8 en el orden de la rampa. Los productos van "
    "ordenados por su masa en G6 y peores, así que la lista ya viene "
    "rankeada por riesgo.",
    "Los sufi moto, cpe y con abren G7 y G8 en B/M/A: es su apertura, no un "
    "grupo nuevo. Llama la atención un producto con la cola G7–G8 mucho más "
    "gruesa que la de su familia, o que cambie de lugar en el orden de un "
    "mes a otro.")
registrar_guia(
    "heatmap_segmento_grupo",
    "Cómo se reparte cada segmento entre los grupos de riesgo.",
    "Cada fila suma 100%; el color es el porcentaje dentro del segmento y el "
    "conteo va en el hover. Segmentos en orden de valor.",
    "El riesgo baja a medida que sube el valor del segmento: Banca Privada "
    "más cargada hacia G1 que Social. Llama la atención una fila que rompe "
    "ese gradiente.")
registrar_guia(
    "cobertura",
    "Qué porcentaje de la base tiene grupo en cada producto.",
    "Una barra por producto, sobre los clientes de la base del mes.",
    "Comercial, micro y sobregiro son estructuralmente bajos: aplican a "
    "quien tiene un pequeño negocio. Llama la atención una caída en un "
    "producto que suele tener cobertura alta.")
registrar_guia(
    "comparar_meses",
    "La composición de grupo de dos meses, lado a lado.",
    "Los dos paneles usan el mismo orden canónico de productos, así que cada "
    "producto queda a la misma altura en ambos.",
    "De un mes a otro los cambios son de pocos puntos. Llama la atención una "
    "barra cuya cola G7–G8 cambie a simple vista.")
registrar_guia(
    "mezcla_riesgo",
    "El reparto de un producto entre grupos de riesgo, mes a mes.",
    "Área apilada al 100%: el grosor de cada capa es su participación. En "
    "porcentaje y no en conteo, porque la base viene bajando y el conteo lo "
    "leería como mejora.",
    "Acá no hay banda de rango habitual: habría una por capa y taparían la "
    "composición, que es lo que se lee. Lo normal es un reparto casi "
    "estable; llama la atención una capa que se ensancha o se adelgaza de "
    "golpe, sobre todo G7–G8.")
registrar_guia(
    "base_clientes_tiempo",
    "Los clientes de la base por segmento, mes a mes, en conteo absoluto.",
    "Hasta cuatro segmentos en orden de valor; el resto, en «otros». La "
    "banda sombreada es el rango habitual de cada serie.",
    "La base viene bajando, así que cada serie tiende a quedar sobre su banda "
    "al principio y debajo al final: es la tendencia, no una alarma. Llama la "
    "atención un escalón de un mes a otro, o un segmento que sale de su banda "
    "en sentido contrario al resto.")
registrar_guia(
    "modelos_vivos",
    "Cuántos modelos distintos califican clientes cada mes.",
    "Una línea; la banda es su rango habitual.",
    "Un número estable, dentro de la banda. Un escalón es un despliegue o un "
    "retiro: si sube, que el modelo nuevo esté en config/modelos.csv.")
registrar_guia(
    "vigencia_modelos",
    "Cómo se reparte la población entre modelos, mes a mes. Todos los "
    "modelos, sin agrupar los chicos.",
    "Área apilada al 100%. Va al lado del PSI porque un escalón acá explica "
    "un salto de PSI sin que ningún modelo haya cambiado.",
    "Sin banda, por la misma razón que la mezcla de riesgo. Capas estables; "
    "llama la atención una capa que aparece o crece de golpe: es "
    "reasignación de población entre modelos.")
