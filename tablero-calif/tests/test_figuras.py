"""Llama a TODAS las funciones públicas de charts con datos sintéticos.

Existe porque dos veces se rompió algo que py_compile e importar el módulo no
ven, porque no ejecutan el cuerpo de las funciones:

  - los @dataclass que se perdieron al partir charts.py;
  - `_FAM`, que quedó sin definir en charts_panorama y charts_modelos.

Tres reglas, y las tres importan:

  1. COBERTURA OBLIGATORIA. Cada nombre público de charts.__all__ que sea
     invocable tiene que tener al menos un caso en CASOS. Una función nueva sin
     caso hace fallar la prueba y dice cuál.
  2. CON DATOS. Un caso con un DataFrame vacío sale por `_sin_datos` y no
     ejecuta el cuerpo: así pasaba la prueba de humo mientras `_FAM` estaba
     roto. Por eso toda figura tiene que salir CON trazas.
  3. ABRIENDO RAMAS. Los filtros opcionales (familia, segmento, modelo, modo,
     base móvil...) van en casos propios: `_FAM` estaba justo detrás de un
     filtro de familia.

Aparte, cada función de figura se prueba también con un DataFrame vacío: tiene
que devolver una figura de "sin datos", no reventar.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import logging
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
# Fuera de `streamlit run`, el caché avisa que no hay runtime. Streamlit arma
# sus loggers al importarse, así que un setLevel previo no alcanza: la opción
# de configuración sí la respeta.
os.environ.setdefault("STREAMLIT_LOGGER_LEVEL", "error")
logging.getLogger("streamlit").setLevel(logging.ERROR)

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

import charts  # noqa: E402
import data  # noqa: E402
import fixtures as fx  # noqa: E402
import theme  # noqa: E402

M = fx.ULTIMO


class _F:
    """Los fixtures se construyen una sola vez para toda la corrida."""
    def __init__(self):
        self.base = fx.base_clientes()
        self.cob = fx.cobertura_producto()
        self.dist = fx.distribucion_grupo()
        self.dist_mes = self.dist[self.dist["idx_mes"] == M]
        self.mig = fx.migracion(1)
        self.mig6 = fx.migracion(6)
        self.mig_mes = self.mig[self.mig["idx_mes"] == M]
        self.mig_pd = fx.migracion_pd(1)
        self.pdm = fx.pd_por_modelo()
        self.cortes = fx.cortes_por_producto()
        self.cortes_mes = self.cortes[self.cortes["idx_mes"] == M]
        self.puente = fx.puente_base()
        self.nulos = fx.nulos_pd_vs_grupo()
        self.modelos_decl = data.leer_modelos()
        self.clasif = data.clasificar_modelos(fx.escala_modelos(), self.modelos_decl)


F = _F()
FIG, DF, STR, TUPLA, CHEQUEO = "figura", "dataframe", "str", "tupla", "chequeo"

# nombre -> [(descripción del caso, llamada, tipo esperado)]
CASOS: dict[str, list] = {
    # --- panorama y evolución ---------------------------------------------
    "composicion_grupo": [
        ("todas las familias", lambda: charts.composicion_grupo(F.dist_mes, "todas"), FIG),
        ("filtro de familia", lambda: charts.composicion_grupo(F.dist_mes, "consumo"), FIG),
        ("familia sufi, con aperturas", lambda: charts.composicion_grupo(F.dist_mes, "sufi"), FIG),
        ("absoluto, orden fijo", lambda: charts.composicion_grupo(
            F.dist_mes, "todas", orden_productos=fx.PRODUCTOS, porcentaje=False), FIG),
    ],
    "heatmap_segmento_grupo": [
        ("todos", lambda: charts.heatmap_segmento_grupo(F.dist_mes, "todos"), FIG),
        ("un producto, sin normalizar", lambda: charts.heatmap_segmento_grupo(
            F.dist_mes, "sufi_moto", normalizar=False), FIG),
    ],
    "cobertura": [
        ("todos", lambda: charts.cobertura(F.cob[F.cob["idx_mes"] == M], "todos"), FIG),
        ("un segmento", lambda: charts.cobertura(F.cob[F.cob["idx_mes"] == M], "11"), FIG),
    ],
    "mezcla_riesgo": [
        ("consumo", lambda: charts.mezcla_riesgo(F.dist, "consumo"), FIG),
        ("sufi con aperturas", lambda: charts.mezcla_riesgo(F.dist, "sufi_con"), FIG),
    ],
    "base_clientes_tiempo": [("", lambda: charts.base_clientes_tiempo(F.base), FIG)],
    "vigencia_modelos": [("", lambda: charts.vigencia_modelos(F.dist), FIG)],
    "modelos_vivos": [("", lambda: charts.modelos_vivos(F.dist), FIG)],
    # --- anomalías ----------------------------------------------------------
    "matriz_segmento_producto": [
        (f"modo {m}", (lambda m=m: charts.matriz_segmento_producto(F.cob, M, m)), FIG)
        for m in charts.MODOS_MATRIZ
    ],
    "ranking_anomalias": [
        ("cantidad", lambda: charts.ranking_anomalias(F.cob, M, "cantidad"), charts.Anomalias),
        ("cobertura con tope", lambda: charts.ranking_anomalias(F.cob, M, "cobertura", 5),
         charts.Anomalias),
    ],
    "top_por_segmento": [
        ("", lambda: charts.top_por_segmento(
            charts.ranking_anomalias(F.cob, M).ranking, fx.SEGMENTOS), list),
    ],
    "mini_serie": [("", lambda: charts.mini_serie([1, 3, 2, 5]), FIG)],
    "puente_base": [
        ("todos", lambda: charts.puente_base(F.puente, M), FIG),
        ("un segmento", lambda: charts.puente_base(F.puente, M, "11"), FIG),
    ],
    "puente_por_segmento": [("", lambda: charts.puente_por_segmento(F.puente, M), FIG)],
    # --- migración ----------------------------------------------------------
    "matriz_migracion": [
        ("mismo segmento", lambda: charts.matriz_migracion(F.mig_mes, "consumo"), FIG),
        ("todos los segmentos, filtro", lambda: charts.matriz_migracion(
            F.mig_mes, "consumo", False, "11"), FIG),
        ("varios meses, rezago 6", lambda: charts.matriz_migracion(F.mig6, "tdc"), FIG),
    ],
    "flujo_modelos": [("", lambda: charts.flujo_modelos(F.mig_mes, "consumo"), FIG)],
    "estabilidad_deterioro": [
        ("rezago 1", lambda: charts.estabilidad_deterioro(F.mig, "consumo"), FIG),
        ("rezago 6", lambda: charts.estabilidad_deterioro(F.mig6, "consumo"), FIG),
    ],
    "serie_estabilidad": [("", lambda: charts.serie_estabilidad(F.mig, "consumo"), DF)],
    "matriz_migracion_pd": [
        (s, (lambda s=s: charts.matriz_migracion_pd(
            F.mig_pd[F.mig_pd["idx_mes"] == M], s)), FIG)
        for s in ("general", "vivienda")
    ],
    "tabla_peores_saltos": [("", lambda: charts.tabla_peores_saltos(F.mig_mes), DF)],
    "filtrar_mismo_segmento": [("", lambda: charts.filtrar_mismo_segmento(F.mig_mes), DF)],
    # --- modelos ------------------------------------------------------------
    "histograma_pd": [
        (e, (lambda e=e: charts.histograma_pd(F.pdm[F.pdm["idx_mes"] == M], e)), FIG)
        for e in ("probabilidad_0_1", "puntaje_0_999")
    ],
    "psi_grupos": [
        ("base fija", lambda: charts.psi_grupos(F.dist, "consumo"), DF),
        ("base móvil, un modelo", lambda: charts.psi_grupos(
            F.dist, "consumo", "T2", "grupo", True), DF),
    ],
    "psi_grupos_grafico": [
        ("nivel 1", lambda: charts.psi_grupos_grafico(F.dist, "consumo"), TUPLA),
        ("nivel 2, base móvil", lambda: charts.psi_grupos_grafico(
            F.dist, "consumo", "T2", "grupo_base", True), TUPLA),
    ],
    "aporte_psi_grupo": [
        ("", lambda: charts.aporte_psi_grupo(F.dist, M, "consumo"), DF),
    ],
    "psi_pd": [("", lambda: charts.psi_pd(F.pdm, "general"), TUPLA)],
    "psi_pd_grafico": [
        ("base fija", lambda: charts.psi_pd_grafico(F.pdm, "general"), TUPLA),
        ("base móvil", lambda: charts.psi_pd_grafico(F.pdm, "vivienda", True), TUPLA),
    ],
    "sensibilidad_cortes": [
        ("todos los modelos", lambda: charts.sensibilidad_cortes(F.cortes_mes, "todos"), FIG),
        ("un modelo", lambda: charts.sensibilidad_cortes(F.cortes_mes, "T2"), FIG),
    ],
    "tabla_solapamientos": [("", lambda: charts.tabla_solapamientos(F.cortes_mes), DF)],
    # --- salud del dato -----------------------------------------------------
    "chequeo_ingestion_day": [
        ("", lambda: charts.chequeo_ingestion_day(fx.duplicados_ingestion_day()), CHEQUEO)],
    "chequeo_mapeo": [("", lambda: charts.chequeo_mapeo(fx.validacion_mapeo()), CHEQUEO)],
    "chequeo_dominio": [
        ("", lambda: charts.chequeo_dominio(fx.dominio_grupos(), F.clasif), CHEQUEO)],
    "chequeo_pd_grupo": [("", lambda: charts.chequeo_pd_grupo(F.nulos), CHEQUEO)],
    "resumen_global": [
        ("", lambda: charts.resumen_global(
            [charts.chequeo_pd_grupo(F.nulos),
             charts.chequeo_dominio(fx.dominio_grupos(), F.clasif)]), TUPLA)],
    "discordancia_pd_grupo": [("", lambda: charts.discordancia_pd_grupo(F.nulos), FIG)],
    # --- base ---------------------------------------------------------------
    "mes_comparacion": [("", lambda: charts.mes_comparacion(fx.MESES, M), TUPLA)],
    "leyenda_comparacion": [("", lambda: charts.leyenda_comparacion(F.mig_mes), STR)],
    "guia": [(k, (lambda k=k: charts.guia(k)), STR) for k in sorted(charts.GUIAS)],
}

# Funciones de figura: además se prueban con un DataFrame vacío.
VACIO = {
    "composicion_grupo": lambda v: charts.composicion_grupo(v, "consumo"),
    "heatmap_segmento_grupo": lambda v: charts.heatmap_segmento_grupo(v),
    "cobertura": lambda v: charts.cobertura(v, "4"),
    "mezcla_riesgo": lambda v: charts.mezcla_riesgo(v, "consumo"),
    "base_clientes_tiempo": charts.base_clientes_tiempo,
    "vigencia_modelos": charts.vigencia_modelos,
    "modelos_vivos": charts.modelos_vivos,
    "matriz_segmento_producto": lambda v: charts.matriz_segmento_producto(v, M, "variacion"),
    "puente_base": lambda v: charts.puente_base(v, M),
    "puente_por_segmento": lambda v: charts.puente_por_segmento(v, M),
    "matriz_migracion": lambda v: charts.matriz_migracion(v, "consumo"),
    "flujo_modelos": charts.flujo_modelos,
    "estabilidad_deterioro": lambda v: charts.estabilidad_deterioro(v, "consumo"),
    "matriz_migracion_pd": lambda v: charts.matriz_migracion_pd(v, "general"),
    "histograma_pd": lambda v: charts.histograma_pd(v, "probabilidad_0_1"),
    "sensibilidad_cortes": charts.sensibilidad_cortes,
    "discordancia_pd_grupo": charts.discordancia_pd_grupo,
}


def _figuras(resultado) -> list[go.Figure]:
    if isinstance(resultado, go.Figure):
        return [resultado]
    if isinstance(resultado, tuple):
        return [x for x in resultado if isinstance(x, go.Figure)]
    return []


class TestCobertura(unittest.TestCase):
    def test_toda_funcion_publica_tiene_caso(self):
        publicas = {n for n in charts.__all__
                    if callable(getattr(charts, n))
                    and not isinstance(getattr(charts, n), type)}
        faltan = sorted(publicas - set(CASOS))
        self.assertFalse(faltan, f"funciones públicas sin caso de prueba: {faltan}")
        sobran = sorted(set(CASOS) - publicas)
        self.assertFalse(sobran, f"casos de funciones que ya no son públicas: {sobran}")

    def test_toda_figura_tiene_caso_vacio(self):
        figuras = {n for n, cs in CASOS.items() if any(t == FIG for _, _, t in cs)}
        figuras.discard("mini_serie")          # recibe una lista, no un DataFrame
        faltan = sorted(figuras - set(VACIO))
        self.assertFalse(faltan, f"figuras sin caso con DataFrame vacío: {faltan}")


class TestFiguras(unittest.TestCase):
    def test_cada_caso(self):
        for nombre, casos in sorted(CASOS.items()):
            for desc, llamada, tipo in casos:
                with self.subTest(funcion=nombre, caso=desc):
                    r = llamada()
                    if tipo == FIG:
                        self.assertIsInstance(r, go.Figure)
                    elif tipo == DF:
                        self.assertIsInstance(r, pd.DataFrame)
                    elif tipo == STR:
                        self.assertIsInstance(r, str)
                        self.assertTrue(r, "texto vacío")
                    elif tipo == TUPLA:
                        self.assertIsInstance(r, tuple)
                    elif tipo == CHEQUEO:
                        self.assertIsInstance(r, charts.Chequeo)
                        self.assertTrue(r.ejecutado)
                    else:
                        self.assertIsInstance(r, tipo)
                    for fig in _figuras(r):
                        fig.to_json()
                        # Regla 2: con datos, la figura tiene trazas. Una
                        # figura de "sin datos" (solo una anotación) acá
                        # significa que el caso no llegó al cuerpo.
                        self.assertGreater(
                            len(fig.data), 0,
                            f"{nombre} [{desc}] salió sin trazas: el caso no "
                            f"ejecutó el cuerpo de la función")

    def test_vacio_no_revienta(self):
        for nombre, llamada in sorted(VACIO.items()):
            with self.subTest(funcion=nombre):
                fig = llamada(pd.DataFrame())
                self.assertIsInstance(fig, go.Figure)
                fig.to_json()


class TestColorPorSignificado(unittest.TestCase):
    """En los heatmaps divergentes el color dice lo que SIGNIFICA el valor, no
    su signo. Cada visual declara acá si subir es bueno o malo, y la prueba
    verifica que el extremo NEGATIVO de su escala sea el color que
    corresponde: mejora si subir es malo, deterioro si subir es bueno.

    Antes la escala era una sola y la matriz segmento × producto pintaba una
    caída a -100% -- la anomalía que se busca -- en el color de mejora.
    """
    MEJORA = theme.escala_divergente("malo")[0][1]      # extremo azul
    DETERIORO = theme.escala_divergente("bueno")[0][1]  # extremo rojo

    # visual -> (figura, qué significa subir)
    DIVERGENTES = {
        "matriz_segmento_producto (variación)": (
            lambda: charts.matriz_segmento_producto(F.cob, M, "variacion"), "bueno"),
        "matriz_migracion": (
            lambda: charts.matriz_migracion(F.mig_mes, "consumo"), "malo"),
        "matriz_migracion_pd": (
            lambda: charts.matriz_migracion_pd(F.mig_pd[F.mig_pd["idx_mes"] == M],
                                               "general"), "malo"),
    }

    def test_extremo_negativo_segun_significado(self):
        for nombre, (hacer, subir) in self.DIVERGENTES.items():
            with self.subTest(visual=nombre, subir=subir):
                escala = hacer().data[0].colorscale
                negativo, positivo = escala[0][1], escala[-1][1]
                if subir == "bueno":
                    self.assertEqual(negativo, self.DETERIORO,
                                     "bajar es lo malo: el extremo negativo "
                                     "tiene que ser el color de deterioro")
                    self.assertEqual(positivo, self.MEJORA)
                else:
                    self.assertEqual(negativo, self.MEJORA,
                                     "subir es lo malo: el extremo negativo "
                                     "tiene que ser el color de mejora")
                    self.assertEqual(positivo, self.DETERIORO)

    def test_espejo_exacto(self):
        malo, bueno = theme.escala_divergente("malo"), theme.escala_divergente("bueno")
        self.assertEqual([c for _, c in bueno], [c for _, c in reversed(malo)])
        self.assertEqual([p for p, _ in bueno], [round(1 - p, 6) for p, _ in reversed(malo)])

    def test_decidir_es_obligatorio(self):
        with self.assertRaises(ValueError):
            theme.escala_divergente("neutro")


if __name__ == "__main__":
    unittest.main()
