"""Figuras de la página de modelos: histograma de PD, PSI y cortes.

Acá `producto` NO es dimensión válida salvo en sensibilidad de cortes: solo
hay dos PD y son atributo del cliente. Ver CLAUDE.md, "La PD no es por
producto".
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
    hubo = False
    for i, nombre in enumerate(elegidas):
        # SIN fillna(0), a diferencia del resto del archivo. Acá el hueco es
        # lo correcto: que un modelo no tenga PSI en un mes significa que no se
        # pudo calcular (le faltan datos, o no tiene dos meses para comparar).
        # Poner 0 afirmaría "no hubo deriva", que es una mentira distinta del
        # silencio. Es una línea, no un apilado, así que el hueco no rompe nada.
        sub = s[s[columna_serie] == nombre].set_index("idx_mes").reindex(meses)
        fig.add_scatter(
            x=etiquetas, y=sub["psi"].values, name=str(nombre),
            mode="lines+markers",
            line=dict(color=theme.SERIES[i % 4], width=2,
                      dash=theme.SERIES_DASH[i % 4]),
            marker=dict(size=8, line=dict(color=theme.SURFACE, width=2)),
            hovertemplate=f"{nombre} · PSI %{{y:.3f}}<extra></extra>")
        hubo = banda_historica(fig, sub["psi"].values, theme.SERIES[i % 4]) or hubo
    for val, txt, col in ((0.10, "0,10  revisar", theme.ESTADO_ALERTA),
                          (0.25, "0,25  severo", theme.ESTADO_CRITICO)):
        fig.add_hline(y=val, line=dict(color=col, width=1, dash="dot"), opacity=0.55)
        fig.add_annotation(x=1, y=val, xref="paper", yref="y", xanchor="left",
                           xshift=6, showarrow=False, text=txt,
                           font=dict(size=10, color=col, family=theme.FONT))
    if hubo:
        leyenda_banda(fig)
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


# ===========================================================================
# GUÍAS DE LECTURA (ver charts_base.guia)
# ===========================================================================
registrar_guia(
    "histograma_pd",
    "La distribución de la PD de cada modelo en el mes.",
    "Eje X logarítmico, una línea por modelo. Las dos escalas, probabilidad "
    "y puntaje, nunca comparten eje.",
    "Curvas suaves. Llama la atención un modelo en bins absurdos — un "
    "puntaje binado como probabilidad —, un pico aislado, o una curva que "
    "cambia de forma de un mes a otro.")
registrar_guia(
    "psi_general",
    "Cuánto se movió la distribución de grupos de toda la población frente "
    "al mes de referencia. Es el nivel que decide.",
    "Umbrales en 0,10 (revisar) y 0,25 (severo). La banda es el rango "
    "habitual de la propia serie. Con base fija la deriva se acumula; con "
    "base móvil es el cambio de un mes al siguiente.",
    "Debajo de 0,10 y dentro de su banda. Llama la atención cruzar 0,10, o "
    "un punto fuera de la banda aunque siga bajo el umbral.")
registrar_guia(
    "aporte_psi_grupo",
    "Qué grupo aporta más al PSI del mes.",
    "La participación de cada grupo en la base y en el mes, y su aporte al "
    "índice.",
    "Aportes repartidos y chicos. Llama la atención un grupo que concentra "
    "casi todo el índice: el movimiento tiene nombre.")
registrar_guia(
    "psi_modelo",
    "El mismo PSI de grupos, filtrado a un modelo.",
    "Mide qué población le está entrando a ese modelo, no si el modelo "
    "cambió.",
    "Bajo y dentro de su banda. Si sube, contrastarlo con la vigencia y con "
    "el flujo entre modelos antes de concluir nada: un salto acá suele ser "
    "reasignación, no deriva.")
registrar_guia(
    "psi_pd",
    "PSI sobre bins de PD, por modelo.",
    "Es diagnóstico: detecta una PD que se mueve dentro de un grupo sin "
    "cambiar el reparto entre grupos. Se descartan los bins con menos de "
    "0,1% de población.",
    "Bajo y dentro de su banda. Llama la atención cuando el nivel 1 está "
    "tranquilo y este sube: la PD se está moviendo sin cruzar cortes.")
registrar_guia(
    "sensibilidad_cortes",
    "Dónde cae cada frontera de grupo sobre la PD, por producto.",
    "Una fila por producto; cada banda es el rango de PD de un grupo. Como "
    "todos traducen la misma PD, las filas se comparan verticalmente.",
    "Bandas escalonadas que no se cruzan. Una X roja marca un solapamiento: "
    "dos clientes con la misma PD en grupos distintos.")
registrar_guia(
    "tabla_solapamientos",
    "Cortes cuyo rango de PD se cruza con el del grupo anterior.",
    "Una fila por grupo solapado, ordenada por el tamaño del solapamiento.",
    "Vacía. Una fila no es necesariamente un error — puede ser una regla de "
    "negocio —, pero cambia cómo se lee el tablero y tiene que ser una "
    "decisión conocida.")
