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

# --- verificación del método, ANTES de cualquier cosa -----------------------
# No es una línea informativa: si el helper no expone el método, reconstruir
# deja las tablas borradas o a medias. Va arriba, en rojo, y bloquea los
# botones.
ddl_ok, ddl_msg = data.verificar_metodo_ddl()
if ddl_ok:
    st.markdown(
        f'<p class="nota">Sentencias sin retorno (drop, create, compute stats) '
        f'vía <code>{ddl_msg}</code>. Se ejecutan de a una para saber en cuál '
        f'falla un script.</p>', unsafe_allow_html=True)
else:
    st.error(f"**No se puede reconstruir.**\n\n{ddl_msg}", icon="⛔")

# --- instancias del helper en este proceso ---------------------------------
# Tiene que ser UNA. Si hay más, el motivo de cada una dice si fueron
# reconexiones reales o algo que vació el caché.
reg = data.registro_helper()
if not reg.empty:
    n_rec = int(reg["motivo"].str.startswith("reconexión").sum())
    n_fallo = int(reg["resultado"].str.startswith("falló").sum())
    partes = [f"**{len(reg)}** {'instancia' if len(reg) == 1 else 'instancias'} "
              f"del helper en este proceso"]
    if n_rec:
        partes.append(f"{n_rec} por reconexión")
    if n_fallo:
        partes.append(f"{n_fallo} fallidas")
    linea = " · ".join(partes)
    if len(reg) == 1 and not n_fallo:
        st.markdown(f'<p class="nota">{linea}, creada el {reg["hora"].iloc[0]} '
                    f'({reg["motivo"].iloc[0]}).</p>', unsafe_allow_html=True)
    else:
        (st.warning if n_fallo or len(reg) > 3 else st.info)(
            linea + ". En un proceso sano es una sola; cada fila de abajo "
            "dice por qué se creó.")
        st.dataframe(reg, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Estado actual
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("## Estado de las tablas")
st.markdown(
    '<p class="sub">El último mes de la <b>tabla fuente</b> al lado del último '
    'mes <b>construido</b>. Si la fuente va más adelante, llegó una partición '
    'nueva y hay que reconstruir; hasta entonces el tablero no la ve.</p>',
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
            "_ult": e["ult_mes"],
            "último mes": (theme.etiqueta_mes_idx(e["ult_mes"])
                           if e["ult_mes"] else "--"),
            "detalle": (e["error"] or "")[:90],
        })
        barra.progress(i / len(data.TABLAS_CONSTRUIDAS), text=f"{t}…")
    barra.progress(1.0, text="Tabla fuente…")
    ults = [f["_ult"] for f in filas if f["_ult"]]
    # Hasta dónde está construido TODO: el menor de los últimos meses. Si una
    # tabla se quedó atrás, ese es el mes que manda.
    construido = min(ults) if ults else None
    try:
        fuente = data.ultimo_mes_fuente(
            construido if construido else data.mes_calendario() - 3)
        err_fuente = None
    except Exception as e:
        fuente, err_fuente = None, f"{type(e).__name__}: {e}"
    barra.empty()
    st.session_state["p9_estado_df"] = pd.DataFrame(filas)
    st.session_state["p9_fuente"] = (fuente, construido, err_fuente)

if "p9_estado_df" in st.session_state:
    df = st.session_state["p9_estado_df"]
    fuente, construido, err_fuente = st.session_state.get(
        "p9_fuente", (None, None, None))
    etq = lambda m: theme.etiqueta_mes_idx(m) if m else "--"

    k1, k2 = st.columns(2)
    k1.metric("Último mes en la tabla fuente", etq(fuente),
              help="Con ingestion_day >= 15, como todo el repo: una carga "
                   "parcial de principios de mes no cuenta.")
    k2.metric("Último mes construido", etq(construido),
              help="El menor de los últimos meses de las tablas: hasta ahí "
                   "está construido TODO.")
    if err_fuente:
        st.warning(f"No se pudo consultar la tabla fuente: {err_fuente}")
    elif fuente and construido and fuente > construido:
        st.error(
            f"**Hay que reconstruir.** La fuente llega a **{etq(fuente)}** y "
            f"lo construido a **{etq(construido)}**: "
            f"{fuente - construido} {'mes' if fuente - construido == 1 else 'meses'} "
            f"sin incorporar. El tablero no los muestra hasta reconstruir.",
            icon="⛔")
    elif fuente and construido and fuente < construido:
        st.error(
            f"**Lo construido va más adelante que la fuente** ({etq(construido)} "
            f"contra {etq(fuente)}). No debería pasar: puede que se haya borrado "
            f"una partición o que la de {etq(construido)} ya no pase el filtro "
            f"de ingestion_day.")
    elif construido and fuente is None:
        st.warning(
            f"La fuente no tiene ninguna partición desde {etq(construido)} con "
            f"ingestion_day >= 15. Revisar la ingesta.")
    elif fuente and construido:
        st.success(f"Al día: la fuente y lo construido llegan a {etq(fuente)}.")

    faltan = (df["existe"] == "NO").sum()
    if faltan:
        st.warning(f"{faltan} de {len(df)} tablas no existen para «{activo}». "
                   f"Si es una versión nueva, es lo esperado: hay que "
                   f"construirla entera.")
    else:
        meses = sorted({m for m in df["_ult"] if m})
        if len(meses) > 1:
            st.warning(f"Las tablas no llegan todas al mismo mes: "
                       f"{', '.join(etq(m) for m in meses)}. Puede ser una "
                       f"construcción a medias.")
    st.markdown(
        '<p class="nota">En las tablas de migración y en el puente, el último '
        'mes es el último con alguna fila que no sea salida. Su join deja al '
        'final meses que todavía no existen, hechos solo de los clientes del '
        'último mes real "saliendo" hacia el futuro: uno en las r1 y en el '
        'puente, seis en las r6.</p>', unsafe_allow_html=True)
    st.dataframe(df.drop(columns=["_ult"]), use_container_width=True,
                 hide_index=True)

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
if not ddl_ok:
    st.info(
        "Los botones de reconstruir están deshabilitados hasta que el helper "
        "exponga el método de arriba. Consultar el estado sí funciona: eso son "
        "consultas normales, que no pasan por ese método.")


def ejecutar(rutas: list) -> None:
    """Corre los scripts en orden. Si uno falla, SE DETIENE: los que siguen
    pueden depender de él (04, 06, 07 y 08 leen de la tabla que crea 01)."""
    if not ddl_ok:
        st.error(f"No se puede reconstruir: {ddl_msg}", icon="⛔")
        return
    barra = st.progress(0.0, text="Arrancando…")
    log = st.container()
    t0 = time.time()
    for i, ruta in enumerate(rutas, 1):
        barra.progress((i - 1) / len(rutas), text=f"{ruta.name}…")
        ini = time.time()
        try:
            r = data.construir(ruta)
        except data.VerificacionFallida as e:
            barra.empty()
            log.error(
                f"**`{ruta.name}` se abortó a propósito** después de "
                f"{time.time() - ini:.1f} s: el dato no cuadra con lo "
                f"declarado y la tabla habría salido equivocada. Se borró.\n\n"
                f"Se detuvo acá: los scripts que siguen pueden depender de "
                f"este.", icon="⛔")
            log.code(str(e), language="text")
            return
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
            f'<p class="nota">✓ <b>{ruta.name}</b> — {r.sentencias} sentencias, '
            f'{time.time() - ini:.1f} s</p>', unsafe_allow_html=True)
        if r.avisos:
            log.warning(
                f"**{ruta.name} construyó, con avisos.** No invalidan la "
                f"tabla, pero hay que actualizar config/modelos.csv:\n\n"
                + "\n".join(f"- {a}" for a in r.avisos))
        if r.informativos:
            log.markdown(
                '<p class="nota">' + "<br>".join(r.informativos) + "</p>",
                unsafe_allow_html=True)
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
        if st.button("Reconstruir todo", type="primary", key="p9_todo",
                     disabled=not ddl_ok):
            st.session_state["p9_confirmar"] = True
            st.rerun()
    else:
        st.markdown(
            f'<p class="nota">Se van a reconstruir las {len(scripts)} tablas '
            f'de <b>{activo}</b>, borrando las actuales.</p>',
            unsafe_allow_html=True)
        cc1, cc2 = st.columns(2)
        if cc1.button("Sí, reconstruir", type="primary", key="p9_si",
                      disabled=not ddl_ok):
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
        if st.button(etiqueta, key=f"p9_{ruta.name}", disabled=not ddl_ok):
            ejecutar([ruta])
