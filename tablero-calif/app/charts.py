"""Fachada: reexporta las figuras de los módulos por página.

`charts.py` tenía 1.647 líneas y 36 funciones, y cualquier cambio obligaba a
leer un archivo entero para ubicar cuatro funciones. El corte es POR PÁGINA,
que es como se piensa el tablero:

    charts_base       helpers compartidos (_sin_datos, _t, contra qué mes)
    charts_panorama   Panorama del mes y Evolución
    charts_anomalias  ranking, matriz segmento × producto y puente
    charts_migracion  migración de grupo, de PD y de modelo
    charts_modelos    histograma de PD, PSI y cortes
    charts_salud      los cuatro chequeos de salud del dato

Este archivo existe para que `import charts` siga funcionando en las páginas y
en export.py: la división es del código, no de la interfaz. La regla de fondo
no cambia -- NINGUNA de estas funciones renderiza. Cada figura se define UNA
vez y tiene dos salidas: main.py la pinta con st.plotly_chart y export.py la
escribe con write_html. Si un gráfico se ve distinto en el HTML que en la app,
es un bug de la función, no de dos implementaciones que se separaron.

Las funciones que devuelven tablas (`tabla_*`) devuelven DataFrames, no
figuras: son alertas de calidad, no gráficos.
"""
from __future__ import annotations

from charts_base import VACIO, mes_comparacion, leyenda_comparacion
from charts_panorama import (
    composicion_grupo,
    heatmap_segmento_grupo,
    cobertura,
    mezcla_riesgo,
    base_clientes_tiempo,
    vigencia_modelos,
    modelos_vivos)
from charts_anomalias import (
    MODOS_MATRIZ,
    matriz_segmento_producto,
    PISO_VARIACION,
    BASE_MINIMA,
    MESES_MINIMOS,
    Anomalias,
    ranking_anomalias,
    top_por_segmento,
    POR_SEGMENTO,
    mini_serie,
    puente_base,
    puente_por_segmento)
from charts_migracion import (
    SIN_MODELO,
    filtrar_mismo_segmento,
    matriz_migracion,
    flujo_modelos,
    estabilidad_deterioro,
    serie_estabilidad,
    matriz_migracion_pd,
    tabla_peores_saltos)
from charts_modelos import (
    histograma_pd,
    MIN_PESO_BIN,
    psi_grupos,
    aporte_psi_grupo,
    psi_pd,
    psi_grupos_grafico,
    psi_pd_grafico,
    sensibilidad_cortes,
    tabla_solapamientos)
from charts_salud import (
    Chequeo,
    resumen_global,
    chequeo_ingestion_day,
    chequeo_mapeo,
    chequeo_dominio,
    chequeo_pd_grupo,
    discordancia_pd_grupo)

__all__ = [
    "Anomalias", "BASE_MINIMA", "Chequeo", "MESES_MINIMOS", "MIN_PESO_BIN",
    "MODOS_MATRIZ", "PISO_VARIACION", "VACIO", "aporte_psi_grupo",
    "base_clientes_tiempo", "chequeo_dominio", "chequeo_ingestion_day",
    "chequeo_mapeo", "chequeo_pd_grupo", "cobertura", "composicion_grupo",
    "discordancia_pd_grupo", "estabilidad_deterioro", "flujo_modelos",
    "heatmap_segmento_grupo", "histograma_pd", "leyenda_comparacion",
    "SIN_MODELO", "filtrar_mismo_segmento",
    "matriz_migracion", "matriz_migracion_pd", "matriz_segmento_producto",
    "mes_comparacion", "mezcla_riesgo", "mini_serie", "modelos_vivos",
    "psi_grupos", "psi_grupos_grafico", "psi_pd", "psi_pd_grafico",
    "puente_base", "puente_por_segmento", "ranking_anomalias", "top_por_segmento", "POR_SEGMENTO",
    "resumen_global", "sensibilidad_cortes", "serie_estabilidad",
    "tabla_peores_saltos", "tabla_solapamientos", "vigencia_modelos",
]
