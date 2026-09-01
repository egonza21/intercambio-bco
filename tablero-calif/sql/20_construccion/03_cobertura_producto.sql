-- ============================================================================
-- CONSTRUCCIÓN: proceso.cobertura_producto_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Cobertura por producto, en salida ANCHA: 16 columnas cob_*, una por
-- producto. La app la despivota en pandas.
--
-- NO usa largo_calificaciones y no puede usarla: esa tabla ya trae aplicado el
-- filtro `grupo IS NOT NULL`, que borra justamente las filas que hay que
-- contar como "no cubierto". La cobertura se calcula sobre la ancha, con
-- `count(columna)`, que ignora nulos.
--
-- Sale ancha a propósito: así se resuelve con 16 count() sobre una sola pasada,
-- sin cross join.
--
-- Se cuenta `g_*`, NO `pd_*`. El criterio de cobertura es tener grupo, y hay un
-- producto con 726 casos de pd nula con grupo poblado.
--
-- El nombre de la columna sigue al PRODUCTO, no al sufijo de la fuente:
-- cob_rotativo cuenta g_rota y cob_sobregiro cuenta g_sobre. Son los dos
-- únicos casos donde no coinciden, y el lugar más probable de un desalineo.
--
-- SIN PARÁMETROS: toda la ventana disponible.
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
  count(c.g_consumo)        as cob_consumo,
  count(c.g_tdc)            as cob_tdc,
  count(c.g_libranza)       as cob_libranza,
  count(c.g_rota)           as cob_rotativo,
  count(c.g_hip_vis)        as cob_hip_vis,
  count(c.g_hip_novis)      as cob_hip_novis,
  count(c.g_lea_hab_vis)    as cob_lea_hab_vis,
  count(c.g_lea_hab_novis)  as cob_lea_hab_novis,
  count(c.g_comercial)      as cob_comercial,
  count(c.g_micro)          as cob_micro,
  count(c.g_sobre)          as cob_sobregiro,
  count(c.g_sufi_veh)       as cob_sufi_veh,
  count(c.g_sufi_moto)      as cob_sufi_moto,
  count(c.g_sufi_cpe)       as cob_sufi_cpe,
  count(c.g_sufi_con)       as cob_sufi_con,
  count(c.g_calm)           as cob_calm
from resultados_riesgos.maestro_calificaciones_pn c
group by
  c.ingestion_year,
  c.ingestion_month,
  c.segmento;

compute stats proceso.cobertura_producto_{IDUNICO};
