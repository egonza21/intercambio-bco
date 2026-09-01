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

DIR_SQL = Path(__file__).resolve().parent.parent / "sql" / "10_agregados"

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

# Formato en que el helper espera los parámetros dentro del SQL.
# Los .sql traen {DESDE}, {HASTA}, {REZAGO} y acá se traducen a este molde.
# Si el helper usa otro estilo, se cambia esta única constante:
#     pyformat (impyla / DB-API)   ->  "%({nombre})s"
#     named    (SQLAlchemy)        ->  ":{nombre}"
#     qmark posicional             ->  requiere reordenar, ver _a_parametros()
FORMATO_PARAMETRO = "%({nombre})s"


def _ejecutar(consulta: str, parametros: dict[str, str]) -> pd.DataFrame:
    """Ejecuta la consulta contra Impala. Único lugar que llama al helper."""
    from helper import Helper

    hp = Helper(dsn=DSN, username=USUARIO)
    return hp.obtener_dataframe(consulta, parametros)


# ===========================================================================
# ||   Fin del bloque acoplado al helper. Lo de abajo es SQL puro y pandas ||
# ===========================================================================


def _a_parametros(sql: str) -> str:
    """Convierte {DESDE} / {HASTA} / {REZAGO} al formato del helper."""
    def sub(m: re.Match) -> str:
        return FORMATO_PARAMETRO.format(nombre=m.group(1).lower())
    return re.sub(r"\{(DESDE|HASTA|REZAGO|MES)\}", sub, sql)


def _leer_sql(nombre: str) -> str:
    ruta = DIR_SQL / nombre
    if not ruta.exists():
        raise FileNotFoundError(f"No está el agregado {ruta}")
    return _a_parametros(ruta.read_text(encoding="utf-8"))


def _valores(desde: int, hasta: int, rezago: int | None = None) -> dict[str, str]:
    """Los valores viajan como texto, pero se fuerzan a int ANTES de
    formatearlos: así un selector de fecha no puede meter texto arbitrario en
    la consulta."""
    vals = {"desde": f"{int(desde)}", "hasta": f"{int(hasta)}"}
    if rezago is not None:
        vals["rezago"] = f"{int(rezago)}"
    return vals


# --- carga de cada agregado ------------------------------------------------
# Sin caché, cada interacción con un filtro golpearía Impala. Los agregados son
# de decenas de miles de filas y caben en memoria de sobra.

@st.cache_data(ttl=TTL, show_spinner="Consultando Impala...")
def base_clientes(desde: int, hasta: int) -> pd.DataFrame:
    df = _ejecutar(_leer_sql("base_clientes.sql"), _valores(desde, hasta))
    return _con_mes(df)


@st.cache_data(ttl=TTL, show_spinner="Consultando Impala...")
def cobertura_producto(desde: int, hasta: int) -> pd.DataFrame:
    """Llega ANCHA (16 columnas cob_*) y se despivota acá, que es el
    equivalente de la 'Anular dinamización' de Power Query. El SQL sale ancho a
    propósito: así evita el cross join contra los 16 productos."""
    df = _ejecutar(_leer_sql("cobertura_producto.sql"), _valores(desde, hasta))
    df = _con_mes(df)
    cols = [c for c in df.columns if c.startswith("cob_")]
    largo = df.melt(
        id_vars=[c for c in df.columns if not c.startswith("cob_")],
        value_vars=cols, var_name="producto", value_name="cubiertos",
    )
    largo["producto"] = largo["producto"].str.removeprefix("cob_")
    largo["cobertura"] = largo["cubiertos"] / largo["clientes"].where(largo["clientes"] > 0)
    return largo


@st.cache_data(ttl=TTL, show_spinner="Consultando Impala...")
def distribucion_grupo(desde: int, hasta: int) -> pd.DataFrame:
    df = _ejecutar(_leer_sql("distribucion_grupo.sql"), _valores(desde, hasta))
    return _con_grupo(_con_mes(df))


@st.cache_data(ttl=TTL, show_spinner="Consultando Impala...")
def migracion(desde: int, hasta: int, rezago: int) -> pd.DataFrame:
    return _con_mes(_ejecutar(_leer_sql("migracion.sql"), _valores(desde, hasta, rezago)))


@st.cache_data(ttl=TTL, show_spinner="Consultando Impala...")
def migracion_pd(desde: int, hasta: int, rezago: int) -> pd.DataFrame:
    return _con_mes(_ejecutar(_leer_sql("migracion_pd.sql"), _valores(desde, hasta, rezago)))


@st.cache_data(ttl=TTL, show_spinner="Consultando Impala...")
def pd_por_modelo(desde: int, hasta: int) -> pd.DataFrame:
    return _con_mes(_ejecutar(_leer_sql("pd_por_modelo.sql"), _valores(desde, hasta)))


@st.cache_data(ttl=TTL, show_spinner="Consultando Impala...")
def cortes_por_producto(desde: int, hasta: int) -> pd.DataFrame:
    return _con_grupo(_con_mes(_ejecutar(_leer_sql("cortes_por_producto.sql"),
                                         _valores(desde, hasta))))


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
    df["grupo_orden"] = df["grupo"].map(theme.GRUPO_ORDEN)
    df["grupo_base"] = df["grupo"].map(theme.GRUPO_BASE)
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


def meses_disponibles(df: pd.DataFrame) -> list[int]:
    if df.empty or "idx_mes" not in df.columns:
        return []
    return sorted(df["idx_mes"].unique().tolist())


def csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")
