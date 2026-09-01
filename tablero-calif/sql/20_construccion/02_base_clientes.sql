-- ============================================================================
-- CONSTRUCCIÓN: proceso.base_clientes
-- ----------------------------------------------------------------------------
-- Clientes por mes y segmento. Es el denominador de todo el tablero y la tabla
-- contra la que reconcilian las entradas y salidas de la migración.
--
-- Sale de la tabla ANCHA, no de largo_calificaciones: en la larga `count(*)`
-- cuenta pares cliente-producto, no clientes.
--
-- `count(*)` cuenta clientes porque la tabla ancha trae una sola fila por
-- cliente + mes (CLAUDE.md, "La deduplicación por ingestion_day NO se hace en
-- SQL"). Si esa premisa se rompiera, este conteo duplica en silencio: por eso
-- el chequeo 1 de la página de salud del dato.
--
-- SIN PARÁMETROS: toda la ventana disponible. La app filtra en pandas.
-- ============================================================================

drop table if exists proceso.base_clientes purge;

create table proceso.base_clientes
stored as parquet
as
select
  c.ingestion_year,
  c.ingestion_month,
  c.ingestion_year * 12 + c.ingestion_month as idx_mes,
  c.segmento,
  count(*) as clientes
from resultados_riesgos.maestro_calificaciones_pn c
group by
  c.ingestion_year,
  c.ingestion_month,
  c.segmento;

compute stats proceso.base_clientes;
