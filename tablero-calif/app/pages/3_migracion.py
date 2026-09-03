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
        "Excluir clientes que cambiaron de segmento", value=True, key="p3_seg")
    st.markdown(
        '<p class="nota">Un cliente que pasa de un segmento a otro aparece '
        'perdiendo elegibilidad en unos productos y ganándola en otros sin que '
        'su riesgo haya cambiado. Excluirlos deja ver la migración real.</p>',
        unsafe_allow_html=True)

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
    productos = [p for p in theme.PRODUCTOS_ORDENADOS
                 if p in set(mig.get("producto", []))]
    producto = st.selectbox(
        "Producto", productos,
        index=productos.index("consumo") if "consumo" in productos else 0,
        key="p3_prod") if productos else "todos"
    _segs = theme.segmentos_ordenados(mig.get("segmento_actual", []))
    segmento = st.selectbox(
        "Segmento", ["todos"] + _segs, key="p3_segfiltro",
        format_func=lambda c: "todos" if c == "todos" else theme.etiqueta_segmento(c))

# --- contexto: contra qué mes se compara, sacado del dato -------------------
mes_origen = mes_mig - rezago
st.markdown(
    f'<p class="sub" style="font-size:1rem;color:{theme.INK}">'
    f'<b>{theme.etiqueta_mes_idx(mes_mig)}</b> contra '
    f'<b>{theme.etiqueta_mes_idx(mes_origen)}</b>'
    f'<span style="color:{theme.INK_MUTED};font-weight:400"> · producto '
    f'{producto}'
    f'{" · " + theme.etiqueta_segmento(segmento) if segmento != "todos" else ""}'
    f'{" · a segmento constante" if mismo_seg else ""}</span></p>',
    unsafe_allow_html=True)

# --- KPIs: volumen absoluto además del porcentaje --------------------------
serie = charts.serie_estabilidad(mig, producto)
fila = serie[serie["idx_mes"] == mes_mig]
d = mig_mes[mig_mes["producto"] == producto] if producto != "todos" else mig_mes
if segmento != "todos" and not d.empty:
    d = d[d["segmento_actual"].map(theme._cod) == theme._cod(segmento)]
if mismo_seg and not d.empty and "segmento_anterior" in d.columns:
    d = d[d["segmento_anterior"] == d["segmento_actual"]]


def _cat(*cats) -> int:
    if d.empty:
        return 0
    return int(d[d["categoria"].isin(cats)]["clientes"].sum())


comparados = _cat("movimiento")
# Permanecen, mejoran y empeoran, en CANTIDAD además de porcentaje: un 3% de
# deterioro sobre 15 MM y sobre 7 mil no son el mismo problema.
_mov = d[d["categoria"] == "movimiento"] if not d.empty else d
if not _mov.empty:
    _o = _mov["grupo_base_origen"].map(theme.GRUPO_ORDEN)
    _dd = _mov["grupo_base_destino"].map(theme.GRUPO_ORDEN)
    n_igual = int(_mov.loc[_o == _dd, "clientes"].sum())
    n_mejor = int(_mov.loc[_dd < _o, "clientes"].sum())
    n_peor = int(_mov.loc[_dd > _o, "clientes"].sum())
else:
    n_igual = n_mejor = n_peor = 0


def _pc(n):
    return theme.fmt_pct(n / comparados) if comparados else "--"


k = st.columns(6)
k[0].metric("Clientes comparados", theme.fmt_miles(comparados),
            help="Con grupo en los DOS meses. Es el denominador de la matriz: "
                 "los porcentajes de estabilidad y deterioro salen de acá.")
k[1].metric("Permanecen en su G", theme.fmt_miles(n_igual), delta=_pc(n_igual),
            delta_color="off", help="La diagonal de la matriz.")
k[2].metric("Mejoraron", theme.fmt_miles(n_mejor), delta=_pc(n_mejor),
            delta_color="off", help="Pasaron a un grupo de menor riesgo.")
k[3].metric("Empeoraron", theme.fmt_miles(n_peor), delta=_pc(n_peor),
            delta_color="off", help="Pasaron a un grupo de mayor riesgo.")
k[4].metric("Salieron", theme.fmt_miles(_cat("salida")),
            help="No están en la tabla en el mes destino. Cambio de población.")
k[5].metric("Perdieron elegibilidad", theme.fmt_miles(_cat("perdida_elegibilidad")),
            help="Tenían grupo y quedaron SIN grupo, sin irse de la tabla. Es "
                 "una decisión del modelo, no una baja: por eso va aparte de "
                 "las salidas y no sumada con ellas.")

st.markdown(f"## Matriz de migración · {theme.etiqueta_mes_idx(mes_mig)}")
st.markdown(
    '<p class="sub">El tono dice la dirección (azul mejora, rojo deterioro) y '
    'la intensidad, el volumen como porcentaje de la fila de origen. La '
    'diagonal queda neutra a propósito, sin importar su masa: es estabilidad, '
    'no señal. Entradas, salidas y elegibilidad van al pie, en gris, fuera de '
    'la escala de riesgo.</p>',
    unsafe_allow_html=True)
st.plotly_chart(charts.matriz_migracion(mig_mes, producto, mismo_seg, segmento),
                use_container_width=True, key="p3_matriz")

st.markdown("## Estabilidad, mejora y deterioro en el tiempo")
st.markdown(
    '<p class="sub">Tres series, no dos: sin la de mejora, un deterioro neto '
    'estable puede esconder que suben las dos a la vez.</p>',
    unsafe_allow_html=True)
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

# --- flujo entre modelos ---------------------------------------------------
st.markdown("---")
st.markdown("## Flujo de clientes entre modelos")
st.markdown(
    f'<p class="sub">Quién calificaba a cada cliente en '
    f'{theme.etiqueta_mes_idx(mes_origen)} y quién lo califica en '
    f'{theme.etiqueta_mes_idx(mes_mig)}. Es lo que separa <b>reasignación</b> '
    f'de <b>deriva</b>: si el PSI de un modelo sube y acá se ve un flujo '
    f'grande hacia él, la población que le entró es nueva — el modelo no '
    f'cambió, cambió a quién califica.</p>',
    unsafe_allow_html=True)
st.plotly_chart(charts.flujo_modelos(mig_mes, producto),
                use_container_width=True, key="p3_flujo")

# --- migración de PD -------------------------------------------------------
st.markdown("---")
st.markdown("## Migración de deciles de PD")
st.markdown(
    '<p class="sub">Cada <b>fila</b> es el decil de PD del cliente en el mes '
    'anterior; cada <b>columna</b>, el decil del mes actual. La diagonal son '
    'los que se quedaron en su decil. Por debajo de la diagonal, los que '
    'empeoraron; por encima, los que mejoraron.</p>'
    '<p class="sub">Una matriz sana tiene la masa concentrada en la diagonal y '
    'en las celdas contiguas. Masa lejos de la diagonal significa que un grupo '
    'grande de clientes cambió mucho de PD en un mes, y eso normalmente es un '
    '<b>cambio de modelo o un problema de datos</b>, no comportamiento real.</p>'
    '<p class="sub">A diferencia de la migración por producto, esta no depende '
    'de cortes: mide el movimiento de la PD misma. <b>Si la PD se mueve poco '
    'pero la migración por producto muestra mucho movimiento, el problema está '
    'en los cortes, no en los clientes.</b></p>',
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
