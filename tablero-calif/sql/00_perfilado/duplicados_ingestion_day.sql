-- ============================================================================
-- Perfilado: ¿hay más de un ingestion_day por mes?
-- ----------------------------------------------------------------------------
-- Pendiente 1 de CLAUDE.md. Opera directamente sobre la tabla ancha, sin
-- unpivot: la pregunta es sobre la partición, no sobre los productos.
--
-- Lectura del resultado:
--   - Si `dias_distintos` es 1 para todos los meses, la partición ya trae un
--     solo ingestion_day por mes y la deduplicación con row_number() se omite
--     en el resto de las queries.
--   - Si `dias_distintos` > 1 para algún mes, hay que deduplicar por
--     num_doc + tipo_doc quedándose con el último ingestion_day (el de
--     `ultimo_dia`) antes del cross join contra productos en
--     sql/_fragmentos/cte_productos.sql.
--
-- Parámetros:
--   {DESDE}, {HASTA} -- rango de meses, en ingestion_year*12+ingestion_month
-- ============================================================================

with meses as (
  select
    c.ingestion_year,
    c.ingestion_month,
    c.ingestion_day
  from resultados_riesgos.maestro_calificaciones_pn c
  where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}
)

select
  m.ingestion_year,
  m.ingestion_month,
  count(distinct m.ingestion_day) as dias_distintos,
  min(m.ingestion_day) as primer_dia,
  max(m.ingestion_day) as ultimo_dia
from meses m
group by
  m.ingestion_year,
  m.ingestion_month
order by
  m.ingestion_year,
  m.ingestion_month;
