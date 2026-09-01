-- ============================================================================
-- CONSTRUCCIÓN: proceso.distribucion_grupo
-- ----------------------------------------------------------------------------
-- Composición de la cartera por grupo de riesgo. Alimenta la barra apilada,
-- el heatmap segmento x grupo y la vigencia de modelos.
--
-- DEPENDE de proceso.largo_calificaciones. Ver 00_orden.md.
--
-- Nada de `pd`: solo hay dos PD por cliente, no 16, así que traerla con
-- `producto` en el grano invitaba a sumar la misma PD doce veces. Ver
-- CLAUDE.md, "La PD no es por producto".
--
-- `grupo_base` y `grupo_orden` tampoco: son presentacionales y los resuelve
-- la app desde theme.DIM_GRUPO.
--
-- El filtro de grupo ya viene aplicado en la tabla de origen.
-- SIN PARÁMETROS: toda la ventana disponible.
-- ============================================================================

drop table if exists proceso.distribucion_grupo purge;

create table proceso.distribucion_grupo
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
from proceso.largo_calificaciones l
group by
  l.ingestion_year,
  l.ingestion_month,
  l.idx_mes,
  l.segmento,
  l.producto,
  l.grupo,
  l.modelo;

compute stats proceso.distribucion_grupo;
