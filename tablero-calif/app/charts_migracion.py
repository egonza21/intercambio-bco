"""Figuras de la página de migración: grupo, PD y modelo entre dos meses."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import theme
from theme import aplicar_template as _t
from charts_base import _sin_datos, _rezago, _pie_comparacion


# ===========================================================================
# MIGRACION
# ===========================================================================

# Las cuatro categorías que no son movimiento. NO son un grupo de riesgo: van
# en gris, fuera de la escala divergente.
_FUERA = ["entrada", "ganancia_elegibilidad", "salida", "perdida_elegibilidad"]

# Filas de la matriz sin grupo de ORIGEN (el cliente aparece), columnas sin
# grupo de DESTINO (el cliente desaparece de la larga).
_ORIGEN_FUERA = ["entrada", "ganancia_elegibilidad"]
_DESTINO_FUERA = ["salida", "perdida_elegibilidad"]
_ETIQUETA_FUERA = {
    "entrada": "entrada (población)",
    "ganancia_elegibilidad": "ganó elegibilidad",
    "salida": "salida (población)",
    "perdida_elegibilidad": "PERDIÓ elegibilidad",
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

        fila «entrada»            el cliente no estaba en la tabla
        fila «ganó elegibilidad»  estaba, sin grupo en ESE producto
        col. «salida»             el cliente ya no está en la tabla
        col. «perdió elegibilidad» sigue, pero sin grupo en ESE producto

    -- porque perder un grupo por decisión del modelo y desaparecer de la
    población son problemas de dueños distintos.

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
    ejes_y = gs + _ORIGEN_FUERA
    ejes_x = gs + _DESTINO_FUERA
    cnt = pd.DataFrame(0.0, index=ejes_y, columns=ejes_x)

    mov = d[d["categoria"] == "movimiento"]
    if not mov.empty:
        m = (mov.groupby(["grupo_base_origen", "grupo_base_destino"],
                         as_index=False)["clientes"].sum()
             .pivot(index="grupo_base_origen", columns="grupo_base_destino",
                    values="clientes").reindex(index=gs, columns=gs).fillna(0))
        cnt.loc[gs, gs] = m.values
    for cat in _ORIGEN_FUERA:      # sin grupo de origen: fila propia
        sub = d[d["categoria"] == cat]
        if sub.empty:
            continue
        v = (sub.groupby("grupo_base_destino")["clientes"].sum()
             .reindex(gs).fillna(0))
        cnt.loc[cat, gs] = v.values
    for cat in _DESTINO_FUERA:     # sin grupo de destino: columna propia
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
        colorscale=theme.ESCALA_DIVERGENTE, xgap=2, ygap=2, customdata=extra,
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
        text=("En gris, fuera de la escala de riesgo: las dos últimas filas son "
              "clientes sin grupo en el mes de origen y las dos últimas "
              "columnas, sin grupo en el de destino. «Perdió elegibilidad» es "
              "una decisión del modelo; «salida», un cambio de población."),
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
    etq_y = gs + [_ETIQUETA_FUERA[c] for c in _ORIGEN_FUERA]
    etq_x = gs + [_ETIQUETA_FUERA[c] for c in _DESTINO_FUERA]
    fig.update_layout(height=640)
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
        nota += (f" «{SIN_MODELO}» son clientes CON grupo y sin modelo: la "
                 f"columna dice cuántos dejaron de ser calificados y la fila, "
                 f"cuántos volvieron a serlo.")
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
