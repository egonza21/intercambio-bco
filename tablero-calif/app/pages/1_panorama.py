"""Panorama del mes: cómo se reparte la cartera entre grupos de riesgo.

Página FUNCIONAL (equipo comercial y de negocio). La pregunta es cómo está
repartida la cartera, no cómo se comporta el modelo.
"""
from __future__ import annotations

import streamlit as st

import charts
import data
import theme

desde = st.session_state["desde"]
hasta = st.session_state["hasta"]
mes = st.session_state["mes"]

st.markdown("# Panorama del mes")
st.markdown(
    f'<p class="sub">Composición de la cartera por grupo de riesgo en '
    f'<b>{theme.etiqueta_mes_idx(mes)}</b>. Todo en participación y no en '
    f'conteo: la base viene cayendo, y apilar conteos hace leer esa '
    f'contracción como mejora del riesgo.</p>',
    unsafe_allow_html=True)

dist = data.distribucion_grupo(desde, hasta)
base = data.base_clientes(desde, hasta)
cob = data.cobertura_producto(desde, hasta)

dist_mes = dist[dist["idx_mes"] == mes]
base_mes = base[base["idx_mes"] == mes]
cob_mes = cob[cob["idx_mes"] == mes]

with st.sidebar:
    st.markdown("## Filtros de la página")
    familias = ["todas"] + sorted({data.FAMILIA_PRODUCTO.get(p, "otra")
                                   for p in dist_mes.get("producto", [])})
    familia = st.selectbox("Familia de producto", familias, key="p1_familia")
    productos = ["todos"] + sorted(dist_mes.get("producto", []).unique().tolist())
    producto_hm = st.selectbox("Producto (heatmap)", productos, key="p1_prod")
    segmentos = ["todos"] + sorted(cob_mes.get("segmento", []).unique().tolist())
    segmento_cob = st.selectbox("Segmento (cobertura)", segmentos, key="p1_seg")

# --- KPIs ------------------------------------------------------------------
clientes = base_mes["clientes"].sum() if not base_mes.empty else None
prev = base[base["idx_mes"] == mes - 1]["clientes"].sum() if not base.empty else 0
delta = (clientes / prev - 1) if (clientes and prev) else None

bajo = None
if not dist_mes.empty:
    consumo = dist_mes[dist_mes["producto"] == "consumo"]
    if not consumo.empty:
        bajo = (consumo[consumo["grupo_orden"] <= 30]["clientes"].sum()
                / consumo["clientes"].sum())

k1, k2, k3, k4 = st.columns([1, 1, 1, 1.4])
k1.metric("Clientes en la base", theme.fmt_miles(clientes),
          delta=(theme.fmt_pct(delta) if delta is not None else None),
          help="Base del mes sobre la tabla ancha, no la larga.")
k2.metric("En G1–G3 · consumo", theme.fmt_pct(bajo) if bajo is not None else "--",
          help="Participación de los tres mejores grupos en el producto consumo.")
k3.metric("Productos con calificación",
          theme.fmt_miles(dist_mes["producto"].nunique()) if not dist_mes.empty else "--")
k4.metric("Segmentos",
          theme.fmt_miles(base_mes["segmento"].nunique()) if not base_mes.empty else "--")

# --- gráfico ancla ---------------------------------------------------------
st.markdown("## Composición de grupo por producto")
st.markdown(
    '<p class="sub">Cada barra suma 100% de los clientes con calificación en '
    'ese producto. Los productos están ordenados por su masa en G6 y peores, '
    'así que la lista ya viene rankeada por riesgo.</p>',
    unsafe_allow_html=True)
st.plotly_chart(charts.composicion_grupo(dist_mes, familia),
                use_container_width=True, key="p1_comp")
st.markdown(
    '<p class="nota">En <b>sufi_moto</b>, <b>sufi_cpe</b> y <b>sufi_con</b> los '
    'grupos G7 y G8 vienen abiertos en bajo, medio y alto. Toman tonos '
    'contiguos dentro del tramo de su grupo base.</p>',
    unsafe_allow_html=True)

c1, c2 = st.columns([1.15, 1])
with c1:
    st.markdown("## Segmento × grupo")
    st.markdown('<p class="sub">Cada fila suma 100% del segmento.</p>',
                unsafe_allow_html=True)
    st.plotly_chart(charts.heatmap_segmento_grupo(dist_mes, producto_hm),
                    use_container_width=True, key="p1_hm")
with c2:
    st.markdown("## Cobertura por producto")
    st.markdown('<p class="sub">Clientes con grupo sobre la base del mes.</p>',
                unsafe_allow_html=True)
    st.plotly_chart(charts.cobertura(cob_mes, segmento_cob),
                    use_container_width=True, key="p1_cob")

# --- comparador de dos meses ----------------------------------------------
st.markdown("---")
st.markdown("## Comparar dos meses")
st.markdown(
    '<p class="sub">Lado a lado, la misma composición en dos cortes. Es la '
    'vista que en Power BI obligaría a duplicar la página.</p>',
    unsafe_allow_html=True)
meses_disp = data.meses_disponibles(dist)
if len(meses_disp) >= 2:
    cc1, cc2 = st.columns(2)
    with cc1:
        m_a = st.selectbox("Mes A", meses_disp, index=0,
                           format_func=theme.etiqueta_mes_idx, key="p1_ma")
        st.plotly_chart(charts.composicion_grupo(dist[dist["idx_mes"] == m_a], familia),
                        use_container_width=True, key="p1_cmp_a")
    with cc2:
        m_b = st.selectbox("Mes B", meses_disp, index=len(meses_disp) - 1,
                           format_func=theme.etiqueta_mes_idx, key="p1_mb")
        st.plotly_chart(charts.composicion_grupo(dist[dist["idx_mes"] == m_b], familia),
                        use_container_width=True, key="p1_cmp_b")
else:
    st.info("Se necesitan al menos dos meses en la ventana para comparar.")

# --- descarga --------------------------------------------------------------
st.markdown("---")
st.download_button(
    "Descargar la distribución del mes en CSV",
    data=data.csv(dist_mes), file_name=f"distribucion_grupo_{mes}.csv",
    mime="text/csv", key="p1_dl")
