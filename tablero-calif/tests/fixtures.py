"""Datos SINTÉTICOS para las pruebas. Inventados, no vienen de ningún lado.

El repo no contiene datos (CLAUDE.md, "Restricciones del entorno"), y esto no
cambia eso: todos los números salen de un generador con semilla fija. Lo que sí
copian es la FORMA de cada tabla -- las columnas de sql/30_lectura/ y de
sql/00_perfilado/ -- y pasan por las mismas transformaciones que aplica
data.py al leer (_con_mes, _con_segmento, _con_grupo, _con_rezago,
despivotar_cobertura). Así lo que recibe cada gráfico es lo que recibiría en la
app.

Los fixtures están hechos para ABRIR ramas, no para verse realistas: hay
productos de las cuatro familias, aperturas de sufi, las siete categorías de
migración, un corte solapado, un modelo sin modelo, las dos escalas de PD. Una
prueba con un DataFrame vacío pasa por `_sin_datos` y no ejecuta el cuerpo de
la función; así fue como `_FAM` quedó sin definir sin que nada lo notara.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import data
import theme

SEMILLA = 20260923
MESES = [theme.idx_mes(2025, 5) + i for i in range(16)]    # 16 meses
ULTIMO = MESES[-1]
SEGMENTOS = ["S", "4", "M", "6", "11", "9"]
PRODUCTOS = list(theme.PRODUCTOS_ORDENADOS)
MODELOS = ["T2", "T1_COMPORT", "ADVANCE_1_1", "T2_HIP"]


def _rng(extra: int = 0) -> np.random.Generator:
    return np.random.default_rng(SEMILLA + extra)


def _anio_mes(m: int) -> tuple[int, int]:
    a = (m - 1) // 12
    return a, m - 12 * a


def _particion(df: pd.DataFrame) -> pd.DataFrame:
    """ingestion_year / ingestion_month a partir de idx_mes, como vienen del SQL."""
    a, mm = zip(*(_anio_mes(int(m)) for m in df["idx_mes"]))
    return df.assign(ingestion_year=list(a), ingestion_month=list(mm))


def _grupos_de(producto: str) -> list[str]:
    abre = producto in ("sufi_moto", "sufi_cpe", "sufi_con")
    base = [f"G{i}" for i in range(1, 7)]
    extra = (["G7_B", "G7_M", "G7_A", "G8_B", "G8_M", "G8_A"] if abre
             else ["G7", "G8"])
    return base + extra


# --- capa de lectura ------------------------------------------------------

def base_clientes() -> pd.DataFrame:
    r = _rng(1)
    filas = [dict(idx_mes=m, segmento=s,
                  clientes=int(2e6 * (1 - 0.005 * i) * r.uniform(.95, 1.05)))
             for i, m in enumerate(MESES) for s in SEGMENTOS]
    return data._con_segmento(data._con_mes(_particion(pd.DataFrame(filas))))


def cobertura_producto() -> pd.DataFrame:
    r = _rng(2)
    filas = []
    for m in MESES:
        for s in SEGMENTOS:
            fila = dict(idx_mes=m, segmento=s, clientes=200_000)
            for p in PRODUCTOS:
                tasa = 0.05 if p in ("comercial", "micro", "sobregiro") else 0.35
                fila[f"cob_{p}"] = int(200_000 * tasa * r.uniform(.98, 1.02))
            filas.append(fila)
    ancho = data._con_segmento(data._con_mes(_particion(pd.DataFrame(filas))))
    return data.despivotar_cobertura(ancho)


def distribucion_grupo() -> pd.DataFrame:
    r = _rng(3)
    filas = []
    for m in MESES:
        for s in SEGMENTOS[:3]:
            for p in PRODUCTOS:
                for j, g in enumerate(_grupos_de(p)):
                    for mod in MODELOS[:2] + [None]:
                        filas.append(dict(
                            idx_mes=m, segmento=s, producto=p, grupo=g,
                            modelo=mod,
                            clientes=int(3000 / (j + 1) * r.uniform(.8, 1.2))))
    d = pd.DataFrame(filas)
    return data._con_grupo(data._con_segmento(data._con_mes(_particion(d))))


def migracion(rezago: int = 1) -> pd.DataFrame:
    """Las SIETE categorías, con los nulos donde los deja el full outer join:
    la categoría de borde no tiene el lado que le falta."""
    r = _rng(4 + rezago)
    gs = theme.GRUPOS_BASE_ORDENADOS
    filas = []
    for m in MESES[rezago:]:
        for p in ("consumo", "tdc", "sufi_moto"):
            for o in gs:
                for d in gs:
                    salto = abs(gs.index(o) - gs.index(d))
                    if salto <= 3:
                        filas.append(dict(
                            idx_mes=m, producto=p, categoria="movimiento",
                            grupo_base_origen=o, grupo_base_destino=d,
                            segmento_anterior="4", segmento_actual="4",
                            modelo_anterior="T2",
                            modelo_actual="T2" if salto < 3 else None,
                            clientes=int((9000 if salto == 0 else 600 / salto)
                                         * r.uniform(.8, 1.2))))
            for cat, o, d, sa, sc, ma, mc in (
                    ("entrada", None, "G2", None, "4", None, "T2"),
                    ("ganancia_por_corte", None, "G5", None, "4", None, "T2"),
                    ("ganancia_de_modelo", None, "G6", None, "4", None, "T2"),
                    ("salida", "G6", None, "4", None, "T2", None),
                    ("perdida_por_corte", "G7", None, "4", None, "T2", None),
                    ("perdida_de_modelo", "G7", None, "11", None, "T2", None)):
                filas.append(dict(
                    idx_mes=m, producto=p, categoria=cat,
                    grupo_base_origen=o, grupo_base_destino=d,
                    segmento_anterior=sa, segmento_actual=sc,
                    modelo_anterior=ma, modelo_actual=mc,
                    clientes=int(400 * r.uniform(.8, 1.2))))
    d = _particion(pd.DataFrame(filas))
    return data._con_rezago(data._con_segmento(data._con_mes(d)), rezago)


def migracion_pd(rezago: int = 1) -> pd.DataFrame:
    r = _rng(10 + rezago)
    filas = []
    for m in MESES[rezago:]:
        for serie in ("general", "vivienda"):
            for o in range(1, 11):
                for d in range(1, 11):
                    if abs(o - d) <= 2:
                        filas.append(dict(
                            idx_mes=m, serie_pd=serie, modelo_origen="T2",
                            modelo_destino="T2", decil_origen=o, decil_destino=d,
                            categoria="movimiento",
                            clientes=int((5000 if o == d else 700) * r.uniform(.8, 1.2))))
            filas.append(dict(idx_mes=m, serie_pd=serie, modelo_origen=None,
                              modelo_destino="T2", decil_origen=None,
                              decil_destino=4, categoria="entrada", clientes=300))
    d = _particion(pd.DataFrame(filas))
    return data._con_rezago(data._con_mes(d), rezago)


def pd_por_modelo() -> pd.DataFrame:
    """Las dos escalas: probabilidad en bins log, puntaje en bins de 50."""
    r = _rng(20)
    filas = []
    for m in MESES:
        for serie in ("general", "vivienda"):
            for mod, escala in (("T2", "probabilidad_0_1"),
                                ("T1_COMPORT", "probabilidad_0_1"),
                                ("ADVANCE_1_1", "puntaje_0_999")):
                bins = range(-60, 0) if escala == "probabilidad_0_1" else range(0, 20)
                for b in bins:
                    if escala == "probabilidad_0_1":
                        lo, hi = 10 ** (b / 20), 10 ** ((b + 1) / 20)
                        peso = np.exp(-((b + 30) / 12) ** 2)
                    else:
                        lo, hi = b * 50.0, (b + 1) * 50.0
                        peso = np.exp(-((b - 10) / 4) ** 2)
                    n = int(20_000 * peso * r.uniform(.9, 1.1)) + 1
                    filas.append(dict(
                        idx_mes=m, segmento="4", serie_pd=serie, modelo=mod,
                        escala=escala, bin=b, bin_min=lo, bin_max=hi,
                        clientes=n, pd_suma=n * (lo + hi) / 2,
                        pd_min=lo, pd_max=hi))
    d = _particion(pd.DataFrame(filas))
    return data._con_segmento(data._con_mes(d))


def cortes_por_producto() -> pd.DataFrame:
    """Un corte SOLAPADO a propósito, para que se dibuje el marcador."""
    filas = []
    for m in MESES[-2:]:
        for k, p in enumerate(PRODUCTOS):
            previo = None
            for j, g in enumerate(theme.GRUPOS_BASE_ORDENADOS):
                lo = 10 ** (-4 + j * 0.4 + k * 0.01)
                hi = 10 ** (-4 + (j + 1) * 0.4 + k * 0.01)
                solapa = p == "tdc" and g == "G4"
                if solapa:
                    lo = previo * 0.9
                filas.append(dict(
                    idx_mes=m, producto=p, modelo="T2", grupo=g,
                    clientes=1000 * (8 - j), pd_min=lo, pd_max=hi,
                    pd_max_grupo_previo=previo, solapa=bool(solapa)))
                previo = hi
    d = _particion(pd.DataFrame(filas))
    return data._con_grupo(data._con_mes(d))


def puente_base() -> pd.DataFrame:
    filas = [dict(idx_mes=m, segmento=s, categoria=c, clientes=v)
             for m in MESES for s in SEGMENTOS
             for c, v in (("permanece", 1_900_000), ("entrada", 40_000),
                          ("salida", 55_000))]
    return data._con_segmento(data._con_mes(_particion(pd.DataFrame(filas))))


# --- perfilado ------------------------------------------------------------

def duplicados_ingestion_day() -> pd.DataFrame:
    filas = [dict(idx_mes=m, dias_distintos=1, primer_dia=21) for m in MESES]
    return data._con_mes(_particion(pd.DataFrame(filas)).drop(columns="idx_mes"))


def validacion_mapeo() -> pd.DataFrame:
    return pd.DataFrame([dict(producto=p, conteo_ancho=1000 + i,
                              conteo_largo=1000 + i, diferencia=0)
                         for i, p in enumerate(PRODUCTOS)])


def dominio_grupos() -> pd.DataFrame:
    return pd.DataFrame([dict(producto=p, grupo=g)
                         for p in PRODUCTOS for g in _grupos_de(p)])


def escala_modelos() -> pd.DataFrame:
    """Uno por modelo declarado, en su escala, más un modelo NUEVO de
    probabilidad (tiene que dar aviso) y filas sin modelo."""
    filas = []
    for m in MESES[-3:]:
        for p in ("consumo", "hip_vis"):
            for mod, lo, hi in (("T2", 0.001, 0.9), ("ADVANCE_1_1", 3.0, 998.0),
                                ("T4_NUEVO", 0.002, 0.7), (None, 0.001, 0.5)):
                filas.append(dict(idx_mes=m, producto=p, modelo=mod,
                                  pd_min=lo, pd_max=hi))
    return data._con_mes(_particion(pd.DataFrame(filas)).drop(columns="idx_mes"))


def nulos_pd_vs_grupo() -> pd.DataFrame:
    r = _rng(30)
    filas = []
    for m in MESES:
        for p in PRODUCTOS:
            v = int(700 * r.uniform(.95, 1.05)) if p == "calm" else 0
            filas.append(dict(idx_mes=m, producto=p, filas_totales=100_000,
                              pd_nulo=v, grupo_nulo=0,
                              pd_nulo_grupo_no_nulo=v, pd_no_nulo_grupo_nulo=0,
                              grupo_cadena_vacia=0, grupo_valor_na=0,
                              modelo_cadena_vacia=0))
    return data._con_mes(_particion(pd.DataFrame(filas)).drop(columns="idx_mes"))
