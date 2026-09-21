"""Ranking de anomalías: qué se movió más este mes.

NO es un panel de alertas binarias. Con 96 celdas segmento × producto
moviéndose cada mes por razones normales, un semáforo se vuelve ruido y deja
de mirarse a las tres semanas. Esto es un RANKING de lo que más se salió de su
propia historia, que siempre muestra sus primeras filas aunque ninguna sea
grave: la pregunta no es "¿hay alarma?" sino "¿qué miro primero?".

Va primera porque es la que dice dónde mirar. Panorama responde qué está
pasando; esta responde dónde.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import data
import theme

desde = st.session_state["desde"]
hasta = st.session_state["hasta"]
mes = st.session_state["mes"]

st.markdown("# Qué se movió este mes")
st.markdown(
    '<p class="sub">Celdas <b>segmento × producto</b> ordenadas por cuánto se '
    'salieron de <b>su propia</b> historia. Siempre se muestran las primeras, '
    'haya o no algo grave: es un ranking, no una alarma.</p>',
    unsafe_allow_html=True)

# La historia completa, no la ventana: el baseline necesita todos los meses
# que haya. El recorte de ventana solo aplica al mes que se compara.
cob = data.cobertura_producto()

with st.sidebar:
    st.markdown("## Ranking")
    tope = st.slider("Filas a mostrar", 5, 40, 15, key="p0a_tope")
    metrica = st.radio(
        "Métrica", ["cantidad", "cobertura"], key="p0a_metrica",
        format_func=lambda m: ("Clientes calificados" if m == "cantidad"
                               else "Cobertura (% de la base)"),
        help="Son problemas distintos: desaparecer de la tabla no es lo mismo "
             "que quedar sin grupo. Conviene mirar los dos.")

st.info(
    "**Cómo se calcula.** Para cada celda se toma la serie de variaciones "
    "entre **meses consecutivos** de toda su historia y se compara la "
    "variación de este mes contra **la mediana y la MAD** de esa serie, no "
    "contra el promedio y el desvío. "
    "La razón: los incidentes pasados están dentro de la historia, y con "
    "promedio/desvío un incidente infla su propia variabilidad, con lo cual el "
    "siguiente igual parece normal. La mediana no se mueve por unos pocos "
    f"extremos.\n\n"
    f"Se excluyen las celdas que se movieron menos del "
    f"**{charts.PISO_VARIACION:.0%}** (una celda que nunca se mueve tiene MAD "
    f"casi cero y un cambio de 0,3% daría un puntaje enorme) y las que tenían "
    f"menos de **{charts.BASE_MINIMA}** clientes el mes anterior.\n\n"
    f"Los pares de meses **no** consecutivos se descartan del baseline: si "
    f"falta un mes, la variación de ese salto es de dos meses y entra "
    f"inflando la mediana y la MAD, que es justo lo que ensancha el baseline "
    f"y termina tapando una anomalía real.")

an = charts.ranking_anomalias(cob, mes, metrica, tope)
rk, sin_base = an.ranking, an.sin_baseline

# Contra qué mes se compara, dicho siempre y con los dos meses concretos.
if an.idx_base is None:
    st.error(
        f"**No hay ningún mes anterior a {an.mes} en los datos**, así que no "
        f"hay contra qué comparar. El ranking mide variación mes a mes: sin "
        f"un mes previo no existe.")
    st.stop()
if an.hay_hueco:
    st.warning(
        f"**Falta la partición del mes inmediatamente anterior a {an.mes}.** "
        f"La comparación va contra **{an.base}**, a **{an.distancia} meses** "
        f"de distancia, mientras que el baseline se arma con variaciones de "
        f"un mes. Una variación acumulada de {an.distancia} meses se ve más "
        f"grande que una mensual: los puntajes están sobreestimados y sirven "
        f"para ordenar, no como magnitud.")
else:
    st.markdown(
        f'<p class="nota">Comparando <b>{an.mes}</b> contra <b>{an.base}</b>.'
        f'</p>', unsafe_allow_html=True)

es_pct = metrica == "cobertura"


def _fmt(v):
    return theme.fmt_pct(v) if es_pct else theme.fmt_miles(v)


if rk.empty:
    st.success(
        "Ninguna celda con historia suficiente superó el piso de variación "
        "este mes. Es un resultado, no un error: significa que nada se movió "
        "lo bastante como para mirarlo.")
else:
    st.markdown(f"## Las {len(rk)} que más se movieron")
    cab = st.columns([1.5, 1.5, 1, 1, 1.1, 0.9, 1.5])
    # Columnas nombradas con el mes concreto, no "anterior"/"actual": una
    # captura de esta tabla tiene que poder leerse sin la página al lado.
    for c, t in zip(cab, ["Segmento", "Producto", an.col_base, an.col_act,
                          "Variación", "Puntaje", "Historia"]):
        c.markdown(f'<p class="nota" style="font-weight:600;'
                   f'text-transform:uppercase;letter-spacing:.04em;'
                   f'margin-bottom:.2rem">{t}</p>', unsafe_allow_html=True)
    for i, r in rk.iterrows():
        c = st.columns([1.5, 1.5, 1, 1, 1.1, 0.9, 1.5])
        aparte = theme.fuera_de_escala(r["_cod_seg"])
        c[0].markdown(
            f"**{r['segmento']}**" + ("  \n<span style='font-size:.72rem;"
                                      f"color:{theme.INK_MUTED}'>fuera de la "
                                      "escala de valor</span>" if aparte else ""),
            unsafe_allow_html=True)
        c[1].markdown(f"`{r['producto']}`")
        c[2].markdown(_fmt(r[an.col_base]))
        c[3].markdown(_fmt(r[an.col_act]))
        signo = "+" if r["var_rel"] >= 0 else ""
        color = theme.ESTADO_CRITICO if r["var_rel"] < 0 else theme.ESTADO_OK
        c[4].markdown(
            f"<span style='color:{color};font-weight:600'>{signo}"
            f"{r['var_rel'] * 100:.1f}%</span><br>"
            f"<span style='font-size:.72rem;color:{theme.INK_MUTED}'>"
            f"{signo}{_fmt(abs(r['var_abs']))}</span>",
            unsafe_allow_html=True)
        c[5].markdown(f"**{r['puntaje']:.1f}**".replace(".", ","))
        c[6].plotly_chart(charts.mini_serie(r["serie"]),
                          use_container_width=True,
                          config={"displayModeBar": False},
                          key=f"p0a_sp_{i}")

    st.download_button(
        "Descargar el ranking en CSV",
        data=data.csv(rk.drop(columns=["serie"])),
        file_name=f"anomalias_{metrica}_{mes}.csv", mime="text/csv",
        key="p0a_dl")

# --- celdas sin variabilidad histórica -------------------------------------
# Antes recibían puntaje 99,0 y encabezaban el ranking siempre, por un valor
# inventado que empujaba hacia abajo las anomalías medidas. Van aparte.
if not an.sin_variabilidad.empty:
    st.markdown(f"## Sin variabilidad histórica ({len(an.sin_variabilidad)})")
    st.markdown(
        '<p class="sub">Celdas cuya variación entre meses consecutivos fue '
        '<b>siempre la misma</b> en toda su historia (MAD nula) y que este mes '
        'se movieron. El movimiento es real y probablemente lo más llamativo '
        'de la página, pero <b>no hay puntaje</b>: dividir por una dispersión '
        'de cero no da un número, da un centinela. Se ordenan por variación '
        'cruda.</p>',
        unsafe_allow_html=True)
    vis = an.sin_variabilidad.drop(columns=["serie", "_cod_seg"]).copy()
    vis["var_rel"] = vis["var_rel"].map(lambda v: f"{v * 100:+.1f}%")
    st.dataframe(vis, use_container_width=True, hide_index=True)
    st.download_button(
        "Descargar estas celdas en CSV",
        data=data.csv(an.sin_variabilidad.drop(columns=["serie"])),
        file_name=f"sin_variabilidad_{metrica}_{mes}.csv", mime="text/csv",
        key="p0a_dl_sv")

# --- celdas sin baseline ---------------------------------------------------
if not sin_base.empty:
    with st.expander(f"Sin baseline suficiente ({len(sin_base)} celdas)",
                     expanded=False):
        st.markdown(
            f'<p class="sub">Estas celdas tienen menos de '
            f'<b>{charts.MESES_MINIMOS} meses</b> de historia, así que no '
            f'reciben puntaje: calcular una mediana y una MAD con cuatro '
            f'puntos sería fingir una precisión que no hay. Va su variación '
            f'cruda, sin ranking. Con 16 meses de tabla el baseline es usable '
            f'pero justo, y conviene saber cuáles no lo tienen. Los meses '
            f'cuentan solo si son consecutivos.</p>',
            unsafe_allow_html=True)
        vis = sin_base.drop(columns=["serie", "_cod_seg"]).copy()
        vis["var_rel"] = vis["var_rel"].map(lambda v: f"{v * 100:+.1f}%")
        st.dataframe(vis, use_container_width=True, hide_index=True)

# --- la matriz completa ----------------------------------------------------
st.markdown("---")
st.markdown("## La matriz completa")
st.markdown(
    '<p class="sub">El ranking dice qué mirar; esto dice dónde está parado. '
    'Las 96 celdas de una vez.</p>',
    unsafe_allow_html=True)
modo = st.radio("Modo", list(charts.MODOS_MATRIZ), horizontal=True,
                key="p0a_modo", format_func=lambda m: charts.MODOS_MATRIZ[m])
st.plotly_chart(charts.matriz_segmento_producto(cob, mes, modo),
                use_container_width=True, key="p0a_matriz")
