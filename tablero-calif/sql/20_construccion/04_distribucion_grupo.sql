-- ============================================================================
-- CONSTRUCCIÓN: proceso.distribucion_grupo_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Composición de la cartera por grupo de riesgo. Alimenta la barra apilada, el
-- heatmap segmento x grupo y la vigencia de modelos.
--
-- DEPENDE de proceso.largo_calificaciones_{IDUNICO}.
--
-- Nada de `pd`: solo hay dos PD por cliente, no 16, así que traerla con
-- `producto` en el grano invitaba a sumar la misma PD doce veces.
--
-- No tiene pasos intermedios: un agregado sobre la tabla larga.
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

drop table if exists proceso.distribucion_grupo_{IDUNICO} purge;

create table proceso.distribucion_grupo_{IDUNICO}
stored as parquet
as
select
  l.ingestion_year,
  l.ingestion_month,
  l.idx_mes,
  l.segmento,
  l.producto,
  l.grupo,
  l.modelo,
  count(*) as clientes
from proceso.largo_calificaciones_{IDUNICO} l
group by
  l.ingestion_year,
  l.ingestion_month,
  l.idx_mes,
  l.segmento,
  l.producto,
  l.grupo,
  l.modelo;

compute stats proceso.distribucion_grupo_{IDUNICO};
