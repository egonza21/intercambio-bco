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


# Los agregados llegan ENTEROS desde la capa construida. El recorte de la
# ventana se hace acá, en pandas: es instantáneo y no vuelve a Impala.
def _ventana(df):
    if df.empty or "idx_mes" not in df.columns:
        return df
    return df[df["idx_mes"].between(desde, hasta)]


dist = _ventana(data.distribucion_grupo())
base = _ventana(data.base_clientes())
cob = _ventana(data.cobertura_producto())

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
    normalizar_hm = st.toggle(
        "Heatmap normalizado por fila", value=True, key="p1_norm",
        help="Normalizado: cada segmento suma 100% y el color dice el reparto "
             "interno. Sin normalizar: el color es el conteo absoluto y los "
             "segmentos grandes dominan.")

# --- KPIs ------------------------------------------------------------------
clientes = base_mes["clientes"].sum() if not base_mes.empty else None
prev = base[base["idx_mes"] == mes - 1]["clientes"].sum() if not base.empty else 0
delta = (clientes / prev - 1) if (clientes and prev) else None


def banda(df_mes, desde_orden: int, hasta_orden: int, producto: str = "consumo"):
    """Participación de una banda de grupos dentro de un producto.

    El corte es por `grupo_orden`, no por el texto del grupo: así las aperturas
    de sufi caen en la banda de su grupo base sin tratamiento aparte
    (G7_B, G7_M y G7_A tienen orden 71-73, dentro del tramo de G7).
    """
    if df_mes.empty:
        return None
    p = df_mes[df_mes["producto"] == producto]
    if p.empty or p["clientes"].sum() == 0:
        return None
    en_banda = p[p["grupo_orden"].between(desde_orden, hasta_orden)]["clientes"].sum()
    return en_banda / p["clientes"].sum()


dist_prev = dist[dist["idx_mes"] == mes - 1]
BANDAS = [
    ("G1–G4", 10, 49, "Base ofertable ampliada."),
    ("G5–G6", 50, 69, "Zona intermedia."),
    ("G7–G8", 70, 99, "Cola de riesgo. Incluye las aperturas de sufi "
                      "(G7_B/M/A y G8_B/M/A), agregadas por grupo base."),
]

cols = st.columns([1.25, 1, 1, 1, 0.9])
cols[0].metric("Clientes en la base", theme.fmt_miles(clientes),
               delta=(theme.fmt_pct(delta) if delta is not None else None),
               help="Base del mes sobre la tabla ancha, no la larga.")
for col, (nombre, lo, hi, ayuda) in zip(cols[1:4], BANDAS):
    act = banda(dist_mes, lo, hi)
    ant = banda(dist_prev, lo, hi)
    var = (act - ant) if (act is not None and ant is not None) else None
    col.metric(f"{nombre} · consumo",
               theme.fmt_pct(act) if act is not None else "--",
               delta=(f"{var * 100:+.1f} pp".replace(".", ",")
                      if var is not None else None),
               delta_color="inverse" if nombre != "G1–G4" else "normal",
               help=ayuda + " La variación es en puntos porcentuales contra el "
                            "mes anterior.")
cols[4].metric("Segmentos",
               theme.fmt_miles(base_mes["segmento"].nunique())
               if not base_mes.empty else "--")

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
    st.markdown(
        '<p class="sub">Cada fila suma 100% del segmento, así que el color dice '
        'cómo se reparte ESE segmento y no cuán grande es. Sin normalizar, los '
        'segmentos grandes se llevan todo el color y los chicos se ven vacíos '
        'aunque su reparto sea peor. El otro valor está siempre en el hover.</p>'
        if normalizar_hm else
        '<p class="sub">Sin normalizar: el color es el conteo absoluto. Los '
        'segmentos grandes dominan la escala. El porcentaje dentro de cada '
        'segmento está en el hover.</p>',
        unsafe_allow_html=True)
    st.plotly_chart(
        charts.heatmap_segmento_grupo(dist_mes, producto_hm, normalizar_hm),
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
    '<p class="sub">Lado a lado, la misma composición en dos cortes. Los dos '
    'paneles usan el <b>mismo orden de productos</b>, el del mapeo canónico, '
    'para que cada fila caiga a la misma altura en ambos: si cada panel se '
    'ordenara por sus propios datos, un producto cambiaría de posición entre '
    'meses y la comparación de un vistazo dejaría de servir.</p>',
    unsafe_allow_html=True)
meses_disp = data.meses_disponibles(dist)
if len(meses_disp) >= 2:
    cc1, cc2 = st.columns(2)
    with cc1:
        m_a = st.selectbox("Mes A", meses_disp, index=0,
                           format_func=theme.etiqueta_mes_idx, key="p1_ma")
        st.plotly_chart(
            charts.composicion_grupo(dist[dist["idx_mes"] == m_a], familia,
                                     orden_productos=theme.PRODUCTOS_ORDENADOS),
            use_container_width=True, key="p1_cmp_a")
    with cc2:
        m_b = st.selectbox("Mes B", meses_disp, index=len(meses_disp) - 1,
                           format_func=theme.etiqueta_mes_idx, key="p1_mb")
        st.plotly_chart(
            charts.composicion_grupo(dist[dist["idx_mes"] == m_b], familia,
                                     orden_productos=theme.PRODUCTOS_ORDENADOS),
            use_container_width=True, key="p1_cmp_b")
else:
    st.info("Se necesitan al menos dos meses en la ventana para comparar.")

# --- descarga --------------------------------------------------------------
st.markdown("---")
st.download_button(
    "Descargar la distribución del mes en CSV",
    data=data.csv(dist_mes), file_name=f"distribucion_grupo_{mes}.csv",
    mime="text/csv", key="p1_dl")
