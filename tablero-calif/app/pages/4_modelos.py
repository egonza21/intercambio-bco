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


# Los agregados llegan ENTEROS desde la capa construida. El recorte de la
# ventana se hace acá, en pandas: es instantáneo y no vuelve a Impala.
def _ventana(df):
    if df.empty or "idx_mes" not in df.columns:
        return df
    return df[df["idx_mes"].between(desde, hasta)]


pdm = _ventana(data.pd_por_modelo())
cortes = _ventana(data.cortes_por_producto())
# El PSI de niveles 1 y 2 va sobre GRUPOS, así que sale de distribucion_grupo,
# no de pd_por_modelo. Ver charts.psi_grupos().
dist_grupo = _ventana(data.distribucion_grupo())

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
        '<p class="sub">Cada traza es la distribución de PD de un modelo: qué '
        'porcentaje de su población cae en cada tramo. El eje es logarítmico '
        'porque las PD se concentran en el extremo bajo.</p>'
        '<p class="sub"><b>Qué mirar:</b> que cada modelo tenga una campana '
        'definida y no picos aislados. Un pico angosto significa muchos '
        'clientes con la misma PD exacta, que suele ser un valor por defecto y '
        'no una predicción.</p>'
        '<p class="sub">Las dos escalas van en gráficos separados: un puntaje '
        'de 0 a 999 y una probabilidad no comparten unidad.</p>',
        unsafe_allow_html=True)
    if escala:
        st.plotly_chart(charts.histograma_pd(pdm_mes, escala),
                        use_container_width=True, key="p4_hist")
    else:
        st.info("Sin datos de PD para esta ventana.")
with c2:
    st.markdown("## Vigencia de modelos")
    st.markdown(
        '<p class="sub">Va al lado del PSI a propósito: un escalón acá explica '
        'un salto de PSI sin que ningún modelo haya cambiado.</p>',
        unsafe_allow_html=True)
    st.plotly_chart(charts.vigencia_modelos(dist_grupo),
                    use_container_width=True, key="p4_vig")

# ===========================================================================
# PSI EN TRES NIVELES
# ===========================================================================
st.markdown("---")
st.markdown("# PSI")
st.markdown(
    '<p class="sub">Mide cuánto se movió la población entre grupos de riesgo '
    'frente a un mes de referencia. Si el reparto entre G1 y G8 es igual, da '
    'cero; mientras más población cambie de grupo, más sube.</p>'
    '<p class="sub">Debajo de <b>0,10</b> el cambio es despreciable; entre '
    '<b>0,10 y 0,25</b> hay que revisarlo; por encima de <b>0,25</b> la '
    'población ya no se parece a la de referencia.</p>',
    unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## PSI")
    base_movil = st.radio(
        "Base de comparación", [False, True], key="p4_base",
        format_func=lambda b: ("Mes anterior (cambio mensual)" if b
                               else "Primer mes de la ventana (deriva acumulada)"))
    prod_psi = st.selectbox(
        "Producto (PSI de grupos)",
        ["todos"] + sorted(dist_grupo["producto"].unique().tolist())
        if not dist_grupo.empty else ["todos"], key="p4_prod_psi")
    abrir_sufi = st.toggle(
        "Usar la apertura de sufi", value=False, key="p4_sufi",
        help="Por defecto el PSI va sobre grupo_base (8 categorías). Activado, "
             "usa el grupo crudo con G7_B/M/A y G8_B/M/A.")

col_grupo = "grupo" if abrir_sufi else "grupo_base"
_serie_n1 = charts.psi_grupos(dist_grupo, prod_psi, None, col_grupo, base_movil)
_base_lbl = (theme.etiqueta_mes_idx(int(_serie_n1["idx_base"].iloc[-1]))
             if not _serie_n1.empty else "--")

st.info(
    f"**Regla de lectura.** El nivel 1 es el que dispara acción. Los niveles 2 "
    f"y 3 explican por qué, no deciden. Si el nivel 1 y el 3 se contradicen, "
    f"manda el 1: los grupos son la unidad con la que se oferta.\n\n"
    f"Base de comparación activa: **{_base_lbl}**"
    f"{' (móvil, cambia con cada mes)' if base_movil else ''}.")

# --- Nivel 1 ---------------------------------------------------------------
st.markdown("## Nivel 1 · General")
st.markdown(
    f'<p class="sub"><b>¿Se está moviendo el riesgo del banco?</b> PSI sobre '
    f'la distribución de grupos de toda la población, producto '
    f'<b>{prod_psi}</b>, sin partir por modelo. Es el que decide.</p>',
    unsafe_allow_html=True)
fig1, _, _ = charts.psi_grupos_grafico(dist_grupo, prod_psi, None, col_grupo,
                                       base_movil)
st.plotly_chart(fig1, use_container_width=True, key="p4_psi1")

# --- aporte por grupo ------------------------------------------------------
st.markdown("### De dónde sale el número")
st.markdown(
    '<p class="sub">Qué grupo aporta más al índice. Convierte «el PSI subió a '
    '0,31» en «subió porque G5 pasó de 8% a 14%».</p>',
    unsafe_allow_html=True)
ap = charts.aporte_psi_grupo(dist_grupo, mes, prod_psi, None, col_grupo, base_movil)
if ap.empty:
    st.info("Hacen falta al menos dos meses en la ventana.")
else:
    st.dataframe(
        ap, use_container_width=True, hide_index=True,
        column_config={
            "% en la base": st.column_config.NumberColumn(format="%.1f%%"),
            "% en el mes": st.column_config.NumberColumn(format="%.1f%%"),
            "aporte al PSI": st.column_config.NumberColumn(format="%.4f"),
        })
    st.download_button("Descargar el aporte por grupo en CSV", data=data.csv(ap),
                       file_name=f"aporte_psi_{mes}.csv", mime="text/csv",
                       key="p4_dl_ap")

# --- Nivel 2 ---------------------------------------------------------------
st.markdown("## Nivel 2 · Por modelo")
st.markdown(
    '<p class="sub"><b>¿Qué población le está entrando a este modelo?</b> El '
    'mismo PSI de grupos, filtrado a un modelo.</p>',
    unsafe_allow_html=True)
st.warning(
    "**Esto mide reasignación de población, no deriva del modelo.** Si otro "
    "modelo se lleva parte de sus clientes, este PSI sube sin que el modelo "
    "haya cambiado nada. Contrastalo siempre con *Vigencia de modelos* de "
    "arriba y con el *flujo entre modelos* de la página de Migración.",
    icon="⚠")
modelos_psi = (sorted(dist_grupo["modelo"].dropna().unique().tolist())
               if not dist_grupo.empty else [])
if modelos_psi:
    mod_psi = st.selectbox("Modelo", modelos_psi, key="p4_mod_psi")
    fig2, _, _ = charts.psi_grupos_grafico(dist_grupo, prod_psi, mod_psi,
                                           col_grupo, base_movil)
    st.plotly_chart(fig2, use_container_width=True, key="p4_psi2")
else:
    st.info("Sin modelos en la ventana.")

# --- Nivel 3 ---------------------------------------------------------------
with st.expander("Nivel 3 · Diagnóstico: PSI sobre la PD", expanded=False):
    st.markdown(
        '<p class="sub"><b>¿Se movió la PD sin cruzar cortes?</b> Sirve cuando '
        'el nivel 1 está tranquilo pero se sospecha deriva: la PD puede '
        'moverse dentro de un grupo sin cambiar el reparto entre grupos.</p>',
        unsafe_allow_html=True)
    fig3, n_mostradas, n_totales, descartados = charts.psi_pd_grafico(
        pdm_serie, serie, base_movil)
    st.plotly_chart(fig3, use_container_width=True, key="p4_psi3")
    partes = []
    if n_totales:
        partes.append(f"Mostrando los <b>{n_mostradas} de {n_totales}</b> "
                      f"modelos con mayor PSI.")
    if descartados:
        partes.append(
            f"Se descartaron <b>{descartados}</b> comparaciones de bin con menos "
            f"del 0,1% de población en alguno de los dos meses, y el resto se "
            f"renormalizó. Sin eso, un puñado de clientes moviéndose entre bins "
            f"de cola irrelevantes producía PSI de 1,5 sostenidos.")
    if partes:
        st.markdown(f'<p class="nota">{" ".join(partes)}</p>',
                    unsafe_allow_html=True)
    st.markdown(
        '<p class="nota">Los bins de probabilidad son logarítmicos, 20 por '
        'década, con bordes fijos. Con bins lineales de 0,05 toda la población '
        'caía en el primero y el PSI daba cero siempre, que se lee como '
        'estabilidad y en realidad es ceguera del instrumento.</p>',
        unsafe_allow_html=True)

st.markdown("---")
st.download_button("Descargar cortes del mes en CSV", data=data.csv(cortes_mes),
                   file_name=f"cortes_por_producto_{mes}.csv", mime="text/csv",
                   key="p4_dl")
