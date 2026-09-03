"""Carga de los agregados de sql/10_agregados/ y caché.

El SQL NO se escribe acá: se lee de los .sql existentes. Esos archivos son la
fuente de verdad y ya llevan documentado el porqué de cada decisión. Lo único
que hace este módulo es sustituir los marcadores {DESDE}/{HASTA}/{REZAGO} por
el formato de parámetros del helper y cachear el resultado.
"""
from __future__ import annotations

import re
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


def _helper():
    from helper import Helper

    return Helper(dsn=DSN, username=USUARIO)


def _ejecutar(consulta: str, parametros: dict[str, str]) -> pd.DataFrame:
    """Ejecuta una consulta que DEVUELVE filas."""
    return _helper().obtener_dataframe(consulta, parametros)


# Métodos candidatos para DDL, en orden de preferencia. `obtener_dataframe`
# espera devolver filas y un drop o un create no devuelven nada: según cómo
# esté implementado, puede fallar o devolver vacío. No se pudo verificar qué
# expone el helper -- no está instalado en el entorno donde se escribió esto --
# así que se elige el primero que exista y, si no hay ninguno, se cae a
# obtener_dataframe, que es el comportamiento anterior.
_METODOS_DDL = ("ejecutar", "ejecutar_sentencia", "execute", "ejecutar_ddl")


def _ejecutar_ddl(sentencia: str) -> None:
    """Ejecuta una sentencia SIN retorno (drop, create table as, compute stats).

    Si el helper resulta exponer otro nombre, se agrega a _METODOS_DDL y no hay
    que tocar nada más."""
    hp = _helper()
    for nombre in _METODOS_DDL:
        metodo = getattr(hp, nombre, None)
        if callable(metodo):
            metodo(sentencia)
            return
    hp.obtener_dataframe(sentencia, {})


def metodo_ddl_detectado() -> str:
    """Qué método usaría _ejecutar_ddl. Lo muestra la página de
    administración, para no tener que adivinarlo mirando el código."""
    try:
        hp = _helper()
    except Exception as e:
        return f"no se pudo instanciar el helper: {e}"
    for nombre in _METODOS_DDL:
        if callable(getattr(hp, nombre, None)):
            return f"Helper.{nombre}()"
    return "Helper.obtener_dataframe() (no se encontró un método sin retorno)"


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
    return _con_mes(_ejecutar(sql, {}))


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


def migracion(rezago: int) -> pd.DataFrame:
    """El rezago NO es un parámetro de la consulta: son dos tablas distintas,
    migracion_r1 y migracion_r6. Ver sql/20_construccion/00_orden.md."""
    return _tabla(f"migracion_r{int(rezago)}")


def migracion_pd(rezago: int) -> pd.DataFrame:
    return _tabla(f"migracion_pd_r{int(rezago)}")


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
# sql/10_agregados/pd_por_modelo.sql. Ver CLAUDE.md, "Modelos y su escala".
MODELOS_PUNTAJE = {"ADVANCE_1_1", "ADVANCE_INCLUSION"}

# Los ocho modelos vigentes. Espejo de CLAUDE.md, "Modelos y su escala".
# Un modelo fuera de esta lista no es un error: es una novedad que hay que
# mirar, porque si viene en escala de puntaje hay que agregarlo a
# MODELOS_PUNTAJE y a pd_por_modelo.sql o sus bins salen mal sin dar síntoma.
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


def estado_tabla(nombre: str, idu: str | None = None) -> dict:
    """Existe, cuántas filas y hasta qué mes llega. Una consulta por tabla.

    Sin caché a propósito: es justamente el dato que tiene que cambiar cuando
    se termina de construir."""
    idu = validar_idunico(idu or idunico())
    tabla = f"{ESQUEMA}.{nombre}_{idu}"
    try:
        df = _ejecutar(
            f"select count(*) as filas, max(idx_mes) as ult_mes from {tabla}", {})
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
