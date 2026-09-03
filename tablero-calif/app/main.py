"""Seguimiento de calificaciones de riesgo. Punto de entrada.

    streamlit run app/main.py

Este archivo hace tres cosas y ninguna más: configura la página, inyecta el
CSS del tema y arma la navegación. Los gráficos se definen en charts.py y se
pintan en las páginas; el mismo charts.py alimenta el export a HTML.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data  # noqa: E402
import theme  # noqa: E402

st.set_page_config(
    page_title="Calificaciones de riesgo",
    page_icon="⬛",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(theme.CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Ventana de datos
# ---------------------------------------------------------------------------
# La tabla arranca en 2025-05 y llega a 2026-08 (CLAUDE.md, "Ventana de datos
# y contracción de la base"). El índice es year*12+month, no YYYYMM: tiene que
# soportar aritmética para el rezago de la migración.
VENTANA = (theme.idx_mes(2025, 5), theme.idx_mes(2026, 8))
PRIMER_MES_TABLA = VENTANA[0]


def _opciones_mes() -> list[int]:
    return list(range(VENTANA[0], VENTANA[1] + 1))


def barra_lateral() -> None:
    """Filtros globales. Los específicos de cada página se agregan en la
    página, debajo de estos."""
    with st.sidebar:
        st.markdown("### Calificaciones de riesgo")
        st.markdown(
            f'<p class="nota">Seguimiento de modelos · ventana '
            f'{theme.etiqueta_mes_idx(VENTANA[0])} a {theme.etiqueta_mes_idx(VENTANA[1])}</p>',
            unsafe_allow_html=True)

        st.markdown("## Ventana")
        meses = _opciones_mes()
        c1, c2 = st.columns(2)
        with c1:
            desde = st.selectbox(
                "Desde", meses, index=0,
                format_func=theme.etiqueta_mes_idx, key="f_desde")
        with c2:
            hasta = st.selectbox(
                "Hasta", meses, index=len(meses) - 1,
                format_func=theme.etiqueta_mes_idx, key="f_hasta")
        if desde > hasta:
            st.warning("El mes inicial es posterior al final. Se invirtieron.")
            desde, hasta = hasta, desde

        st.session_state["desde"] = int(desde)
        st.session_state["hasta"] = int(hasta)

        st.markdown("## Mes de corte")
        st.session_state["mes"] = int(st.selectbox(
            "Mes a mostrar en las vistas de un solo período",
            [m for m in meses if desde <= m <= hasta],
            index=len([m for m in meses if desde <= m <= hasta]) - 1,
            format_func=theme.etiqueta_mes_idx, key="f_mes"))

        st.markdown("---")
        # El identificador tiene que estar a la vista en todas las páginas: los
        # números salen de las tablas de ESA versión y no de otra.
        st.markdown(
            f'<p class="nota">Versión de tablas<br>'
            f'<code style="font-size:.95em">{data.idunico()}</code></p>',
            unsafe_allow_html=True)
        st.markdown(
            '<p class="nota">Los agregados se cachean una hora. Para forzar '
            'una relectura de Impala, usá <b>C</b> y luego «Clear cache».</p>',
            unsafe_allow_html=True)


barra_lateral()

paginas = [
    # Anomalías va primera: dice DÓNDE mirar. Salud del dato va segunda: dice
    # si lo que se mira es confiable. Recién después panorama dice QUÉ pasa.
    st.Page("pages/0_anomalias.py", title="Qué se movió", icon="🔎", default=True),
    st.Page("pages/0_salud_dato.py", title="Salud del dato", icon="🩺"),
    st.Page("pages/1_panorama.py", title="Panorama del mes", icon="📊"),
    st.Page("pages/2_evolucion.py", title="Evolución", icon="📈"),
    st.Page("pages/3_migracion.py", title="Migración", icon="🔀"),
    st.Page("pages/4_modelos.py", title="Modelos", icon="🧮"),
    # Administración, al final: no se entra acá para mirar números.
    st.Page("pages/9_construccion.py", title="Construcción", icon="⚙️"),
]
st.navigation(paginas).run()
