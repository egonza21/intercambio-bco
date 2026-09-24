"""Carga de datos y caché.

El SQL NO se escribe acá: se lee de los .sql del repo, que son la fuente de
verdad y llevan documentado el porqué de cada decisión.

Dos orígenes distintos:

  sql/30_lectura/     SELECT sin filtros sobre las tablas ya construidas. Es
                      de donde sale todo lo que muestra el tablero.
  sql/00_perfilado/   consultas diagnósticas, que sí van directo contra la
                      tabla fuente y sí llevan parámetros.

Las tablas las construye sql/20_construccion/, que esta misma capa ejecuta
desde la página de administración.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import theme

_SQL = Path(__file__).resolve().parent.parent / "sql"
DIR_LECTURA = _SQL / "30_lectura"
DIR_PERFILADO = _SQL / "00_perfilado"
DIR_CONSTRUCCION = _SQL / "20_construccion"

# Esquema donde vive la capa construida. Un solo lugar.
ESQUEMA = "proceso"

TTL = 3600  # una hora


# ===========================================================================
# ||                                                                       ||
# ||   >>> UNICO PUNTO DE CONTACTO CON EL HELPER DEL BANCO <<<             ||
# ||                                                                       ||
# ||   Si la firma del helper difiere de lo que hay acá, se ajusta EN      ||
# ||   ESTE BLOQUE y en ningún otro lado. Ninguna otra función del repo    ||
# ||   importa `helper` ni sabe cómo se conecta a Impala.                  ||
# ||                                                                       ||
# ||   Hay UNA instancia por proceso y no se cierra nunca: ver _helper().  ||
# ||   Todo lo que ejecute algo pasa por _con_reintento().                 ||
# ||                                                                       ||
# ===========================================================================

DSN = "impala-virtual-prd"
USUARIO = "efgon"

# Identificador de versión que se agrega al nombre de cada tabla construida:
#     proceso.distribucion_grupo_vfinal
#
# Construcción y lectura TIENEN que usar el mismo valor. Si difieren, la app
# lee tablas que no existen. Por eso vive acá y no en dos lados.
#
# Cambiarlo permite construir una versión de prueba sin tocar la que está en
# uso, y de paso resuelve la concurrencia: dos personas con identificadores
# distintos escriben en tablas distintas y no se pisan.
#
# La página de administración lo puede sobreescribir por sesión; el valor
# efectivo sale siempre de idunico(), nunca de esta constante directamente.
IDUNICO_POR_DEFECTO = "vfinal"

# Formato en que el helper espera los parámetros dentro del SQL.
# Los .sql traen {DESDE}, {HASTA}, {REZAGO} y acá se traducen a este molde.
# Si el helper usa otro estilo, se cambia esta única constante:
#     pyformat (impyla / DB-API)   ->  "%({nombre})s"
#     named    (SQLAlchemy)        ->  ":{nombre}"
#     qmark posicional             ->  requiere reordenar, ver _a_parametros()
FORMATO_PARAMETRO = "{{{nombre}}}"


# Registro de instanciaciones del helper. Vive a nivel de módulo, NO en
# cache_resource: el «Clear cache» del menú de Streamlit vacía también los
# recursos, y un registro que se borra justo cuando se recrea la instancia no
# registra nada. Así sobrevive a todo menos a reiniciar el proceso, que es
# exactamente la vida de una instancia.
_REGISTRO_HELPER: list[dict] = []
_CANDADO_HELPER = threading.Lock()
# Motivo de la PRÓXIMA instanciación. Lo fija _con_reintento() antes de limpiar
# el caché; _helper() lo consume. Sin eso, cada instancia nueva se vería igual
# en el registro y no se sabría si fue arranque, reconexión o limpieza manual.
_motivo_pendiente: str | None = None


def _tomar_motivo() -> str:
    global _motivo_pendiente
    with _CANDADO_HELPER:
        motivo, _motivo_pendiente = _motivo_pendiente, None
    if motivo:
        return motivo
    if not _REGISTRO_HELPER:
        return "primera instanciación del proceso"
    return ("caché vaciado desde fuera del código (menú «Clear cache» de "
            "Streamlit)")


def _registrar_instancia(motivo: str, resultado: str) -> None:
    with _CANDADO_HELPER:
        _REGISTRO_HELPER.append({
            "hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "motivo": motivo,
            "resultado": resultado,
        })


def registro_helper() -> pd.DataFrame:
    """Cada instanciación del helper en este proceso, con hora y motivo.

    La muestra la página de Construcción: cuántas instancias hubo y por qué se
    ve acá, en vez de suponerse. En un proceso sano es UNA fila.
    """
    with _CANDADO_HELPER:
        filas = list(_REGISTRO_HELPER)
    return pd.DataFrame(filas, columns=["hora", "motivo", "resultado"])


@st.cache_resource(show_spinner=False)
def _helper():
    """UNA instancia por proceso de Streamlit, compartida por todas las páginas.

    Antes se instanciaba en cada llamada, y `_ejecutar_ddl` se llama una vez
    por sentencia: reconstruir todo son ~170 conexiones nuevas para nada.

    `cache_resource` y no `cache_data` porque esto no es un valor serializable
    sino un recurso vivo, y porque se quiere compartido entre sesiones.

    NO se cierra. El patrón del banco es instanciar y reusar; un `close` acá
    dejaría inservible la instancia que siguen usando las demás páginas.

    Cada instanciación queda en el registro (registro_helper()), incluidas las
    que fallan: un helper que no se puede crear también es un dato.
    """
    from helper import Helper

    motivo = _tomar_motivo()
    try:
        hp = Helper(dsn=DSN, username=USUARIO)
    except Exception as e:
        _registrar_instancia(motivo, f"falló: {type(e).__name__}: {e}")
        raise
    _registrar_instancia(motivo, "ok")
    return hp


# Mensajes ESPECÍFICOS de conexión caída. Antes la lista tenía palabras
# genéricas -- "connection", "closed", "timeout", "socket", "eof" -- que
# aparecen también en errores que no son de conexión ("cursor is closed", un
# timeout de consulta, un EOF de parseo). Cada falso positivo vaciaba el caché
# y creaba una instancia nueva sin necesidad.
#
# Criterio: frases que solo produce la capa de transporte (socket, thrift, SSL)
# o una sesión de Impala vencida por inactividad, que es justamente el caso de
# un proceso de Streamlit que vive horas.
_SENALES_CONEXION = (
    # socket / sistema operativo
    "broken pipe",                      # EPIPE
    "connection reset by peer",         # ECONNRESET
    "connection refused",               # ECONNREFUSED
    "connection aborted",               # ECONNABORTED
    "connection timed out",             # ETIMEDOUT, el del socket
    "[errno 32]", "[errno 104]", "[errno 110]", "[errno 111]",
    # thrift, que es sobre lo que viaja HiveServer2
    "ttransportexception",
    "tsocket read 0 bytes",
    "could not connect to",
    # SSL
    "eof occurred in violation of protocol",
    # sesión de Impala vencida por inactividad
    "session expired", "invalid session id", "session is closed",
)
# Excepciones de Python que son de conexión por su TIPO, sin mirar el texto.
# TimeoutError queda afuera a propósito: un helper puede usarla para una
# consulta que tardó demasiado, y eso no se arregla reconectando.
_TIPOS_CONEXION = (ConnectionError,)
# Y estas ganan siempre: son errores de la CONSULTA. Reintentar un SQL que
# falló no lo arregla -- lo vuelve a correr, que en un DDL puede ser caro --
# y además esconde el error real detrás de un segundo intento idéntico.
_SENALES_SQL = (
    "already exists", "analysisexception", "authorizationexception",
    "does not exist", "memory limit exceeded", "parseexception",
    "semantic error", "syntax error",
)


def _es_error_de_conexion(e: BaseException) -> bool:
    """Distingue "se cayó el socket" de "la consulta está mal".

    Se mira toda la cadena de causas, porque el helper puede envolver el error
    de transporte en uno propio. Ante la duda NO es de conexión: un falso
    positivo reejecuta un DDL, y eso sí hace daño.
    """
    actual: BaseException | None = e
    while actual is not None:
        texto = f"{type(actual).__name__} {actual}".lower()
        if any(m in texto for m in _SENALES_SQL):
            return False
        if isinstance(actual, _TIPOS_CONEXION):
            return True
        if any(m in texto for m in _SENALES_CONEXION):
            return True
        actual = actual.__cause__ or actual.__context__
    return False


def _con_reintento(operacion):
    """Corre `operacion(helper)` y, si se cayó la conexión, reinstancia y
    reintenta UNA sola vez.

    El reintento es exactamente uno: si la segunda también falla, el problema
    no es una conexión dormida y el error tiene que verse.
    """
    global _motivo_pendiente
    try:
        return operacion(_helper())
    except Exception as e:
        if not _es_error_de_conexion(e):
            raise
        with _CANDADO_HELPER:
            _motivo_pendiente = (f"reconexión tras {type(e).__name__}: "
                                 f"{str(e)[:200]}")
        _helper.clear()
        return operacion(_helper())


def _ejecutar(consulta: str, parametros: dict[str, str]) -> pd.DataFrame:
    """Ejecuta una consulta que DEVUELVE filas."""
    return _con_reintento(lambda hp: hp.obtener_dataframe(consulta, parametros))


# Método del helper para sentencias SIN retorno (drop, create table as,
# compute stats). `obtener_dataframe` espera devolver filas y un DDL no devuelve
# nada, así que no sirve.
#
# UN nombre, no una lista de candidatos por introspección. Lo que había antes
# probaba cuatro nombres y, si ninguno existía, se caía a `obtener_dataframe`:
# ese respaldo silencioso es exactamente lo que esconde un nombre mal escrito
# hasta que alguien mira los datos.
#
# El nombre es SINGULAR. Se escribió primero en plural y estaba mal; queda
# anotado porque es el tercer nombre mal escrito de este repo -- antes fueron
# `%advanced%` por `ADVANCE` y este mismo. No se puede inspeccionar la clase
# desde fuera del banco (el paquete no está instalado), así que la defensa es
# que el fallo se vea: si el helper no expone este método, la página de
# Construcción lo dice arriba y en rojo antes de dejar reconstruir nada, y
# lista los métodos que sí encontró. Ver verificar_metodo_ddl().
#
# Se corrige acá y en ningún otro lado.
METODO_DDL = "ejecutar_consulta"


def _ejecutar_ddl(sentencia: str) -> None:
    """Ejecuta UNA sentencia sin retorno.

    Una por llamada aunque el método aceptara varias: si un script de 31
    sentencias falla, hay que poder decir en cuál. Mandarlas juntas devuelve un
    error del lote y obliga a leer el .sql contando puntos y comas.
    """
    def _correr(hp):
        metodo = getattr(hp, METODO_DDL, None)
        if not callable(metodo):
            raise AttributeError(_falta_metodo(hp))
        metodo(sentencia)

    _con_reintento(_correr)


def _falta_metodo(hp) -> str:
    """El mensaje de un helper que no expone lo que esperamos. Se escribe una
    vez y lo usan el fallo real y la verificación de la página."""
    expuestos = sorted(n for n in dir(hp)
                       if not n.startswith("_") and callable(getattr(hp, n, None)))
    return (f"El helper no expone {type(hp).__name__}.{METODO_DDL}(), que es el "
            f"método con el que este repo ejecuta las sentencias sin retorno "
            f"(drop, create table as, compute stats). Métodos disponibles: "
            f"{', '.join(expuestos) or 'ninguno'}. Corregir data.METODO_DDL.")


def verificar_metodo_ddl() -> tuple[bool, str]:
    """¿Se puede reconstruir? Devuelve (ok, mensaje).

    Es una VERIFICACIÓN, no un dato informativo: si devuelve False la página de
    Construcción no deja tocar los botones. Reconstruir con el método
    equivocado deja las tablas borradas o a medias.
    """
    try:
        hp = _helper()
    except Exception as e:
        return False, (f"No se pudo instanciar el helper, así que no se puede "
                       f"reconstruir: {type(e).__name__}: {e}")
    if callable(getattr(hp, METODO_DDL, None)):
        return True, f"{type(hp).__name__}.{METODO_DDL}()"
    return False, _falta_metodo(hp)


# ===========================================================================
# ||   Fin del bloque acoplado al helper. Lo de abajo es SQL puro y pandas ||
# ===========================================================================


# --- identificador de versión ----------------------------------------------

_IDUNICO_VALIDO = re.compile(r"^[A-Za-z0-9_]+$")


def validar_idunico(valor: str) -> str:
    """El identificador va DIRECTO al nombre de una tabla en un DDL, así que no
    puede pasar por un parámetro ligado: no existe forma de parametrizar un
    nombre de objeto. La única defensa es validarlo antes de interpolarlo.

    Solo letras, números y guion bajo. Un espacio, una comilla o un punto y
    coma romperían la sentencia, o algo peor."""
    valor = (valor or "").strip()
    if not valor:
        raise ValueError("El identificador no puede estar vacío.")
    if len(valor) > 40:
        raise ValueError("El identificador no puede pasar de 40 caracteres.")
    if not _IDUNICO_VALIDO.match(valor):
        raise ValueError(
            f"Identificador inválido: {valor!r}. Solo se permiten letras, "
            f"números y guion bajo, sin espacios ni signos.")
    return valor


def idunico() -> str:
    """El identificador efectivo. La página de administración lo puede
    sobreescribir por sesión; si no lo hizo, vale el de la constante."""
    valor = st.session_state.get("idunico", IDUNICO_POR_DEFECTO)
    return validar_idunico(valor)


def _resolver_idunico(sql: str, idu: str | None = None) -> str:
    """Sustituye {IDUNICO} en los nombres de tabla. No es un parámetro ligado,
    es interpolación de texto: por eso el valor pasa antes por validar."""
    return sql.replace("{IDUNICO}", validar_idunico(idu or idunico()))


def _a_parametros(sql: str) -> str:
    """Convierte {DESDE} / {HASTA} / {REZAGO} al formato del helper."""
    def sub(m: re.Match) -> str:
        return FORMATO_PARAMETRO.format(nombre=m.group(1).lower())
    return re.sub(r"\{(DESDE|HASTA|REZAGO|MES)\}", sub, sql)


def _leer_lectura(nombre: str) -> str:
    """Lee una consulta de sql/30_lectura/. NO sustituye parámetros: esas
    consultas no tienen. Traen la tabla entera y la app filtra en pandas."""
    ruta = DIR_LECTURA / f"{nombre}.sql"
    if not ruta.exists():
        raise FileNotFoundError(
            f"No está la consulta de lectura {ruta}. ¿Se corrió "
            f"sql/20_construccion/? Ver 00_orden.md.")
    return _resolver_idunico(ruta.read_text(encoding="utf-8"))


# `idu` entra como argumento y no se lee adentro a propósito: es parte de la
# CLAVE del caché. Sin eso, cambiar de identificador devolvería las filas
# cacheadas de la versión anterior.
@st.cache_data(ttl=TTL, show_spinner="Leyendo la tabla construida...")
def _tabla_cacheada(nombre: str, idu: str) -> pd.DataFrame:
    """Trae una tabla de la capa construida, entera y sin filtros.

    Una sola llamada a Impala por tabla y por hora. Todo el filtrado de la app
    (ventana de meses, producto, segmento) pasa después en pandas, así que
    mover un selector del sidebar no vuelve a consultar."""
    ruta = DIR_LECTURA / f"{nombre}.sql"
    sql = _resolver_idunico(ruta.read_text(encoding="utf-8"), idu)
    return _con_segmento(_con_mes(_ejecutar(sql, {})))


def _tabla(nombre: str) -> pd.DataFrame:
    return _tabla_cacheada(nombre, idunico())


def _leer_perfilado(nombre: str, sentencia: int = 0) -> str:
    """Lee una consulta de sql/00_perfilado/.

    `dominio_grupos_y_escala_pd.sql` tiene DOS sentencias en el mismo archivo
    (comparten el unpivot pero agregan a distinto grano), y el helper ejecuta
    una por vez. `sentencia` elige cuál. El corte es por `;` sobre el código
    sin comentarios: ninguna de estas consultas tiene `;` dentro de un literal.
    """
    ruta = DIR_PERFILADO / nombre
    if not ruta.exists():
        raise FileNotFoundError(f"No está la consulta de perfilado {ruta}")
    codigo = "\n".join(l for l in ruta.read_text(encoding="utf-8").splitlines()
                       if not l.strip().startswith("--"))
    partes = [p.strip() for p in codigo.split(";") if p.strip()]
    return _a_parametros(partes[sentencia])


def _valores(desde: int, hasta: int, rezago: int | None = None) -> dict[str, str]:
    """Los valores viajan como texto, pero se fuerzan a int ANTES de
    formatearlos: así un selector de fecha no puede meter texto arbitrario en
    la consulta."""
    vals = {"desde": f"{int(desde)}", "hasta": f"{int(hasta)}"}
    if rezago is not None:
        vals["rezago"] = f"{int(rezago)}"
    return vals


# --- capa de LECTURA -------------------------------------------------------
# Los agregados ya no se calculan al vuelo: los construye sql/20_construccion/
# una vez al mes y acá solo se leen enteros. Por eso ninguna de estas funciones
# recibe rango de fechas -- el filtro es responsabilidad de la app, en pandas.

def base_clientes() -> pd.DataFrame:
    return _tabla("base_clientes")


def cobertura_producto() -> pd.DataFrame:
    """Llega ANCHA (16 columnas cob_*) y se despivota acá, que es lo mismo que
    hacía Power Query. El SQL sale ancho a propósito: así se resuelve con 16
    count() sobre una pasada, sin cross join."""
    df = _tabla("cobertura_producto")
    if df.empty:
        return df
    cols = [c for c in df.columns if c.startswith("cob_")]
    largo = df.melt(
        id_vars=[c for c in df.columns if not c.startswith("cob_")],
        value_vars=cols, var_name="producto", value_name="cubiertos",
    )
    largo["producto"] = largo["producto"].str.removeprefix("cob_")
    largo["cobertura"] = largo["cubiertos"] / largo["clientes"].where(largo["clientes"] > 0)
    return largo


def distribucion_grupo() -> pd.DataFrame:
    return _con_grupo(_tabla("distribucion_grupo"))


def _con_rezago(df: pd.DataFrame, rezago: int) -> pd.DataFrame:
    """Deja el rezago DENTRO de los datos.

    El rezago vive en el nombre de la tabla, así que los visuales no tenían
    forma de saber contra qué mes está comparado lo que reciben y hablaban de
    "el mes anterior" a ciegas: cierto con rezago 1, falso con rezago 6.
    Viajando como columna no puede desfasarse de la tabla que se leyó.
    """
    if df.empty:
        return df
    df = df.copy()
    df["rezago"] = int(rezago)
    return df


def migracion(rezago: int) -> pd.DataFrame:
    """El rezago NO es un parámetro de la consulta: son dos tablas distintas,
    migracion_r1 y migracion_r6. Ver sql/20_construccion/00_orden.md."""
    return _con_rezago(_tabla(f"migracion_r{int(rezago)}"), rezago)


def migracion_pd(rezago: int) -> pd.DataFrame:
    return _con_rezago(_tabla(f"migracion_pd_r{int(rezago)}"), rezago)


def pd_por_modelo() -> pd.DataFrame:
    return _tabla("pd_por_modelo")


def cortes_por_producto() -> pd.DataFrame:
    return _con_grupo(_tabla("cortes_por_producto"))


def puente_base() -> pd.DataFrame:
    """Descomposición de la base: permanece, entrada, salida, por segmento."""
    return _tabla("puente_base")


# --- perfilado: las consultas que responden "¿son confiables estos datos?" --
# Estas SÍ siguen yendo directo contra la tabla fuente y con parámetros. No se
# materializan a propósito: son diagnósticas, se corren cuando hacen falta, y
# la de mapeo se ejecuta deliberadamente sobre un solo mes porque su costo se
# multiplica por la cantidad de meses del rango.

@st.cache_data(ttl=TTL, show_spinner="Verificando ingestiones...")
def duplicados_ingestion_day(desde: int, hasta: int) -> pd.DataFrame:
    return _con_mes(_ejecutar(_leer_perfilado("duplicados_ingestion_day.sql"),
                              _valores(desde, hasta)))


@st.cache_data(ttl=TTL, show_spinner="Validando el mapeo idx -> producto...")
def validacion_mapeo(desde: int, hasta: int) -> pd.DataFrame:
    """OJO: el lado ancho son 16 agregados, uno por rama del UNION ALL, así
    que el costo se multiplica por la cantidad de meses del rango. La página
    la llama siempre con desde = hasta."""
    return _ejecutar(_leer_perfilado("validacion_mapeo.sql"), _valores(desde, hasta))


@st.cache_data(ttl=TTL, show_spinner="Revisando el dominio de grupos...")
def dominio_grupos(desde: int, hasta: int) -> pd.DataFrame:
    """Sentencia 1 de dominio_grupos_y_escala_pd.sql: valores de grupo por
    producto."""
    return _ejecutar(_leer_perfilado("dominio_grupos_y_escala_pd.sql", 0),
                     _valores(desde, hasta))


@st.cache_data(ttl=TTL, show_spinner="Revisando la escala de los modelos...")
def escala_modelos(desde: int, hasta: int) -> pd.DataFrame:
    """Sentencia 2: rango de pd por mes, producto y modelo. Es el control de
    la lista manual de modelos de puntaje de pd_por_modelo.sql."""
    return _con_mes(_ejecutar(_leer_perfilado("dominio_grupos_y_escala_pd.sql", 1),
                              _valores(desde, hasta)))


@st.cache_data(ttl=TTL, show_spinner="Comparando pd contra grupo...")
def nulos_pd_vs_grupo(desde: int, hasta: int) -> pd.DataFrame:
    return _con_mes(_ejecutar(_leer_perfilado("nulos_pd_vs_grupo.sql"),
                              _valores(desde, hasta)))


# --- enriquecimiento común -------------------------------------------------

def _con_mes(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega idx_mes y la etiqueta legible ('ago 2026')."""
    if df.empty or "ingestion_year" not in df.columns:
        return df
    df = df.copy()
    df["idx_mes"] = df["ingestion_year"].astype(int) * 12 + df["ingestion_month"].astype(int)
    df["mes"] = [theme.etiqueta_mes(a, m)
                 for a, m in zip(df["ingestion_year"], df["ingestion_month"])]
    return df


def _con_segmento(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza a string TODA columna de segmento, una sola vez y acá.

    Antes cada función hacía su propio .map(theme._cod), y las que se
    olvidaban trabajaban con el valor crudo. Si la columna llega numérica
    desde Impala, 4.0 no es '4' y deja de encontrar su nombre en SEGMENTOS:
    el código cae a su propio valor como etiqueta y dos segmentos pueden
    terminar con el mismo nombre en un eje.

    Cubre `segmento` y también `segmento_anterior` / `segmento_actual` de la
    migración, que es donde el olvido era más fácil.
    """
    if df.empty:
        return df
    cols = [c for c in df.columns
            if c == "segmento" or c.startswith("segmento_")]
    if not cols:
        return df
    df = df.copy()
    for c in cols:
        df[c] = df[c].map(theme._cod)
    return df


def _con_grupo(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega grupo_base y grupo_orden desde la dimensión de theme.py. No
    vienen del SQL a propósito: son presentacionales."""
    if df.empty or "grupo" not in df.columns:
        return df
    df = df.copy()
    # strip ANTES de mapear: 'G1 ' con espacio no está en GRUPO_ORDEN, cae al
    # final del orden y no da ningún error. Es exactamente el tipo de fallo
    # silencioso que este repo trata de no tener.
    df["grupo"] = df["grupo"].astype("string").str.strip()
    df["grupo_orden"] = df["grupo"].map(theme.GRUPO_ORDEN)
    df["grupo_base"] = df["grupo"].map(theme.GRUPO_BASE)
    sin_mapear = df.loc[df["grupo_orden"].isna(), "grupo"].dropna().unique()
    if len(sin_mapear):
        # No se rompe, pero tiene que verse: son grupos fuera del dominio.
        df.attrs["grupos_sin_mapear"] = sorted(sin_mapear.tolist())
    return df


# --- utilidades ------------------------------------------------------------

FAMILIA_PRODUCTO = {
    "consumo": "consumo", "tdc": "consumo", "libranza": "consumo",
    "rotativo": "consumo", "calm": "consumo",
    "hip_vis": "vivienda", "hip_novis": "vivienda",
    "lea_hab_vis": "vivienda", "lea_hab_novis": "vivienda",
    "comercial": "comercial", "micro": "comercial", "sobregiro": "comercial",
    "sufi_veh": "sufi", "sufi_moto": "sufi", "sufi_cpe": "sufi", "sufi_con": "sufi",
}

# Modelos que devuelven puntaje 0-999. Espejo de la lista de
# sql/20_construccion/05_pd_por_modelo.sql. Ver CLAUDE.md, "Modelos y su
# escala".
MODELOS_PUNTAJE = {"ADVANCE_1_1", "ADVANCE_INCLUSION"}

# Los ocho modelos vigentes. Espejo de CLAUDE.md, "Modelos y su escala".
# Un modelo fuera de esta lista no es un error: es una novedad que hay que
# mirar, porque si viene en escala de puntaje hay que agregarlo a
# MODELOS_PUNTAJE y a 05_pd_por_modelo.sql o sus bins salen mal sin síntoma.
MODELOS_CONOCIDOS = {
    "ADVANCE_1_1", "ADVANCE_INCLUSION", "T1_COMPORT", "T1_COMPORT_NEI",
    "T1_COMPORT_SOCIAL", "T2", "T3_MARCAS", "T_2_3",
}


# --- construcción ----------------------------------------------------------

def scripts_construccion() -> list[Path]:
    """Los scripts de 20_construccion/, en orden. El prefijo numérico ES el
    orden y hay dependencias reales: 01 tiene que existir antes que 04, 06, 07
    y 08. Ver sql/20_construccion/00_orden.md."""
    return sorted(DIR_CONSTRUCCION.glob("*.sql"))


def sentencias(ruta: Path, idu: str | None = None) -> list[str]:
    """Parte un .sql en sentencias ejecutables.

    Quita los comentarios de línea ANTES de partir por punto y coma. El orden
    importa: estos archivos tienen encabezados largos, y un ';' dentro de un
    comentario partiría la sentencia por la mitad y dejaría dos fragmentos
    inválidos.
    """
    crudo = ruta.read_text(encoding="utf-8")
    codigo = "\n".join(l for l in crudo.splitlines()
                       if not l.strip().startswith("--"))
    return [_resolver_idunico(p.strip(), idu)
            for p in codigo.split(";") if p.strip()]


def construir(ruta: Path, idu: str | None = None) -> int:
    """Ejecuta un script de construcción. Devuelve cuántas sentencias corrió.

    Las sentencias van EN SECUENCIA, una llamada por cada una: no se asume que
    el helper acepte varias juntas. Si alguna falla, la excepción sube sin
    tocar: quien llama decide si sigue o se detiene."""
    ejecutadas = 0
    for s in sentencias(ruta, idu):
        _ejecutar_ddl(s)
        ejecutadas += 1
    return ejecutadas


TABLAS_CONSTRUIDAS = [
    "largo_calificaciones", "base_clientes", "cobertura_producto",
    "distribucion_grupo", "pd_por_modelo", "cortes_por_producto",
    "migracion_r1", "migracion_r6", "migracion_pd_r1", "migracion_pd_r6",
    "puente_base",
]


# Tablas cuyo full outer join desplaza el lado origen `+rezago` y deja, al
# final, meses que todavía no existen hechos SOLO de salidas: los clientes del
# último mes real "salen" hacia un mes futuro que no llegó. migracion_r1,
# migracion_pd_r1 y puente_base llegan a último+1; las r6, a último+6. El
# último mes real de estas es el último con alguna fila que no sea salida.
#
# Sin esto, "hasta qué mes llega" cada tabla daba meses del futuro y el aviso
# de "las tablas no llegan todas al mismo mes" saltaba siempre.
_TABLAS_CON_SALIDA_FUTURA = {"migracion_r1", "migracion_r6", "migracion_pd_r1",
                             "migracion_pd_r6", "puente_base"}


def _expr_ultimo_mes(nombre: str) -> str:
    if nombre in _TABLAS_CON_SALIDA_FUTURA:
        return "max(case when categoria <> 'salida' then idx_mes end)"
    return "max(idx_mes)"


def estado_tabla(nombre: str, idu: str | None = None) -> dict:
    """Existe, cuántas filas y hasta qué mes llega. Una consulta por tabla.

    Sin caché a propósito: es justamente el dato que tiene que cambiar cuando
    se termina de construir."""
    idu = validar_idunico(idu or idunico())
    tabla = f"{ESQUEMA}.{nombre}_{idu}"
    try:
        df = _ejecutar(
            f"select count(*) as filas, {_expr_ultimo_mes(nombre)} as ult_mes "
            f"from {tabla}", {})
    except Exception as e:
        return {"tabla": tabla, "existe": False, "filas": None,
                "ult_mes": None, "error": str(e)}
    filas = int(df["filas"].iloc[0]) if not df.empty else 0
    ult = df["ult_mes"].iloc[0] if not df.empty else None
    return {"tabla": tabla, "existe": True, "filas": filas,
            "ult_mes": int(ult) if pd.notna(ult) else None, "error": None}


def meses_disponibles(df: pd.DataFrame) -> list[int]:
    if df.empty or "idx_mes" not in df.columns:
        return []
    return sorted(df["idx_mes"].unique().tolist())


def csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# --- ventana de datos ------------------------------------------------------
# De qué mes a qué mes se puede mirar. Sale de las tablas construidas, no del
# código: cada mes nuevo aparece solo al reconstruir.

# Las tres que usa toda página de negocio. Las de migración y el puente quedan
# afuera a propósito: tienen meses futuros hechos solo de salidas (ver
# _TABLAS_CON_SALIDA_FUTURA) y arrancan `rezago` meses después.
_TABLAS_VENTANA = ("base_clientes", "distribucion_grupo", "cobertura_producto")


@dataclass(frozen=True)
class Ventana:
    """Rango de meses disponible, con el porqué de cada borde."""
    desde: int | None
    hasta: int | None
    tope_calendario: int
    por_tabla: dict
    recortada_por_calendario: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.desde is not None and self.hasta is not None

    def meses(self) -> list[int]:
        return list(range(self.desde, self.hasta + 1)) if self.ok else []


def mes_calendario() -> int:
    hoy = datetime.now()
    return hoy.year * 12 + hoy.month


@st.cache_data(ttl=TTL, show_spinner=False)
def _rango_tabla(nombre: str, idu: str) -> tuple[int | None, int | None]:
    tabla = f"{ESQUEMA}.{nombre}_{validar_idunico(idu)}"
    df = _ejecutar(f"select min(idx_mes) as primero, {_expr_ultimo_mes(nombre)} "
                   f"as ultimo from {tabla}", {})
    if df.empty:
        return None, None
    a, b = df["primero"].iloc[0], df["ultimo"].iloc[0]
    return (int(a) if pd.notna(a) else None, int(b) if pd.notna(b) else None)


def ventana_datos(idu: str | None = None) -> Ventana:
    """El rango donde las tres tablas base tienen datos: desde el mayor de los
    primeros meses hasta el menor de los últimos.

    El calendario entra SOLO como tope de seguridad, nunca como límite
    superior directo. Usar el mes en curso haría aparecer, a principios de
    mes, un mes vacío -- la ingesta todavía no llegó, y el filtro
    `ingestion_day >= 15` la descartaría igual -- y todas las comparaciones
    contra el mes anterior se romperían. El tope solo actúa si una tabla trae
    un mes posterior a hoy, que sería un error de construcción.
    """
    idu = idu or idunico()
    tope = mes_calendario()
    rangos, errores = {}, []
    for t in _TABLAS_VENTANA:
        try:
            rangos[t] = _rango_tabla(t, idu)
        except Exception as e:
            errores.append(f"{t}: {type(e).__name__}: {str(e)[:160]}")
    validos = {t: r for t, r in rangos.items() if r[0] is not None and r[1] is not None}
    if errores or not validos:
        return Ventana(None, None, tope, rangos,
                       error=("; ".join(errores) or
                              "las tablas base existen pero están vacías"))
    desde = max(r[0] for r in validos.values())
    hasta_dato = min(r[1] for r in validos.values())
    hasta = min(hasta_dato, tope)
    if desde > hasta:
        return Ventana(None, None, tope, rangos,
                       error=(f"las tablas base no comparten ningún mes: "
                              f"{validos}"))
    return Ventana(desde, hasta, tope, rangos,
                   recortada_por_calendario=hasta < hasta_dato)


def ultimo_mes_fuente(desde: int) -> int | None:
    """Último mes de la tabla fuente, con el filtro de ingestion_day.

    Sin caché: es el dato que dice si llegó una partición nueva, y tiene que
    mirarse en el momento. `desde` poda particiones; ver
    sql/00_perfilado/ultimo_mes_fuente.sql.
    """
    df = _ejecutar(_leer_perfilado("ultimo_mes_fuente.sql"),
                   {"desde": f"{int(desde)}"})
    if df.empty or pd.isna(df["ultimo_mes"].iloc[0]):
        return None
    return int(df["ultimo_mes"].iloc[0])
