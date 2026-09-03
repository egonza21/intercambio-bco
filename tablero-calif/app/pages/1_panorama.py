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

with st.sidebar:
    st.markdown("## Filtros de la página")
    st.markdown('<p class="nota">Se aplican a TODO: KPIs, composición, '
                'heatmap, cobertura y comparador.</p>', unsafe_allow_html=True)
    familias = ["todas"] + sorted({data.FAMILIA_PRODUCTO.get(p, "otra")
                                   for p in dist.get("producto", [])})
    familia = st.selectbox("Familia de producto", familias, key="p1_familia")
    _prods = [p for p in theme.PRODUCTOS_ORDENADOS
              if p in set(dist.get("producto", []))]
    if familia != "todas":
        _prods = [p for p in _prods if data.FAMILIA_PRODUCTO.get(p) == familia]
    producto = st.selectbox("Producto", ["todos"] + _prods, key="p1_prod")
    _segs = theme.segmentos_ordenados(dist.get("segmento", []))
    segmento = st.selectbox(
        "Segmento", ["todos"] + _segs, key="p1_seg",
        format_func=lambda c: "todos" if c == "todos" else theme.etiqueta_segmento(c))
    normalizar_hm = st.toggle(
        "Heatmap normalizado por fila", value=True, key="p1_norm",
        help="Normalizado: cada segmento suma 100% y el color dice el reparto "
             "interno. Sin normalizar: el color es el conteo absoluto y los "
             "segmentos grandes dominan.")
    apilado_pct = st.toggle(
        "Composición en porcentaje", value=True, key="p1_pct",
        help="Apagado cambia a apilado ABSOLUTO, que es un gráfico distinto: "
             "muestra el volumen y no el reparto.")


# --- EL FILTRO SE APLICA ACÁ, ANTES DE TODO --------------------------------
# Antes los filtros solo llegaban a algunos visuales: los KPIs y el comparador
# seguían con la población completa, así que filtrar Banca Privada mostraba
# 7 mil clientes en la matriz y 15 MM en el KPI de al lado.
def _filtrar(df):
    if df.empty:
        return df
    d = df
    if segmento != "todos" and "segmento" in d.columns:
        d = d[d["segmento"].map(theme._cod) == theme._cod(segmento)]
    if producto != "todos" and "producto" in d.columns:
        d = d[d["producto"] == producto]
    elif familia != "todas" and "producto" in d.columns:
        d = d[d["producto"].map(data.FAMILIA_PRODUCTO) == familia]
    return d


hay_filtro = (segmento != "todos" or producto != "todos" or familia != "todas")

dist_f = _filtrar(dist)
base_f = base if segmento == "todos" else base[
    base["segmento"].map(theme._cod) == theme._cod(segmento)]
cob_f = _filtrar(cob)

dist_mes = dist_f[dist_f["idx_mes"] == mes]
base_mes = base_f[base_f["idx_mes"] == mes]
cob_mes = cob_f[cob_f["idx_mes"] == mes]

# --- KPIs ------------------------------------------------------------------
clientes = base_mes["clientes"].sum() if not base_mes.empty else None
prev = (base_f[base_f["idx_mes"] == mes - 1]["clientes"].sum()
        if not base_f.empty else 0)
delta = (clientes / prev - 1) if (clientes and prev) else None

# Un KPI que dice "7.043 clientes" sin decir de qué es una cifra huérfana en
# cuanto alguien saca captura. Con filtro activo, el contexto va al lado.
if hay_filtro:
    partes = []
    if segmento != "todos":
        partes.append(f"segmento <b>{theme.etiqueta_segmento(segmento)}</b>")
    if producto != "todos":
        partes.append(f"producto <b>{producto}</b>")
    elif familia != "todas":
        partes.append(f"familia <b>{familia}</b>")
    total_mes = (base[base["idx_mes"] == mes]["clientes"].sum()
                 if not base.empty else 0)
    prop = (clientes / total_mes) if (clientes and total_mes) else None
    st.markdown(
        f'<div style="background:#eef4fb;border:1px solid {theme.SERIES[0]};'
        f'border-radius:10px;padding:.6rem .9rem;margin:.2rem 0 1rem">'
        f'<span style="font-size:.85rem">Filtrado por {" · ".join(partes)}. '
        f'Todo lo de abajo — KPIs incluidos — responde a este filtro.'
        + (f' Son el <b>{theme.fmt_pct(prop)}</b> de la base del mes '
           f'({theme.fmt_miles(total_mes)} clientes).' if prop else "")
        + '</span></div>', unsafe_allow_html=True)


def banda(df_mes, desde_orden: int, hasta_orden: int, producto: str):
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


# Filtrado también: si no, la variación compara manzanas con peras.
dist_prev = dist_f[dist_f["idx_mes"] == mes - 1]
# La banda se mide sobre el producto elegido; sin filtro, consumo.
_prod_kpi = producto if producto != "todos" else "consumo"
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
    act = banda(dist_mes, lo, hi, _prod_kpi)
    ant = banda(dist_prev, lo, hi, _prod_kpi)
    var = (act - ant) if (act is not None and ant is not None) else None
    col.metric(f"{nombre} · {_prod_kpi}",
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
    ('<p class="sub">Cada barra suma 100% de los clientes con calificación en '
     'ese producto. Los productos están ordenados por su masa en G6 y peores, '
     'así que la lista ya viene rankeada por riesgo.</p>' if apilado_pct else
     '<p class="sub"><b>Apilado absoluto</b>, no porcentual: las barras miden '
     'volumen y por eso tienen largos distintos. Es un gráfico distinto del '
     'de composición, no el mismo en otra unidad — acá se ve el tamaño de '
     'cada producto, no cómo se reparte por dentro.</p>'),
    unsafe_allow_html=True)
st.plotly_chart(charts.composicion_grupo(dist_mes, "todas",
                                        porcentaje=apilado_pct),
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
        charts.heatmap_segmento_grupo(dist_mes, "todos", normalizar_hm),
        use_container_width=True, key="p1_hm")
with c2:
    st.markdown("## Cobertura por producto")
    st.markdown('<p class="sub">Clientes con grupo sobre la base del mes.</p>',
                unsafe_allow_html=True)
    st.plotly_chart(charts.cobertura(cob_mes, "todos"),
                    use_container_width=True, key="p1_cob")

# --- matriz segmento x producto -------------------------------------------
st.markdown("---")
st.markdown("## Segmento × producto")
st.markdown(
    '<p class="sub">Las 96 celdas de una vez. Los tres modos no son '
    'redundantes: si un mes desaparecen filas enteras en vez de quedar con '
    'grupo nulo, la <b>cobertura</b> no se mueve — bajan numerador y '
    'denominador a la vez — pero la <b>cantidad</b> sí.</p>',
    unsafe_allow_html=True)
modo_m = st.radio("Modo", list(charts.MODOS_MATRIZ), horizontal=True,
                  key="p1_modo", format_func=lambda m: charts.MODOS_MATRIZ[m])
st.plotly_chart(charts.matriz_segmento_producto(cob_f, mes, modo_m),
                use_container_width=True, key="p1_matriz")

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
meses_disp = data.meses_disponibles(dist_f)
if len(meses_disp) >= 2:
    cc1, cc2 = st.columns(2)
    with cc1:
        m_a = st.selectbox("Mes A", meses_disp, index=0,
                           format_func=theme.etiqueta_mes_idx, key="p1_ma")
        st.plotly_chart(
            charts.composicion_grupo(dist_f[dist_f["idx_mes"] == m_a], "todas",
                                     orden_productos=theme.PRODUCTOS_ORDENADOS,
                                     porcentaje=apilado_pct),
            use_container_width=True, key="p1_cmp_a")
    with cc2:
        m_b = st.selectbox("Mes B", meses_disp, index=len(meses_disp) - 1,
                           format_func=theme.etiqueta_mes_idx, key="p1_mb")
        st.plotly_chart(
            charts.composicion_grupo(dist_f[dist_f["idx_mes"] == m_b], "todas",
                                     orden_productos=theme.PRODUCTOS_ORDENADOS,
                                     porcentaje=apilado_pct),
            use_container_width=True, key="p1_cmp_b")
else:
    st.info("Se necesitan al menos dos meses en la ventana para comparar.")

# --- descarga --------------------------------------------------------------
st.markdown("---")
st.download_button(
    "Descargar la distribución del mes en CSV",
    data=data.csv(dist_mes), file_name=f"distribucion_grupo_{mes}.csv",
    mime="text/csv", key="p1_dl")
