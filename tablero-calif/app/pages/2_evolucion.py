"""Evolución: cómo se mueve la cartera mes a mes.

Página FUNCIONAL. La mezcla va en porcentaje; el conteo absoluto tiene su
propio visual, abajo, para que la contracción de la base se lea como lo que es.
"""
from __future__ import annotations

import streamlit as st

import charts
import data
import theme

desde = st.session_state["desde"]
hasta = st.session_state["hasta"]

st.markdown("# Evolución")
st.markdown(
    f'<p class="sub">De {theme.etiqueta_mes_idx(desde)} a '
    f'{theme.etiqueta_mes_idx(hasta)}. La mezcla de riesgo va en participación; '
    f'la caída de la base se mira aparte, porque una cosa explica la otra.</p>',
    unsafe_allow_html=True)

dist = data.distribucion_grupo(desde, hasta)
base = data.base_clientes(desde, hasta)

with st.sidebar:
    st.markdown("## Filtros de la página")
    productos = sorted(dist["producto"].unique().tolist()) if not dist.empty else []
    producto = st.selectbox(
        "Producto", productos,
        index=productos.index("consumo") if "consumo" in productos else 0,
        key="p2_prod") if productos else "todos"

# --- KPIs ------------------------------------------------------------------
k1, k2, k3 = st.columns([1, 1, 1])
if not base.empty:
    por_mes = base.groupby("idx_mes")["clientes"].sum().sort_index()
    ini, fin = por_mes.iloc[0], por_mes.iloc[-1]
    k1.metric("Base al inicio", theme.fmt_miles(ini),
              help=theme.etiqueta_mes_idx(int(por_mes.index[0])))
    k2.metric("Base al cierre", theme.fmt_miles(fin),
              delta=theme.fmt_pct(fin / ini - 1) if ini else None,
              help=theme.etiqueta_mes_idx(int(por_mes.index[-1])))
    k3.metric("Meses en la ventana", theme.fmt_miles(len(por_mes)))

st.markdown("## Mezcla de riesgo en el tiempo")
st.markdown(
    f'<p class="sub">Producto <b>{producto}</b>. Cada mes suma 100%: lo que se '
    f've es cómo cambia el reparto, no cuántos clientes hay.</p>',
    unsafe_allow_html=True)
st.plotly_chart(charts.mezcla_riesgo(dist, producto),
                use_container_width=True, key="p2_mezcla")

c1, c2 = st.columns(2)
with c1:
    st.markdown("## Base de clientes")
    st.markdown('<p class="sub">Conteo absoluto por segmento.</p>',
                unsafe_allow_html=True)
    st.plotly_chart(charts.base_clientes_tiempo(base),
                    use_container_width=True, key="p2_base")
with c2:
    st.markdown("## Vigencia de modelos")
    st.markdown(
        '<p class="sub">Participación de la población por modelo. Un escalón '
        'acá suele explicar un salto en las otras páginas.</p>',
        unsafe_allow_html=True)
    st.plotly_chart(charts.vigencia_modelos(dist),
                    use_container_width=True, key="p2_vig")

st.markdown(
    '<p class="nota">Las series llevan color <b>y</b> estilo de línea distinto, '
    'para que se lean también impresas o en blanco y negro. Cuando hay más de '
    'cuatro, las menores se agrupan en «otros» en vez de generar colores '
    'nuevos.</p>',
    unsafe_allow_html=True)

st.markdown("---")
c1, c2 = st.columns(2)
c1.download_button("Descargar base de clientes en CSV", data=data.csv(base),
                   file_name="base_clientes.csv", mime="text/csv", key="p2_dl1")
c2.download_button("Descargar distribución en CSV", data=data.csv(dist),
                   file_name="distribucion_grupo.csv", mime="text/csv", key="p2_dl2")
