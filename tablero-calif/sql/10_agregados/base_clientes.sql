-- ============================================================================
-- Agregado: base de clientes por mes y segmento
-- ----------------------------------------------------------------------------
-- Produce una fila por ingestion_year + ingestion_month + segmento con el
-- conteo de clientes de la tabla ANCHA. Es el denominador de todo el tablero
-- y la tabla contra la que reconcilian las entradas y salidas de la matriz de
-- migración.
--
-- Parámetros:
--   {DESDE}, {HASTA} -- rango de meses, en ingestion_year*12+ingestion_month
--
-- ----------------------------------------------------------------------------
-- Por qué la tabla ancha y no la larga
-- ----------------------------------------------------------------------------
-- En la tabla larga `count(*)` cuenta pares cliente-producto, no clientes: un
-- cliente con calificación en 5 productos aportaría 5. Sobre la ancha cada
-- fila es un cliente-mes, así que el conteo es directo.
--
-- `clientes` es `count(*)`, no un COUNT(DISTINCT). Es válido porque la tabla
-- ancha trae una sola fila por cliente + mes (verificado 2026-08-25: un solo
-- ingestion_day por mes en los 16 meses de la ventana, sin duplicados). Si
-- alguna vez hiciera falta reverificarlo desde aquí, la forma permitida en
-- Impala sin activar APPX_COUNT_DISTINCT es el COUNT(DISTINCT) multicolumna
-- `count(distinct c.num_doc, c.tipo_doc)`, que cuenta combinaciones distintas
-- y es un solo agregado. Se deja fuera porque es caro sobre ~15 MM de filas
-- por mes y la premisa ya está verificada.
--
-- OJO al leer este agregado junto a los de composición: la base viene
-- bajando sostenidamente (16,6 MM en 2025-05 a 15,2 MM en 2026-08, -9%). Ver
-- CLAUDE.md, "La base de clientes se contrae".
--
-- Sin ORDER BY a propósito: Power BI importa y ordena en el modelo.
-- ============================================================================

with base as (
  select
    c.ingestion_year,
    c.ingestion_month,
    c.segmento
  from resultados_riesgos.maestro_calificaciones_pn c
  where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}
)

select
  b.ingestion_year,
  b.ingestion_month,
  b.segmento,
  count(*) as clientes
from base b
group by
  b.ingestion_year,
  b.ingestion_month,
  b.segmento;
