"""Modelos: cómo se comporta el modelo, no cómo se reparte la cartera.

Página de MODELOS (seguimiento técnico). `producto` NO es dimensión válida acá
salvo en sensibilidad de cortes: solo hay dos PD, así que un histograma "por
producto" serían doce copias del mismo histograma. Los cortes SÍ son por
producto, y por eso ese visual es la excepción.
"""
from __future__ import annotations

import streamlit as st

import charts
import data
import theme

desde = st.session_state["desde"]
hasta = st.session_state["hasta"]
mes = st.session_state["mes"]

st.markdown("# Modelos")
st.markdown(
    '<p class="sub">Solo hay dos PD: una para los doce productos que no son de '
    'vivienda y otra para los cuatro que sí. La PD es del cliente; lo que es '
    'del producto son los <b>cortes</b> que la traducen a grupo.</p>',
    unsafe_allow_html=True)

pdm = data.pd_por_modelo(desde, hasta)
cortes = data.cortes_por_producto(desde, hasta)

with st.sidebar:
    st.markdown("## Filtros de la página")
    series = sorted(pdm["serie_pd"].unique().tolist()) if not pdm.empty else ["general"]
    serie = st.radio("Serie de PD", series, horizontal=True, key="p4_serie")
    escalas = sorted(pdm["escala"].unique().tolist()) if not pdm.empty else []
    escala = st.selectbox(
        "Escala", escalas, key="p4_escala",
        format_func=lambda e: ("puntaje 0–999" if e == "puntaje_0_999"
                               else "probabilidad 0–1")) if escalas else None

pdm_serie = pdm[pdm["serie_pd"] == serie] if not pdm.empty else pdm
pdm_mes = pdm_serie[pdm_serie["idx_mes"] == mes] if not pdm_serie.empty else pdm_serie
cortes_mes = cortes[cortes["idx_mes"] == mes] if not cortes.empty else cortes

# --- KPIs ------------------------------------------------------------------
psi = charts.psi_series(pdm, serie)
psi_ult = psi[psi["idx_mes"] == psi["idx_mes"].max()] if not psi.empty else psi
peor = psi_ult.loc[psi_ult["psi"].idxmax()] if not psi_ult.empty else None
solap = charts.tabla_solapamientos(cortes_mes)

k1, k2, k3, k4 = st.columns([1.2, 1, 1, 1])
k1.metric("Peor PSI del último mes",
          f"{peor['psi']:.3f}".replace(".", ",") if peor is not None else "--",
          help=f"Modelo {peor['modelo']}" if peor is not None else None)
k2.metric("Modelos activos",
          theme.fmt_miles(pdm_mes["modelo"].nunique()) if not pdm_mes.empty else "--")
k3.metric("Cortes solapados", theme.fmt_miles(len(solap)) if solap is not None else "0",
          help="Rangos de PD que se cruzan entre grupos consecutivos.")
k4.metric("Productos con cortes",
          theme.fmt_miles(cortes_mes["producto"].nunique()) if not cortes_mes.empty else "--")

# --- sensibilidad de cortes: el visual ancla -------------------------------
st.markdown("## Sensibilidad de cortes")
st.markdown(
    '<p class="sub">Dónde cae cada frontera G1–G8, por producto, sobre la PD en '
    'escala logarítmica. Como todos los productos traducen la <b>misma</b> PD, '
    'las filas se comparan verticalmente: un corte desplazado se ve como una '
    'banda corrida respecto de la de al lado. Las cruces rojas marcan '
    'solapamientos.</p>',
    unsafe_allow_html=True)
with st.sidebar:
    modelos_c = (["todos"] + sorted(cortes_mes["modelo"].dropna().unique().tolist())
                 if not cortes_mes.empty else ["todos"])
    modelo_c = st.selectbox("Modelo (cortes)", modelos_c, key="p4_modelo")
st.plotly_chart(charts.sensibilidad_cortes(cortes_mes, modelo_c),
                use_container_width=True, key="p4_cortes")

# --- alerta de solapamientos ----------------------------------------------
st.markdown("### Solapamientos de corte")
if solap is None or solap.empty:
    st.success(
        "Ningún solapamiento en este mes: en cada producto, el máximo de un "
        "grupo queda por debajo del mínimo del siguiente. Los cortes son "
        "consistentes con una traducción puramente por PD.")
else:
    st.warning(
        f"{len(solap)} combinaciones con rangos cruzados. Dos clientes con la "
        f"misma PD quedaron en grupos distintos, así que el corte de ese "
        f"producto no depende solo de la PD. Puede ser una regla de negocio "
        f"legítima, pero tiene que ser una decisión conocida.")
    st.dataframe(
        solap, use_container_width=True, hide_index=True,
        column_config={
            "pd_min": st.column_config.NumberColumn("PD mín", format="%.5f"),
            "pd_max": st.column_config.NumberColumn("PD máx", format="%.5f"),
            "pd_max_grupo_previo": st.column_config.NumberColumn("PD máx anterior",
                                                                 format="%.5f"),
            "solapamiento": st.column_config.NumberColumn("solapamiento", format="%.5f"),
            "clientes": st.column_config.NumberColumn("clientes", format="%d"),
        })
    st.download_button("Descargar solapamientos en CSV", data=data.csv(solap),
                       file_name=f"solapamientos_{mes}.csv", mime="text/csv",
                       key="p4_dl_sol")

# --- histograma y PSI ------------------------------------------------------
st.markdown("---")
c1, c2 = st.columns(2)
with c1:
    st.markdown("## Histograma de PD")
    st.markdown(
        '<p class="sub">Una traza por modelo, eje logarítmico. Las dos escalas '
        'van en gráficos separados: un puntaje de 0 a 999 y una probabilidad '
        'no comparten unidad.</p>', unsafe_allow_html=True)
    if escala:
        st.plotly_chart(charts.histograma_pd(pdm_mes, escala),
                        use_container_width=True, key="p4_hist")
    else:
        st.info("Sin datos de PD para esta ventana.")
with c2:
    st.markdown("## PSI en el tiempo")
    st.markdown(
        '<p class="sub">Contra el primer mes de la ventana, sobre bins de '
        'ancho fijo. Los umbrales van como líneas tenues, no como series.</p>',
        unsafe_allow_html=True)
    st.plotly_chart(charts.psi_tiempo(pdm, serie),
                    use_container_width=True, key="p4_psi")

st.markdown(
    '<p class="nota">Los bins de probabilidad son logarítmicos, 20 por década. '
    'Con bins lineales de 0,05 toda la población caía en el primer bin y el PSI '
    'daba cero siempre, que se lee como estabilidad y en realidad es ceguera '
    'del instrumento.</p>', unsafe_allow_html=True)

st.markdown("---")
st.download_button("Descargar cortes del mes en CSV", data=data.csv(cortes_mes),
                   file_name=f"cortes_por_producto_{mes}.csv", mime="text/csv",
                   key="p4_dl")
