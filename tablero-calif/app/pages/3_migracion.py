"""Migración: quién cambió de grupo, y si eso fue riesgo o población.

La matriz de grupo es FUNCIONAL; la de deciles de PD es de MODELOS y está acá
solo porque comparte el parámetro de rezago. No se leen igual: ver la nota.
"""
from __future__ import annotations

import streamlit as st

import charts
import data
import theme

desde = st.session_state["desde"]
hasta = st.session_state["hasta"]
mes = st.session_state["mes"]

st.markdown("# Migración")

with st.sidebar:
    st.markdown("## Filtros de la página")
    rezago = st.radio(
        "Rezago", [1, 6], horizontal=True, key="p3_rezago",
        format_func=lambda r: "1 mes" if r == 1 else "6 meses",
        help="Rezago 1 mide rotación; rezago 6 mide desplazamiento neto. "
             "No son encadenables: seis matrices mensuales no dan la semestral.")
    mismo_seg = st.checkbox(
        "Solo clientes que no cambiaron de segmento", value=True, key="p3_seg",
        help="Un cliente que cambia de segmento no cambió de riesgo, pero al "
             "filtrar por segmento aparece como salida y entrada.")

# El origen es idx_mes - rezago, así que los primeros meses de la tabla no
# tienen contra qué compararse. Ver CLAUDE.md.
primer_valido = theme.idx_mes(2025, 5) + rezago
desde_ok = max(desde, primer_valido)

st.markdown(
    f'<p class="sub">Comparación contra <b>{rezago}</b> '
    f'{"mes" if rezago == 1 else "meses"} atrás. La primera matriz válida con '
    f'este rezago es la de <b>{theme.etiqueta_mes_idx(primer_valido)}</b>: '
    f'antes de eso no hay mes de origen y todo saldría clasificado como '
    f'entrada, que sería un artefacto del borde de la ventana.</p>',
    unsafe_allow_html=True)

if hasta < primer_valido:
    st.warning(
        f"La ventana termina en {theme.etiqueta_mes_idx(hasta)}, antes del "
        f"primer mes comparable con rezago {rezago} "
        f"({theme.etiqueta_mes_idx(primer_valido)}). Ampliá la ventana.")
    st.stop()


# Los agregados llegan ENTEROS desde la capa construida. El recorte de la
# ventana se hace acá, en pandas: es instantáneo y no vuelve a Impala.
def _ventana(df):
    if df.empty or "idx_mes" not in df.columns:
        return df
    return df[df["idx_mes"].between(desde_ok, hasta)]


mig = _ventana(data.migracion(rezago))
mes_mig = max(mes, primer_valido)
mig_mes = mig[mig["idx_mes"] == mes_mig]

with st.sidebar:
    productos = sorted(mig["producto"].unique().tolist()) if not mig.empty else []
    producto = st.selectbox(
        "Producto", productos,
        index=productos.index("consumo") if "consumo" in productos else 0,
        key="p3_prod") if productos else "todos"

# --- KPIs ------------------------------------------------------------------
serie = charts.serie_estabilidad(mig, producto)
fila = serie[serie["idx_mes"] == mes_mig]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Estabilidad",
          theme.fmt_pct(fila["estabilidad"].iloc[0]) if not fila.empty else "--",
          help="Masa en la diagonal: clientes que se quedaron en su grupo.")
k2.metric("Deterioro neto",
          theme.fmt_pct(fila["deterioro_neto"].iloc[0]) if not fila.empty else "--",
          help="Masa bajo la diagonal menos masa sobre ella.")
if not mig_mes.empty:
    d = mig_mes[mig_mes["producto"] == producto] if producto != "todos" else mig_mes
    k3.metric("Entradas", theme.fmt_miles(
        d[d["categoria"].isin(["entrada", "ganancia_elegibilidad"])]["clientes"].sum()))
    k4.metric("Salidas", theme.fmt_miles(
        d[d["categoria"].isin(["salida", "perdida_elegibilidad"])]["clientes"].sum()))

st.markdown(f"## Matriz de migración · {theme.etiqueta_mes_idx(mes_mig)}")
st.markdown(
    '<p class="sub">El tono dice la dirección (azul mejora, rojo deterioro) y '
    'la intensidad, el volumen como porcentaje de la fila de origen. La '
    'diagonal queda neutra a propósito, sin importar su masa: es estabilidad, '
    'no señal. Entradas, salidas y elegibilidad van al pie, en gris, fuera de '
    'la escala de riesgo.</p>',
    unsafe_allow_html=True)
st.plotly_chart(charts.matriz_migracion(mig_mes, producto, mismo_seg),
                use_container_width=True, key="p3_matriz")

st.markdown("## Estabilidad y deterioro en el tiempo")
st.plotly_chart(charts.estabilidad_deterioro(mig, producto),
                use_container_width=True, key="p3_estab")

# --- peores saltos ---------------------------------------------------------
st.markdown("---")
st.markdown("## Peores saltos")
st.markdown(
    '<p class="sub">Combinaciones origen → destino con caída de tres grupos o '
    'más, por volumen. Es una tabla y no un gráfico a propósito: lo que se '
    'quiere es el listado accionable, no la forma.</p>',
    unsafe_allow_html=True)
saltos = charts.tabla_peores_saltos(mig_mes if not mig_mes.empty else mig)
if saltos.empty:
    st.success("Ningún salto de tres grupos o más en este corte.")
else:
    st.dataframe(saltos, use_container_width=True, hide_index=True,
                 column_config={
                     "clientes": st.column_config.NumberColumn("clientes", format="%d"),
                     "saltos": st.column_config.NumberColumn("grupos de caída"),
                 })
    st.download_button("Descargar peores saltos en CSV", data=data.csv(saltos),
                       file_name="peores_saltos.csv", mime="text/csv", key="p3_dl")

# --- migración de PD -------------------------------------------------------
st.markdown("---")
st.markdown("## Migración de deciles de PD")
st.markdown(
    '<p class="sub"><b>No se lee como la de arriba.</b> Los deciles se '
    'recalculan cada mes, así que esto mide reordenamiento del ranking, no '
    'desplazamiento de la distribución. Una diagonal fuerte acá dice que el '
    'orden se mantuvo, no que la PD no se movió: eso lo dice el PSI, en la '
    'página de Modelos.</p>',
    unsafe_allow_html=True)

mig_pd = _ventana(data.migracion_pd(rezago))
if mig_pd.empty:
    st.info("Sin datos de migración de PD para esta ventana.")
else:
    serie_pd = st.radio("Serie de PD", sorted(mig_pd["serie_pd"].unique()),
                        horizontal=True, key="p3_serie")
    st.plotly_chart(
        charts.matriz_migracion_pd(mig_pd[mig_pd["idx_mes"] == mes_mig], serie_pd),
        use_container_width=True, key="p3_matriz_pd")
    st.markdown(
        '<p class="nota">Los valores anotados son el porcentaje del decil de '
        'origen, no el conteo: con diez deciles el conteo no entra legible en '
        'la celda.</p>', unsafe_allow_html=True)
