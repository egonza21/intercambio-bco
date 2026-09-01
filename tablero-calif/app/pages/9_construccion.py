"""Administración: construir las tablas de proceso.

NO corre nada al abrirse. Todo pasa por un botón explícito, porque cada script
hace `drop table` antes del `create`: mientras corre, esa tabla no existe y
cualquiera que esté mirando el tablero se queda sin datos.

El identificador de versión aísla ejecuciones: dos personas con identificadores
distintos escriben en tablas distintas y no se pisan.
"""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

import data
import theme

st.markdown("# Construcción de tablas")
st.markdown(
    '<p class="sub">Ejecuta los scripts de <code>sql/20_construccion/</code>. '
    'Se corre <b>una vez al mes</b>, cuando llega la partición nueva. No hay '
    'nada automático en esta página: nada se ejecuta hasta que se aprieta un '
    'botón.</p>',
    unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Identificador de versión
# ---------------------------------------------------------------------------
activo = data.idunico()

st.markdown("## Identificador de versión")
c1, c2 = st.columns([1, 2])
with c1:
    nuevo = st.text_input(
        "Identificador activo", value=activo, key="p9_idu",
        help="Se agrega al nombre de cada tabla: distribucion_grupo_<id>. "
             "Solo letras, números y guion bajo.")
with c2:
    st.markdown(
        f'<p class="nota" style="margin-top:1.9rem">Las tablas de esta sesión '
        f'son <code>{data.ESQUEMA}.&lt;nombre&gt;_{activo}</code>. Cambiar el '
        f'identificador permite construir una versión de prueba sin tocar la '
        f'que está en uso — y es lo que hace que dos personas construyendo a la '
        f'vez no se pisen, siempre que usen identificadores distintos.</p>',
        unsafe_allow_html=True)

if nuevo != activo:
    try:
        data.validar_idunico(nuevo)
    except ValueError as e:
        st.error(f"{e}")
    else:
        if st.button(f"Cambiar a «{nuevo}»", type="primary", key="p9_cambiar"):
            st.session_state["idunico"] = nuevo
            st.cache_data.clear()   # el caché está indexado por identificador
            st.rerun()

st.markdown(
    f'<p class="nota">Método que se usará para las sentencias sin retorno '
    f'(drop, create, compute stats): <code>{data.metodo_ddl_detectado()}</code>. '
    f'Se elige por introspección del helper, porque <code>obtener_dataframe</code> '
    f'espera devolver filas y un DDL no devuelve nada.</p>',
    unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Estado actual
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("## Estado de las tablas")
st.markdown(
    '<p class="sub">Si el mes máximo de alguna tabla se quedó atrás respecto '
    'de la partición nueva, hay que reconstruir.</p>',
    unsafe_allow_html=True)

if st.button("Consultar estado", key="p9_estado"):
    filas = []
    barra = st.progress(0.0, text="Consultando…")
    for i, t in enumerate(data.TABLAS_CONSTRUIDAS, 1):
        e = data.estado_tabla(t)
        filas.append({
            "tabla": t,
            "existe": "sí" if e["existe"] else "NO",
            "filas": theme.fmt_miles(e["filas"]) if e["existe"] else "--",
            "último mes": (theme.etiqueta_mes_idx(e["ult_mes"])
                           if e["ult_mes"] else "--"),
            "detalle": (e["error"] or "")[:90],
        })
        barra.progress(i / len(data.TABLAS_CONSTRUIDAS), text=f"{t}…")
    barra.empty()
    st.session_state["p9_estado_df"] = pd.DataFrame(filas)

if "p9_estado_df" in st.session_state:
    df = st.session_state["p9_estado_df"]
    faltan = (df["existe"] == "NO").sum()
    if faltan:
        st.warning(f"{faltan} de {len(df)} tablas no existen para «{activo}». "
                   f"Si es una versión nueva, es lo esperado: hay que "
                   f"construirla entera.")
    else:
        meses = {m for m in df["último mes"] if m != "--"}
        if len(meses) > 1:
            st.warning(f"Las tablas no llegan todas al mismo mes: {sorted(meses)}. "
                       f"Puede ser una construcción a medias.")
        else:
            st.success(f"Las {len(df)} tablas existen y llegan a "
                       f"{meses.pop() if meses else '--'}.")
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("## Reconstruir")
st.warning(
    "**Mientras un script corre, su tabla no existe.** El `drop` va antes del "
    "`create`. Si alguien tiene el tablero abierto y fuerza una relectura, le "
    "va a fallar. Avisá antes de correr esto sobre un identificador en uso.",
    icon="⚠")

scripts = data.scripts_construccion()
if not scripts:
    st.error(f"No hay scripts en {data.DIR_CONSTRUCCION}.")
    st.stop()


def ejecutar(rutas: list) -> None:
    """Corre los scripts en orden. Si uno falla, SE DETIENE: los que siguen
    pueden depender de él (04, 06, 07 y 08 leen de la tabla que crea 01)."""
    barra = st.progress(0.0, text="Arrancando…")
    log = st.container()
    t0 = time.time()
    for i, ruta in enumerate(rutas, 1):
        barra.progress((i - 1) / len(rutas), text=f"{ruta.name}…")
        ini = time.time()
        try:
            n = data.construir(ruta)
        except Exception as e:
            barra.empty()
            log.error(
                f"**Falló `{ruta.name}`** después de {time.time() - ini:.1f} s.\n\n"
                f"Se detuvo acá: los scripts que siguen pueden depender de "
                f"este. Las tablas ya construidas quedaron bien; esta quedó "
                f"borrada o a medias.")
            log.code(f"{type(e).__name__}: {e}", language="text")
            return
        log.markdown(
            f'<p class="nota">✓ <b>{ruta.name}</b> — {n} sentencias, '
            f'{time.time() - ini:.1f} s</p>', unsafe_allow_html=True)
    barra.progress(1.0, text="Listo")
    # Sin esto las otras páginas seguirían mostrando lo cacheado de antes.
    st.cache_data.clear()
    st.session_state.pop("p9_estado_df", None)
    log.success(
        f"**{len(rutas)} scripts en {time.time() - t0:.1f} s.** Caché limpiado: "
        f"el resto de la app ya lee las tablas nuevas. Conviene pasar por "
        f"**Salud del dato** y activar el chequeo de mapeo antes de mirar "
        f"números.")


c1, c2 = st.columns([1, 2])
with c1:
    st.markdown("#### Todo, en orden")
    if not st.session_state.get("p9_confirmar"):
        if st.button("Reconstruir todo", type="primary", key="p9_todo"):
            st.session_state["p9_confirmar"] = True
            st.rerun()
    else:
        st.markdown(
            f'<p class="nota">Se van a reconstruir las {len(scripts)} tablas '
            f'de <b>{activo}</b>, borrando las actuales.</p>',
            unsafe_allow_html=True)
        cc1, cc2 = st.columns(2)
        if cc1.button("Sí, reconstruir", type="primary", key="p9_si"):
            st.session_state["p9_confirmar"] = False
            ejecutar(scripts)
        if cc2.button("Cancelar", key="p9_no"):
            st.session_state["p9_confirmar"] = False
            st.rerun()

with c2:
    st.markdown("#### Uno solo")
    st.markdown(
        '<p class="nota">Ojo con el orden: <code>01_largo_calificaciones</code> '
        'tiene que existir antes que 04, 06, 07 y 08, que leen de ella. Los '
        'demás son independientes.</p>', unsafe_allow_html=True)
    for ruta in scripts:
        dep = ruta.name.startswith(("04_", "06_", "07_", "08_"))
        etiqueta = f"{ruta.name}" + ("  · depende de 01" if dep else "")
        if st.button(etiqueta, key=f"p9_{ruta.name}"):
            ejecutar([ruta])
