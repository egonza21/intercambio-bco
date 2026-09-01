"""Salud del dato: ¿son confiables los números del resto del tablero?

No es una página de gráficos. Es el estado de las consultas de
sql/00_perfilado/, que son las que verifican los supuestos sobre los que se
apoya todo lo demás: una fila por cliente y mes, el unpivot bien etiquetado,
el dominio de grupos y modelos sin novedades, y la PD concordando con el grupo.

Va primera a propósito. Si algo de acá está en rojo, los números de las otras
cuatro páginas no significan lo que parecen.
"""
from __future__ import annotations

import streamlit as st

import charts
import data
import theme

desde = st.session_state["desde"]
hasta = st.session_state["hasta"]
mes = st.session_state["mes"]

st.markdown("# Salud del dato")
st.markdown(
    f'<p class="sub">Estado de los cuatro chequeos de <code>sql/00_perfilado/</code> '
    f'sobre la ventana {theme.etiqueta_mes_idx(desde)} – '
    f'{theme.etiqueta_mes_idx(hasta)}. El detalle de cada uno solo se despliega '
    f'si falla: si están todos en verde no hay nada que leer.</p>',
    unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## Chequeos")
    correr_mapeo = st.checkbox(
        "Incluir la validación del mapeo", value=False, key="p0_mapeo",
        help="Es la consulta más lenta: 16 agregados sobre la misma partición. "
             "Se corre sobre un solo mes.")

# ---------------------------------------------------------------------------
# Los cuatro chequeos
# ---------------------------------------------------------------------------
resultados: list[charts.Chequeo] = []

resultados.append(charts.chequeo_ingestion_day(
    data.duplicados_ingestion_day(desde, hasta)))

if correr_mapeo:
    # Siempre sobre UN mes: el costo se multiplica por la cantidad de meses.
    resultados.append(charts.chequeo_mapeo(data.validacion_mapeo(mes, mes)))
else:
    resultados.append(charts.Chequeo(
        "Mapeo idx → columna alineado", False,
        "No se ejecutó, así que sobre el mapeo no hay nada verificado. Es la "
        "consulta más lenta de la página: 16 agregados, uno por producto, "
        "sobre la misma partición. Activala en la barra lateral cuando haga "
        "falta — conviene correrla después de tocar el mapeo o antes de dar "
        "por buena una carga nueva. El export siempre la ejecuta.",
        ejecutado=False))

nulos = data.nulos_pd_vs_grupo(desde, hasta)
resultados.append(charts.chequeo_dominio(
    data.dominio_grupos(desde, hasta),
    data.escala_modelos(desde, hasta),
    data.MODELOS_CONOCIDOS))
resultados.append(charts.chequeo_pd_grupo(nulos))

# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------
# El estado global cuenta los TRES estados por separado. Solo es verde si los
# cuatro se ejecutaron y los cuatro pasaron.
nivel, mensaje, _ = charts.resumen_global(resultados)
{"alerta": st.error, "aviso": st.warning, "ok": st.success}[nivel](f"**{mensaje}**")

cols = st.columns(len(resultados))
for col, c in zip(cols, resultados):
    col.markdown(
        f'<div style="background:{theme.SURFACE};border:1px solid {theme.BORDER};'
        f'border-left:3px solid {c.color};border-radius:10px;padding:.8rem 1rem;'
        f'height:100%">'
        f'<div style="font-size:.7rem;letter-spacing:.05em;font-weight:600;'
        f'color:{c.color}">{c.icono} {c.estado}</div>'
        f'<div style="font-size:.9rem;font-weight:600;color:{theme.INK};'
        f'margin-top:.25rem;line-height:1.3">{c.nombre}</div></div>',
        unsafe_allow_html=True)

st.markdown("")

for c in resultados:
    st.markdown(f"### {c.nombre}")
    st.markdown(f'<p class="sub">{c.resumen}</p>', unsafe_allow_html=True)
    if c.nota:
        st.markdown(f'<p class="nota">{c.nota}</p>', unsafe_allow_html=True)
    # El detalle solo se despliega si el chequeo falla.
    if c.ejecutado and not c.ok and c.detalle is not None and not c.detalle.empty:
        with st.expander(f"Ver el detalle ({len(c.detalle)} filas)"):
            st.dataframe(c.detalle, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar en CSV", data=data.csv(c.detalle),
                file_name=f"chequeo_{c.nombre[:18].replace(' ', '_')}.csv",
                mime="text/csv", key=f"p0_dl_{c.nombre[:12]}")

# ---------------------------------------------------------------------------
# El único chequeo con tendencia
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("## Discordancia entre PD y grupo, mes a mes")
st.markdown(
    '<p class="sub">De los cuatro chequeos, este es el único donde la '
    'tendencia dice algo: los otros tres son binarios. Que existan filas con '
    'PD nula y grupo poblado no es un problema — el filtro del tablero es por '
    'grupo, no por PD. Lo que importa es que <b>no crezcan</b>: si esta línea '
    'sube, el proceso que replica la PD entre las columnas se está '
    'degradando.</p>',
    unsafe_allow_html=True)
st.plotly_chart(charts.discordancia_pd_grupo(nulos),
                use_container_width=True, key="p0_disc")

# Cuántos productos quedaron fuera del gráfico. Sin esto, ver tres líneas deja
# la duda de si el resto no tiene casos o si el filtro se los comió.
if not nulos.empty:
    _tot = nulos.groupby("producto")["pd_nulo_grupo_no_nulo"].sum()
    _con, _sin = int((_tot > 0).sum()), int((_tot == 0).sum())
    st.markdown(
        f'<p class="nota"><b>{_con} de {_con + _sin} productos</b> tienen al '
        f'menos un caso en la ventana y son los que aparecen arriba. Los '
        f'{_sin} restantes están en cero todos los meses y se dejan fuera de '
        f'la leyenda para que el gráfico no se llene de líneas planas. Si un '
        f'producto que hoy está en cero empieza a acumular casos, aparece solo '
        f'como una línea nueva.</p>',
        unsafe_allow_html=True)

st.markdown("---")
st.download_button("Descargar el perfilado de nulos en CSV", data=data.csv(nulos),
                   file_name="nulos_pd_vs_grupo.csv", mime="text/csv", key="p0_dl")
