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

_FUERA = ["entrada", "ganancia_elegibilidad", "salida", "perdida_elegibilidad"]


def matriz_migracion(df: pd.DataFrame, producto: str,
                     solo_mismo_segmento: bool = True,
                     segmento: str | None = None) -> go.Figure:
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
    if segmento and segmento != "todos" and "segmento_actual" in d.columns:
        d = d[d["segmento_actual"].map(theme._cod) == theme._cod(segmento)]
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
    etiquetas = {
        "entrada": "entrada (población)",
        "ganancia_elegibilidad": "ganó elegibilidad",
        "salida": "salida (población)",
        "perdida_elegibilidad": "PERDIÓ ELEGIBILIDAD (tenía G, quedó sin G)",
    }
    partes = [f"{etiquetas[k]}  <b>{theme.fmt_miles(v)}</b>" for k, v in fuera.items() if v > 0]
    if partes:
        fig.add_annotation(
            x=0, y=-0.20, xref="paper", yref="paper", xanchor="left", showarrow=False,
            align="left", text="Fuera de la matriz &nbsp;·&nbsp; " + " &nbsp;&nbsp; ".join(partes),
            font=dict(size=11, color=theme.GRIS_FUERA_ESCALA, family=theme.FONT))

    _pie_comparacion(fig, d, y=-0.26)
    rez = _rezago(d)
    meses = sorted(int(m) for m in set(d["idx_mes"].dropna()))
    if len(meses) == 1:
        t_dst = f"Grupo en {theme.etiqueta_mes_idx(meses[0])}"
        t_org = f"Grupo en {theme.etiqueta_mes_idx(meses[0] - rez)}"
    else:
        t_dst = "Grupo en el mes destino"
        t_org = f"Grupo {rez} mes(es) antes"
    fig.update_layout(height=560)
    fig.update_xaxes(title_text=t_dst, side="top", showline=False, ticks="")
    fig.update_yaxes(title_text=t_org, autorange="reversed",
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
