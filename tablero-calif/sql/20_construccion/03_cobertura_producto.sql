-- ============================================================================
-- CONSTRUCCIÓN: proceso.cobertura_producto_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Cobertura por producto, en salida ANCHA: 16 columnas cob_*. La app la
-- despivota en pandas.
--
-- NO usa largo_calificaciones y no puede: esa tabla ya trae `grupo IS NOT NULL`
-- aplicado, que borra justamente las filas que hay que contar como no cubierto.
-- `count(columna)` ignora nulos, así que cada count da directo los cubiertos.
--
-- Se cuenta `g_*`, NO `pd_*`: el criterio de cobertura es tener grupo, y hay un
-- producto con 726 casos de pd nula con grupo poblado.
--
-- El nombre sigue al PRODUCTO, no al sufijo: cob_rotativo cuenta g_rota y
-- cob_sobregiro cuenta g_sobre. Son los dos únicos donde no coinciden.
--
-- No tiene pasos intermedios: 16 count() sobre una sola pasada.
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

drop table if exists proceso.cobertura_producto_{IDUNICO} purge;

create table proceso.cobertura_producto_{IDUNICO}
stored as parquet
as
select
  c.ingestion_year,
  c.ingestion_month,
  c.ingestion_year * 12 + c.ingestion_month as idx_mes,
  c.segmento,
  count(*)                  as clientes,
  count(c.g_consumo)         as cob_consumo,
  count(c.g_tdc)             as cob_tdc,
  count(c.g_libranza)        as cob_libranza,
  count(c.g_rota)            as cob_rotativo,
  count(c.g_hip_vis)         as cob_hip_vis,
  count(c.g_hip_novis)       as cob_hip_novis,
  count(c.g_lea_hab_vis)     as cob_lea_hab_vis,
  count(c.g_lea_hab_novis)   as cob_lea_hab_novis,
  count(c.g_comercial)       as cob_comercial,
  count(c.g_micro)           as cob_micro,
  count(c.g_sobre)           as cob_sobregiro,
  count(c.g_sufi_veh)        as cob_sufi_veh,
  count(c.g_sufi_moto)       as cob_sufi_moto,
  count(c.g_sufi_cpe)        as cob_sufi_cpe,
  count(c.g_sufi_con)        as cob_sufi_con,
  count(c.g_calm)            as cob_calm
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

compute stats proceso.cobertura_producto_{IDUNICO};
