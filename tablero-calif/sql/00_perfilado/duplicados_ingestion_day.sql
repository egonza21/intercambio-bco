-- ============================================================================
-- Perfilado: ¿hay más de un ingestion_day por mes?
-- ----------------------------------------------------------------------------
-- Pendiente 1 de CLAUDE.md. Opera directamente sobre la tabla ancha, sin
-- unpivot: la pregunta es sobre la partición, no sobre los productos.
--
-- Resuelto 2026-08-25: sí hubo un mes con `dias_distintos` > 1 (reproceso
-- controlado, un ensayo). Fue un caso único, ya corregido a mano borrando la
-- ingestión del ensayo de ese mes, y no se va a repetir. Por eso
-- sql/_fragmentos/cte_productos.sql NO deduplica con row_number(): asume una
-- sola fila por num_doc + tipo_doc + mes. Esta query se conserva como
-- verificación puntual, por si hace falta reconfirmar el estado de la
-- partición antes de correr los agregados.
--
-- ESTA CONSULTA NO LLEVA EL FILTRO `ingestion_day >= 15`, a diferencia del
-- resto del repo. Es deliberado: su trabajo es detectar ingestas anómalas, y
-- filtrarlas la dejaría ciega justo para lo que existe. Si un mes llega con
-- una carga parcial de día 3, esta consulta tiene que verla.
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
