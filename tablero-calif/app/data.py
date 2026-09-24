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
from dataclasses import dataclass, field
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
    codigo = _resolver_productos(codigo, ruta.name)
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
    return despivotar_cobertura(_tabla("cobertura_producto"))


def despivotar_cobertura(df: pd.DataFrame) -> pd.DataFrame:
    """De las 16 columnas cob_* a una fila por producto. Separada del loader
    para que las pruebas pasen sus datos sintéticos por la MISMA
    transformación que la app."""
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


# --- modelos: config/modelos.csv es la única lista ------------------------
# Antes había tres copias: MODELOS_PUNTAJE y MODELOS_CONOCIDOS acá y un IN
# literal en 05_pd_por_modelo.sql. Se desincronizaban, y el chequeo 3 marcaba
# novedad todos los meses porque su copia tenía ocho de los doce modelos.
#
# Cuando entra un modelo nuevo se agrega UNA línea al CSV. Si alguien se
# olvida, la verificación de la construcción lo atrapa (ver clasificar_modelos).

RUTA_MODELOS = Path(__file__).resolve().parent.parent / "config" / "modelos.csv"

# Vocabulario del CSV -> vocabulario de las tablas. El CSV usa la palabra que
# se dice en voz alta; las tablas conservan los valores que ya tenían, para no
# tocar nada aguas abajo.
ESCALAS = {"probabilidad": "probabilidad_0_1", "puntaje": "puntaje_0_999"}

# Mismo criterio que {IDUNICO} y que los productos: el nombre se interpola en
# un literal SQL, y esta validación es la única defensa.
_MODELO_VALIDO = theme.NOMBRE_SQL


def leer_modelos(ruta: Path | None = None) -> pd.DataFrame:
    """Lee y VALIDA config/modelos.csv. Devuelve (modelo, escala, escala_tabla).

    Falla con un error que lista TODAS las líneas malas, no solo la primera:
    arreglar de a una y volver a correr es la forma lenta de hacerlo.
    """
    ruta = ruta or RUTA_MODELOS
    if not ruta.exists():
        raise FileNotFoundError(f"No está {ruta}: es la lista de modelos y su "
                                f"escala, sin ella no se puede construir.")
    df = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    if list(df.columns) != ["modelo", "escala"]:
        raise ValueError(f"{ruta.name}: las columnas tienen que ser exactamente "
                         f"'modelo,escala'; son {list(df.columns)}.")
    df = df.apply(lambda c: c.str.strip())
    errores = []
    for i, r in df.iterrows():
        linea = i + 2          # +1 por el encabezado, +1 porque arranca en 1
        if not r["modelo"]:
            errores.append(f"línea {linea}: modelo vacío")
        elif not _MODELO_VALIDO.match(r["modelo"]):
            errores.append(f"línea {linea}: {r['modelo']!r} tiene caracteres "
                           f"fuera de letras, números y guion bajo")
        if r["escala"] not in ESCALAS:
            errores.append(f"línea {linea}: escala {r['escala']!r}, tiene que "
                           f"ser {' o '.join(ESCALAS)}")
    dup = df.loc[df["modelo"].duplicated(keep=False) & (df["modelo"] != ""), "modelo"]
    if not dup.empty:
        errores.append(f"modelos repetidos: {sorted(set(dup))}")
    if df.empty:
        errores.append("el archivo no tiene ningún modelo")
    if errores:
        raise ValueError(f"{ruta.name} tiene errores:\n  - " + "\n  - ".join(errores))
    df["escala_tabla"] = df["escala"].map(ESCALAS)
    return df.reset_index(drop=True)


def _sql_modelos_declarados(modelos: pd.DataFrame) -> str:
    """El cuerpo de tmp_modelos, una fila por modelo. Los nombres ya pasaron
    por leer_modelos(), que es lo que hace seguro interpolarlos."""
    filas = [f"'{r.modelo}' as modelo, '{r.escala_tabla}' as escala"
             if i == 0 else f"'{r.modelo}', '{r.escala_tabla}'"
             for i, r in enumerate(modelos.itertuples())]
    return ("          select " + filas[0] + "\n"
            + "".join(f"union all select {f}\n" for f in filas[1:])).rstrip()


def _sql_productos_declarados() -> str:
    """El cuerpo de la tabla de productos, desde config/productos.csv. Los
    nombres ya pasaron por theme.leer_productos(), que es lo que hace seguro
    interpolarlos. Sirve tal cual como `create table ... as` y como cuerpo de
    un CTE."""
    filas = []
    for i, p in enumerate(theme.PRODUCTOS):
        if i == 0:
            filas.append(f"          select {p.idx} as idx, '{p.producto}' as producto,\n"
                         f"                 '{p.familia_producto}' as familia_producto, "
                         f"'{p.serie_pd}' as serie_pd")
        else:
            filas.append(f"union all select {p.idx}, '{p.producto}', "
                         f"'{p.familia_producto}', '{p.serie_pd}'")
    return "\n".join(filas)


_WHEN_IDX = re.compile(r"\bwhen\s+(\d+)\s+then\s+c\.[a-z]+_", re.I)


def _chequear_idx_contra_case(sql: str, origen: str) -> None:
    """Los idx del CSV tienen que ser exactamente los que mapean los CASE del
    SQL que lo usa. Es el control ESTRUCTURAL: un idx de más en el CSV no
    tendría columna y sus filas desaparecerían en el `grupo is not null`; uno
    de menos dejaría un producto sin fila. Que cada idx apunte a la columna
    CORRECTA es otra cosa, semántica, y la verifica validacion_mapeo.sql."""
    en_case = {int(n) for n in _WHEN_IDX.findall(sql)}
    en_csv = {p.idx for p in theme.PRODUCTOS}
    if en_case and en_case != en_csv:
        raise ValueError(
            f"{origen}: los idx de config/productos.csv no coinciden con los "
            f"del CASE que mapea idx -> columna. Solo en el CSV: "
            f"{sorted(en_csv - en_case) or '-'}; solo en el CASE: "
            f"{sorted(en_case - en_csv) or '-'}.")


def _resolver_productos(sql: str, origen: str) -> str:
    if "{PRODUCTOS_DECLARADOS}" not in sql:
        return sql
    _chequear_idx_contra_case(sql, origen)
    return sql.replace("{PRODUCTOS_DECLARADOS}", _sql_productos_declarados())


def clasificar_modelos(observados: pd.DataFrame,
                       declarados: pd.DataFrame) -> pd.DataFrame:
    """Compara el rango de PD de cada modelo contra lo declarado en el CSV.

    `observados` trae (modelo, pd_max) y opcionalmente pd_min; puede tener
    varias filas por modelo (el perfilado viene por mes y producto): se toma el
    máximo. Devuelve una fila por modelo con `severidad`:

      falla  no declarado con PD > 1, o declarado como probabilidad con PD > 1.
             Sus bins saldrían mal: la construcción de pd_por_modelo aborta.
      aviso  no declarado con PD entre 0 y 1 -- un modelo nuevo que hay que
             agregar al CSV; declarado como puntaje pero con PD <= 1 -- puede
             haber cambiado de escala, y sus bins de 50 los mete todos en el
             primero; o filas SIN modelo con PD > 1 -- su escala se asume
             probabilidad y ahí no lo es.
      info   declarado pero no aparece en la ventana.
      ok     declarado y consistente.

    Es la misma función para la construcción y para el chequeo 3 de Salud del
    dato: la regla está una sola vez.
    """
    decl = dict(zip(declarados["modelo"], declarados["escala"]))
    obs = observados.copy()
    obs["modelo"] = obs["modelo"].where(obs["modelo"].notna(), None)
    obs["modelo"] = obs["modelo"].map(
        lambda m: None if m is None or str(m).strip() == "" else str(m).strip())
    agg = {"pd_max": ("pd_max", "max")}
    if "pd_min" in obs.columns:
        agg["pd_min"] = ("pd_min", "min")
    g = (obs.assign(_k=obs["modelo"].fillna("\x00"))
         .groupby("_k", as_index=False).agg(**agg))
    g["modelo"] = g["_k"].where(g["_k"] != "\x00", None)
    filas = []
    for r in g.itertuples():
        m, pmax = r.modelo, float(r.pd_max) if pd.notna(r.pd_max) else None
        esc = decl.get(m)
        if m is None:
            sev, mot = (("aviso", f"filas SIN modelo con PD hasta {pmax:g}: se "
                         f"binean como probabilidad y no lo son")
                        if pmax is not None and pmax > 1 else
                        ("ok", "filas sin modelo; su escala se asume probabilidad"))
        elif esc is None:
            sev, mot = (("falla", f"no está en {RUTA_MODELOS.name} y su PD llega "
                         f"a {pmax:g}: es de puntaje")
                        if pmax is not None and pmax > 1 else
                        ("aviso", f"no está en {RUTA_MODELOS.name}; su PD llega a "
                         f"{pmax:g}, así que se trata como probabilidad. "
                         f"Agregarlo al CSV"))
        elif esc == "probabilidad" and pmax is not None and pmax > 1:
            sev, mot = ("falla", f"declarado como probabilidad pero su PD llega "
                        f"a {pmax:g}")
        elif esc == "puntaje" and pmax is not None and pmax <= 1:
            sev, mot = ("aviso", f"declarado como puntaje pero su PD no pasa de "
                        f"{pmax:g}: ¿cambió de escala?")
        else:
            sev, mot = "ok", f"declarado como {esc}, consistente"
        filas.append({"modelo": m if m is not None else "(sin modelo)",
                      "escala_declarada": esc or "--", "pd_max": pmax,
                      "severidad": sev, "motivo": mot})
    vistos = {f["modelo"] for f in filas}
    for m, esc in decl.items():
        if m not in vistos:
            filas.append({"modelo": m, "escala_declarada": esc, "pd_max": None,
                          "severidad": "info",
                          "motivo": "declarado, no aparece en los datos"})
    orden = {"falla": 0, "aviso": 1, "info": 2, "ok": 3}
    out = pd.DataFrame(filas, columns=["modelo", "escala_declarada", "pd_max",
                                       "severidad", "motivo"])
    return (out.assign(_o=out["severidad"].map(orden))
            .sort_values(["_o", "modelo"]).drop(columns="_o")
            .reset_index(drop=True))


# --- construcción ----------------------------------------------------------

def scripts_construccion() -> list[Path]:
    """Los scripts de 20_construccion/, en orden. El prefijo numérico ES el
    orden y hay dependencias reales: 01 tiene que existir antes que 04, 06, 07
    y 08. Ver sql/20_construccion/00_orden.md."""
    return sorted(DIR_CONSTRUCCION.glob("*.sql"))


_MARCA_VERIFICACION = re.compile(r"^\s*--\s*@verificacion\s+(\w+)\s*$")
_CENTINELA = "@@verificacion:"


class VerificacionFallida(RuntimeError):
    """La construcción se detuvo a propósito: el dato no cuadra con lo
    declarado y la tabla saldría equivocada."""


@dataclass
class ResultadoConstruccion:
    sentencias: int
    avisos: list[str] = field(default_factory=list)
    informativos: list[str] = field(default_factory=list)


def _resolver_marcadores(sql: str, idu: str | None) -> str:
    sql = _resolver_idunico(sql, idu)
    if "{MODELOS_DECLARADOS}" in sql:
        sql = sql.replace("{MODELOS_DECLARADOS}",
                          _sql_modelos_declarados(leer_modelos()))
    return sql


def pasos(ruta: Path, idu: str | None = None) -> list[str]:
    """Las sentencias de un script, más las verificaciones marcadas.

    Una verificación se marca con una línea `-- @verificacion <nombre>` y
    aparece en la lista como `@@verificacion:<nombre>`. Va como comentario
    para que el archivo siga siendo SQL válido.

    Quita los comentarios de línea ANTES de partir por punto y coma: estos
    archivos tienen encabezados largos, y un ';' dentro de un comentario
    partiría la sentencia por la mitad.

    Todo se resuelve ANTES de ejecutar nada: un CSV de modelos mal escrito
    falla acá, antes del primer drop, y no deja el script a medias.

    El orden importa: PRIMERO se quitan los comentarios y DESPUÉS se resuelven
    los marcadores. Al revés, un marcador mencionado en un comentario -- el
    encabezado de 01 nombra {PRODUCTOS_DECLARADOS} -- se reemplazaba por varias
    líneas de SQL de las que solo la primera quedaba comentada; las demás se
    pegaban delante de la primera sentencia del script y Impala la rechazaba.
    Rompía "Reconstruir todo" en la primera sentencia de 01.
    """
    lineas = []
    for l in ruta.read_text(encoding="utf-8").splitlines():
        m = _MARCA_VERIFICACION.match(l)
        if m:
            lineas.append(f"{_CENTINELA}{m.group(1)};")
        elif not l.strip().startswith("--"):
            lineas.append(l)
    # El chequeo de idx contra el CASE necesita el script ENTERO -- el CASE y
    # el marcador están en sentencias distintas --, pero ya sin comentarios.
    codigo = _resolver_productos("\n".join(lineas), ruta.name)
    return [p.strip() if p.strip().startswith(_CENTINELA)
            else _resolver_marcadores(p.strip(), idu)
            for p in codigo.split(";") if p.strip()]


def sentencias(ruta: Path, idu: str | None = None) -> list[str]:
    """Solo el SQL, sin las verificaciones."""
    return [p for p in pasos(ruta, idu) if not p.startswith(_CENTINELA)]


def _verificar_modelos(idu: str | None) -> tuple[list[str], list[str], list[str]]:
    """(fallas, avisos, informativos) de la escala de modelos, sobre
    tmp_pd_escalado de la construcción en curso."""
    ruta = DIR_CONSTRUCCION / "verificaciones" / "modelos.sql"
    codigo = "\n".join(l for l in ruta.read_text(encoding="utf-8").splitlines()
                       if not l.strip().startswith("--"))
    obs = _ejecutar(_resolver_idunico(codigo.strip().rstrip(";"), idu), {})
    c = clasificar_modelos(obs, leer_modelos())
    fila = lambda r: f"{r.modelo}: {r.motivo}"
    return ([fila(r) for r in c.itertuples() if r.severidad == "falla"],
            [fila(r) for r in c.itertuples() if r.severidad == "aviso"],
            [fila(r) for r in c.itertuples() if r.severidad == "info"])


_VERIFICACIONES = {"modelos": _verificar_modelos}


def construir(ruta: Path, idu: str | None = None) -> ResultadoConstruccion:
    """Ejecuta un script de construcción.

    Las sentencias van EN SECUENCIA, una llamada por cada una: no se asume que
    el helper acepte varias juntas, y así un fallo dice en cuál fue. Si alguna
    falla, la excepción sube sin tocar: quien llama decide si sigue.

    Si una VERIFICACIÓN falla, ejecuta todos los `drop` del script -- tabla
    final incluida -- y levanta VerificacionFallida. Es mejor no tener la tabla
    que tenerla equivocada: una tabla que no existe se nota en la primera
    página que la lee; una con los bins mal, no.
    """
    todos = pasos(ruta, idu)
    res = ResultadoConstruccion(0)
    for p in todos:
        if p.startswith(_CENTINELA):
            nombre = p[len(_CENTINELA):]
            fallas, avisos, info = _VERIFICACIONES[nombre](idu)
            res.avisos += avisos
            res.informativos += info
            if fallas:
                drops = [s for s in todos if s.lower().startswith("drop table")]
                for d in drops:
                    _ejecutar_ddl(d)
                raise VerificacionFallida(
                    f"{ruta.name}: la verificación de {nombre} falló y la "
                    f"construcción se abortó.\n  - " + "\n  - ".join(fallas)
                    + f"\nSe ejecutaron los {len(drops)} drop del script, tabla "
                    f"final incluida: mejor no tenerla que tenerla con los bins "
                    f"mal. Corregir {RUTA_MODELOS.relative_to(RUTA_MODELOS.parent.parent)} "
                    f"y reconstruir.")
            continue
        _ejecutar_ddl(p)
        res.sentencias += 1
    return res


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
