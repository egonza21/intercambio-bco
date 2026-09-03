-- ============================================================================
-- CONSTRUCCIÓN: proceso.base_clientes_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Clientes por mes y segmento. Denominador del tablero y tabla contra la que
-- reconcilian las entradas y salidas de la migración.
--
-- Sale de la tabla ANCHA: en la larga `count(*)` cuenta pares cliente-producto.
-- `count(*)` cuenta clientes porque la ancha trae una fila por cliente y mes.
--
-- No tiene pasos intermedios: es un solo agregado sobre la tabla fuente.
--
-- ----------------------------------------------------------------------------
-- SIN CTEs: cada paso intermedio es una tabla física
-- ----------------------------------------------------------------------------
-- Impala no materializa los CTEs, los inlinea. Encadenar varios en un mismo
-- CREATE TABLE AS deja todos los intermedios en memoria dentro de un solo
-- plan, que es lo que hacía cancelar las ETL pesadas. Con tablas físicas cada
-- paso va a disco y el `compute stats` de cada una le da al planificador los
-- tamaños reales antes del paso que la consume.
--
-- Las tmp_ se borran al final, cuando la tabla definitiva ya existe. Los drop
-- del arranque limpian las que hayan quedado de una corrida interrumpida.
-- ============================================================================

drop table if exists proceso.base_clientes_{IDUNICO} purge;

create table proceso.base_clientes_{IDUNICO}
stored as parquet
as
select
  c.ingestion_year,
  c.ingestion_month,
  c.ingestion_year * 12 + c.ingestion_month as idx_mes,
  c.segmento,
  count(*) as clientes
from resultados_riesgos.maestro_calificaciones_pn c
  -- Salvaguarda contra ingestas parciales de principios de mes. Ver CLAUDE.md,
  -- "El filtro de ingestion_day". HOY NO DESCARTA NADA: los días observados van
  -- de 19 a 24. Está justamente para el día en que aparezca una carga a medias,
  -- y por eso queda escrito para qué sirve -- si no, dentro de seis meses
  -- alguien lo borra por parecer inútil.
  where c.ingestion_day >= 15
group by
  c.ingestion_year,
  c.ingestion_month,
  c.segmento;

compute stats proceso.base_clientes_{IDUNICO};
