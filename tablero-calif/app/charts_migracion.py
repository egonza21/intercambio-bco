"""Figuras de la página de migración: grupo, PD y modelo entre dos meses."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import theme
from theme import aplicar_template as _t
from charts_base import (
    _sin_datos, _rezago, _pie_comparacion, banda_historica, leyenda_banda,
    registrar_guia)


# ===========================================================================
# MIGRACION
# ===========================================================================

# Las categorías que no son movimiento. NO son un grupo de riesgo: van en
# gris, fuera de la escala divergente.
#
# Ganar y perder elegibilidad están ABIERTAS en dos por el modelo del cliente
# en el mes de referencia (07_migracion_r1.sql, paso 5). La distinción es de
# dueño distinto: que el corte de un producto deje fuera a un cliente que el
# modelo sí calificó es una decisión de política del producto; que el cliente
# deje de tener modelo es que salió del universo calificable.
#
# Filas: sin grupo de ORIGEN. Columnas: sin grupo de DESTINO.
_ORIGEN_FUERA = ["entrada", "ganancia_por_corte", "ganancia_de_modelo"]
_DESTINO_FUERA = ["salida", "perdida_por_corte", "perdida_de_modelo"]
# Nombres previos a la apertura. Se muestran solo si la tabla leída todavía
# los trae, para que una construcción vieja no pierda filas en silencio.
_ORIGEN_LEGADO = ["ganancia_elegibilidad"]
_DESTINO_LEGADO = ["perdida_elegibilidad"]
_FUERA = _ORIGEN_FUERA + _DESTINO_FUERA + _ORIGEN_LEGADO + _DESTINO_LEGADO
_ETIQUETA_FUERA = {
    "entrada": "entrada (población)",
    "ganancia_por_corte": "ganó · el corte lo incluyó",
    "ganancia_de_modelo": "ganó · empezó a calificarse",
    "ganancia_elegibilidad": "ganó elegibilidad (sin abrir)",
    "salida": "salida (población)",
    "perdida_por_corte": "PERDIÓ · el corte lo excluyó",
    "perdida_de_modelo": "PERDIÓ · dejó de calificarse",
    "perdida_elegibilidad": "perdió elegibilidad (sin abrir)",
}
# Gris claro a gris medio: mismo rol que la escala secuencial pero sin tono,
# para que se lea como "fuera de la escala de riesgo" y no como un grupo más.
_ESCALA_GRIS = [[0.0, "#efeeeb"], [1.0, theme.GRIS_FUERA_ESCALA]]

# Clave Y etiqueta de la ausencia de modelo. Los modelos reales son
# identificadores en mayúsculas (T2, ADVANCE_1_1), así que no puede chocar.
SIN_MODELO = "(sin modelo)"


def filtrar_mismo_segmento(d: pd.DataFrame) -> pd.DataFrame:
    """Deja solo los clientes que no cambiaron de segmento.

    La comparación se aplica SOLO donde los dos segmentos existen. Antes era un
    `segmento_anterior == segmento_actual` plano, y eso borraba en silencio las
    cuatro categorías que no son movimiento: para una entrada o una ganancia de
    elegibilidad el lado origen no existe en la tabla larga -- el join es un
    full outer y `largo_calificaciones` lleva `grupo IS NOT NULL` -- así que
    `segmento_anterior` viene nulo por construcción, nunca es igual a nada, y
    la fila desaparecía. Por eso entradas, salidas y elegibilidad no se veían
    en la matriz con el filtro activo, que es el default de la página.

    Un cliente sin uno de los dos lados no cambió de segmento: no hay nada que
    comparar. Se queda.
    """
    if d.empty or "segmento_anterior" not in d.columns:
        return d
    ant, act = d["segmento_anterior"], d["segmento_actual"]
    incompleto = ant.isna() | act.isna() | (ant == "") | (act == "")
    return d[incompleto | (ant == act)]


def matriz_migracion(df: pd.DataFrame, producto: str,
                     solo_mismo_segmento: bool = True,
                     segmento: str | None = None) -> go.Figure:
    """Matriz de grupo_base con las cuatro categorías de borde como filas y
    columnas propias.

    El color del bloque 8x8 es DIVERGENTE y centrado en la diagonal: el tono
    dice la dirección (azul mejora, rojo deterioro) y la intensidad el volumen,
    como participación de la fila de origen. La diagonal queda neutra por
    construcción, sin importar su masa: es estabilidad, no señal.

    Las dos filas y las dos columnas de más van en GRIS, fuera de la escala:
    no son grupos de riesgo, son cambios de población o decisiones del modelo.
    Son cuatro categorías DISTINTAS y se muestran separadas --

        fila «entrada»                     no estaba en la tabla
        fila «ganó · el corte lo incluyó»  estaba y ya tenía modelo
        fila «ganó · empezó a calificarse» estaba y no tenía modelo
        col. «salida»                      ya no está en la tabla
        col. «PERDIÓ · el corte lo excluyó» sigue y conserva modelo
        col. «PERDIÓ · dejó de calificarse» sigue y ya no tiene modelo

    -- porque son tres problemas de dueños distintos: el corte de un producto,
    el universo calificable del modelo, y la población.

    El denominador de cada fila incluye ahora las dos columnas grises: de los
    que estaban en G3, cuántos siguen en G3 y cuántos se fueron. Sin eso la
    matriz sumaba 100% ignorando a los que se caían, que es justo lo que
    interesa ver.
    """
    if df.empty:
        return _sin_datos()
    d = df[df["producto"] == producto] if producto and producto != "todos" else df.copy()
    if segmento and segmento != "todos" and "segmento_actual" in d.columns:
        # Para una salida no hay segmento_actual; se filtra por el que exista.
        act = d["segmento_actual"].map(theme._cod)
        ant = d["segmento_anterior"].map(theme._cod)
        d = d[act.where(act != "", ant) == theme._cod(segmento)]
    if solo_mismo_segmento:
        d = filtrar_mismo_segmento(d)
    if d.empty:
        return _sin_datos()

    gs = theme.GRUPOS_BASE_ORDENADOS
    presentes = set(d["categoria"])
    ejes_y = gs + _ORIGEN_FUERA + [c for c in _ORIGEN_LEGADO if c in presentes]
    ejes_x = gs + _DESTINO_FUERA + [c for c in _DESTINO_LEGADO if c in presentes]
    cnt = pd.DataFrame(0.0, index=ejes_y, columns=ejes_x)

    mov = d[d["categoria"] == "movimiento"]
    if not mov.empty:
        m = (mov.groupby(["grupo_base_origen", "grupo_base_destino"],
                         as_index=False)["clientes"].sum()
             .pivot(index="grupo_base_origen", columns="grupo_base_destino",
                    values="clientes").reindex(index=gs, columns=gs).fillna(0))
        cnt.loc[gs, gs] = m.values
    for cat in ejes_y[len(gs):]:   # sin grupo de origen: fila propia
        sub = d[d["categoria"] == cat]
        if sub.empty:
            continue
        v = (sub.groupby("grupo_base_destino")["clientes"].sum()
             .reindex(gs).fillna(0))
        cnt.loc[cat, gs] = v.values
    for cat in ejes_x[len(gs):]:   # sin grupo de destino: columna propia
        sub = d[d["categoria"] == cat]
        if sub.empty:
            continue
        v = (sub.groupby("grupo_base_origen")["clientes"].sum()
             .reindex(gs).fillna(0))
        cnt.loc[gs, cat] = v.values

    valores = cnt.values
    fila = valores.sum(axis=1, keepdims=True)
    share = np.divide(valores, fila, out=np.zeros_like(valores, dtype=float),
                      where=fila > 0)

    # Máscara del bloque de riesgo: las dos últimas filas y las dos últimas
    # columnas quedan fuera de la escala divergente.
    ng = len(gs)
    nucleo = np.zeros_like(share, dtype=bool)
    nucleo[:ng, :ng] = True
    idx = np.arange(ng)
    signo = np.zeros_like(share)
    signo[:ng, :ng] = np.sign(idx[None, :] - idx[:, None])
    z_riesgo = np.where(nucleo, share * signo, np.nan)
    z_fuera = np.where(nucleo | (valores <= 0), np.nan, share)

    hover = ("<b>%{y} &#8594; %{x}</b><br>%{customdata[0]:,.0f} clientes"
             "<br>%{customdata[1]:.1%} de los que estaban en %{y}<extra></extra>")
    extra = np.stack([valores, share], axis=-1)
    fig = go.Figure(go.Heatmap(
        z=z_riesgo, x=ejes_x, y=ejes_y, zmid=0, zmin=-1, zmax=1,
        colorscale=theme.escala_divergente("malo"),  # z > 0: pasó a un grupo peor
        xgap=2, ygap=2, customdata=extra,
        colorbar=dict(
            title=dict(text="mejora  <->  deterioro<br>(% de la fila)",
                       font=dict(size=10, color=theme.INK_MUTED)),
            tickvals=[-1, -0.5, 0, 0.5, 1], ticktext=["100%", "50%", "0", "50%", "100%"],
            thickness=12, len=0.7, outlinewidth=0, x=1.02),
        hovertemplate=hover))
    fig.add_heatmap(
        z=z_fuera, x=ejes_x, y=ejes_y, zmin=0, zmax=1, colorscale=_ESCALA_GRIS,
        xgap=2, ygap=2, customdata=extra, showscale=False, hovertemplate=hover)

    tinta_riesgo = np.where(np.abs(np.nan_to_num(z_riesgo)) > 0.45, "#ffffff", theme.INK)
    for i, yv in enumerate(ejes_y):
        for j, xv in enumerate(ejes_x):
            if valores[i, j] <= 0:
                continue
            if nucleo[i, j]:
                color = tinta_riesgo[i, j]
            else:
                color = "#ffffff" if share[i, j] > 0.6 else theme.INK
            fig.add_annotation(x=xv, y=yv, text=theme.fmt_miles(valores[i, j]),
                               showarrow=False,
                               font=dict(size=10, color=color, family=theme.FONT))

    fig.add_annotation(
        x=0, y=-0.20, xref="paper", yref="paper", xanchor="left",
        showarrow=False, align="left",
        text=("En gris, fuera de la escala de riesgo: las últimas filas son "
              "clientes sin grupo en el mes de origen y las últimas columnas, "
              "sin grupo en el de destino. «El corte lo excluyó» es una "
              "decisión de política del producto — el modelo sí calificó al "
              "cliente; «dejó de calificarse» es que perdió el modelo y salió "
              "del universo calificable; «salida» es cambio de población."),
        font=dict(size=11, color=theme.GRIS_FUERA_ESCALA, family=theme.FONT))

    _pie_comparacion(fig, d, y=-0.30)
    rez = _rezago(d)
    meses = sorted(int(m) for m in set(d["idx_mes"].dropna()))
    if len(meses) == 1:
        t_dst = f"Grupo en {theme.etiqueta_mes_idx(meses[0])}"
        t_org = f"Grupo en {theme.etiqueta_mes_idx(meses[0] - rez)}"
    else:
        t_dst = "Grupo en el mes destino"
        t_org = f"Grupo {rez} mes(es) antes"
    etq_y = [_ETIQUETA_FUERA.get(c, c) for c in ejes_y]
    etq_x = [_ETIQUETA_FUERA.get(c, c) for c in ejes_x]
    fig.update_layout(height=max(640, 46 * len(ejes_y) + 220))
    # Los ejes van por CLAVE de categoría; el texto legible solo en ticktext.
    fig.update_xaxes(title_text=t_dst, side="top", showline=False, ticks="",
                     type="category", categoryorder="array", categoryarray=ejes_x,
                     tickmode="array", tickvals=ejes_x, ticktext=etq_x)
    fig.update_yaxes(title_text=t_org, autorange="reversed", showgrid=False,
                     showline=False, ticks="", type="category",
                     categoryorder="array", categoryarray=ejes_y,
                     tickmode="array", tickvals=ejes_y, ticktext=etq_y)
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
    if d.empty:
        return _sin_datos()
    # «Sin modelo» es una categoría, no un dato ausente. Estas filas EXISTEN en
    # la tabla: tienen grupo en los dos meses y `modelo` nulo, porque
    # largo_calificaciones normaliza con nullif(trim(modelo), '') y filtra por
    # grupo, no por modelo. Descartarlas con .notna() borraba justo a los
    # clientes que dejaron de ser calificados, que es lo que hay que ver.
    # Acá la fila ya es de categoría 'movimiento', así que un nulo significa
    # "no tiene modelo", no "el cliente no está en ese mes".
    for c in ("modelo_anterior", "modelo_actual"):
        d[c] = d[c].fillna(SIN_MODELO).replace("", SIN_MODELO)

    m = (d.groupby(["modelo_anterior", "modelo_actual"], as_index=False)["clientes"]
         .sum())
    # Sin modelo al final del eje, no donde caiga alfabéticamente.
    ejes = sorted(set(m["modelo_anterior"]) | set(m["modelo_actual"]),
                  key=lambda x: (x == SIN_MODELO, x))
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
    nota = ("La diagonal (los que no cambiaron de modelo) va sin color para "
            "que no domine la escala; el conteo sigue anotado.")
    if SIN_MODELO in ejes:
        nota += (
            f" «{SIN_MODELO}» NO son los que dejaron de ser calificados: acá "
            f"solo entran clientes con grupo en los DOS meses, y quien deja de "
            f"ser calificado pierde también el grupo, sale de "
            f"largo_calificaciones y nunca llega a esta matriz. Lo que mide "
            f"esta fila y esta columna es clientes CON grupo y SIN modelo, que "
            f"es más bien una anomalía del dato. Los que dejaron de ser "
            f"calificados se ven en la matriz de migración de grupo, en la "
            f"columna «{_ETIQUETA_FUERA['perdida_de_modelo']}».")
    fig.add_annotation(
        x=0, y=-0.14, xref="paper", yref="paper", xanchor="left", showarrow=False,
        align="left", text=nota,
        font=dict(size=11, color=theme.INK_MUTED, family=theme.FONT))
    return _t(fig)


def estabilidad_deterioro(df: pd.DataFrame, producto: str) -> go.Figure:
    """Estabilidad (traza de la matriz) y deterioro neto en el tiempo.

    Cada punto es un mes CONTRA otro, no un estado del mes. El eje X lleva el
    mes destino, así que sin decir el rezago la lectura natural es "esto pasó
    en agosto" cuando lo que dice es "esto pasó entre julio y agosto".

    Un mes cuya partición de referencia falta no produce filas de movimiento y
    antes desaparecía de la serie sin dejar rastro: la línea se veía continua
    por encima del hueco. Ahora se listan al pie.
    """
    if df.empty:
        return _sin_datos()
    s = serie_estabilidad(df, producto)
    rez = _rezago(df)
    if s.empty:
        return _sin_datos(
            f"ningún mes tiene comparación a {rez} mes(es) de distancia: no "
            f"hay filas de movimiento")
    etiquetas = [theme.etiqueta_mes_idx(m) for m in s["idx_mes"]]
    # Meses presentes en el agregado que no llegaron a la serie: sin
    # movimiento porque su mes de referencia no existe.
    d_prod = (df[df["producto"] == producto]
              if producto and producto != "todos" else df)
    huecos = sorted(set(int(m) for m in d_prod["idx_mes"].dropna())
                    - set(int(m) for m in s["idx_mes"]))

    fig = go.Figure()
    fig.add_scatter(x=etiquetas, y=s["estabilidad"], name="Estabilidad (diagonal)",
                    mode="lines", line=dict(color=theme.SERIES[0], width=2, dash="solid"),
                    hovertemplate="Estabilidad · %{y:.1%}<extra></extra>")
    fig.add_scatter(x=etiquetas, y=s["mejora"], name="Mejoraron",
                    mode="lines", line=dict(color=theme.SERIES[2], width=2, dash="dot"),
                    hovertemplate="Mejoraron · %{y:.1%}<extra></extra>")
    fig.add_scatter(x=etiquetas, y=s["deterioro"], name="Empeoraron",
                    mode="lines", line=dict(color=theme.SERIES[1], width=2, dash="dash"),
                    hovertemplate="Empeoraron · %{y:.1%}<extra></extra>")
    hubo = False
    for col, color in (("estabilidad", theme.SERIES[0]), ("mejora", theme.SERIES[2]),
                       ("deterioro", theme.SERIES[1])):
        hubo = banda_historica(fig, s[col].values, color) or hubo
    if hubo:
        leyenda_banda(fig)
    fig.add_hline(y=0, line=dict(color=theme.AXIS, width=1))
    if huecos:
        fig.add_annotation(
            x=0, y=-0.30, xref="paper", yref="paper", xanchor="left",
            showarrow=False, align="left",
            text=("Sin comparación y por eso ausentes del gráfico: "
                  + ", ".join(theme.etiqueta_mes_idx(m) for m in huecos)
                  + f" — falta su mes de referencia ({rez} mes(es) antes)."),
            font=dict(size=11, color=theme.ESTADO_ALERTA, family=theme.FONT))
    fig.update_layout(height=380)
    fig.update_xaxes(
        title_text=("Mes destino; cada punto lo compara contra "
                    + ("el mes anterior" if rez == 1
                       else f"{rez} meses antes")))
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
            "mejora": x.loc[x["_mejor"], "clientes"].sum() / x["clientes"].sum(),
            "deterioro": x.loc[x["_peor"], "clientes"].sum() / x["clientes"].sum(),
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
        colorscale=theme.escala_divergente("malo"),  # z > 0: subió de decil de PD
        xgap=2, ygap=2,
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
    _pie_comparacion(fig, d, y=-0.26)
    rez = _rezago(d)
    meses = sorted(int(m) for m in set(d["idx_mes"].dropna()))
    if len(meses) == 1:
        t_dst = f"Decil de PD en {theme.etiqueta_mes_idx(meses[0])}"
        t_org = f"Decil de PD en {theme.etiqueta_mes_idx(meses[0] - rez)}"
    else:
        t_dst = "Decil de PD en el mes destino"
        t_org = f"Decil de PD {rez} mes(es) antes"
    fig.update_layout(height=540)
    fig.update_xaxes(title_text=t_dst, side="top", showline=False, ticks="",
                     dtick=1)
    fig.update_yaxes(title_text=t_org, autorange="reversed", showgrid=False,
                     showline=False, ticks="", dtick=1)
    return _t(fig)


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
# GUÍAS DE LECTURA (ver charts_base.guia)
# ===========================================================================
registrar_guia(
    "matriz_migracion",
    "De qué grupo a qué grupo se movieron los clientes entre dos meses, más "
    "los que entraron, salieron o cambiaron de elegibilidad.",
    "Filas: grupo en el mes de origen; columnas: en el de destino. Azul es "
    "mejora, rojo deterioro, y la intensidad es el % de la fila. En gris, "
    "fuera de la escala, las categorías de borde: entradas, salidas y las "
    "cuatro de elegibilidad.",
    "La diagonal concentra casi toda la masa. Llama la atención masa lejos "
    "de la diagonal — saltos de varios grupos — o una columna «PERDIÓ · dejó "
    "de calificarse» grande: son clientes que salieron del universo "
    "calificable.")
registrar_guia(
    "estabilidad_deterioro",
    "Qué parte de los clientes se quedó en su grupo, mejoró o empeoró, cada "
    "mes.",
    "Tres líneas, sobre los clientes con grupo en los dos meses. Cada punto "
    "compara un mes contra su referencia. Las bandas son el rango habitual "
    "de cada línea.",
    "Estabilidad alta y pareja; mejora y deterioro bajas y parecidas. Llama "
    "la atención un punto fuera de su banda, o mejora y deterioro subiendo a "
    "la vez: más rotación, que no es lo mismo que más riesgo.")
registrar_guia(
    "tabla_peores_saltos",
    "Combinaciones origen → destino con caída de tres grupos o más.",
    "Una fila por combinación, ordenada por cantidad de clientes.",
    "Pocas filas y chicas. Llama la atención una combinación con mucho "
    "volumen, y cualquier salto desde G1–G2: clientes buenos que se "
    "deterioraron de golpe.")
registrar_guia(
    "flujo_modelos",
    "Clientes que cambiaron de modelo entre los dos meses, entre los que "
    "tienen grupo en ambos.",
    "Filas: modelo de origen; columnas: de destino. La diagonal va sin color "
    "para no dominar la escala; el conteo sigue anotado.",
    "Casi todo en la diagonal. Un flujo grande hacia un modelo explica un "
    "PSI que sube sin deriva. «(sin modelo)» son clientes con grupo y sin "
    "modelo, una anomalía del dato: los que dejaron de calificarse están en "
    "la matriz de migración, columna «PERDIÓ · dejó de calificarse».")
registrar_guia(
    "matriz_migracion_pd",
    "Cómo se reordenaron los clientes entre deciles de PD de un mes a otro.",
    "Filas: decil en el mes de origen; columnas: en el de destino. El número "
    "es el % de la fila.",
    "Diagonal fuerte. Ojo: dice que el ORDEN se mantuvo, no que la PD no se "
    "movió — eso lo dice el PSI. Llama la atención masa lejos de la "
    "diagonal: el modelo está reordenando a los clientes.")
