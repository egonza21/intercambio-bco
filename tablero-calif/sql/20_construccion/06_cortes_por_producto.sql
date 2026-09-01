-- ============================================================================
-- CONSTRUCCIÓN: proceso.cortes_por_producto
-- ----------------------------------------------------------------------------
-- Fronteras de corte de PD por producto y grupo. Alimenta el visual de
-- sensibilidad de cortes y la tabla de solapamientos.
--
-- DEPENDE de proceso.largo_calificaciones. Ver 00_orden.md.
--
-- El max de un grupo y el min del siguiente son la frontera. `solapa` marca
-- donde el rango de un grupo se cruza con el del anterior: dos clientes con la
-- misma PD en grupos distintos, o sea que el corte de ese producto no depende
-- solo de la PD. El orden es por pd_min, no por grupo_orden, para que la
-- validación sea independiente de la convención de nombres.
--
-- SIN PARÁMETROS: toda la ventana disponible.
-- ============================================================================

drop table if exists proceso.cortes_por_producto purge;

create table proceso.cortes_por_producto
stored as parquet
as
with rangos as (
  select
    l.ingestion_year,
    l.ingestion_month,
    l.idx_mes,
    l.producto,
    l.modelo,
    l.grupo,
    count(*)   as clientes,
    min(l.pd)  as pd_min,
    max(l.pd)  as pd_max
  from proceso.largo_calificaciones l
  where l.pd is not null
  group by
    l.ingestion_year,
    l.ingestion_month,
    l.idx_mes,
    l.producto,
    l.modelo,
    l.grupo
)

select
  r.ingestion_year,
  r.ingestion_month,
  r.idx_mes,
  r.producto,
  r.modelo,
  r.grupo,
  r.clientes,
  r.pd_min,
  r.pd_max,
  lag(r.pd_max) over (
    partition by r.idx_mes, r.producto, r.modelo
    order by r.pd_min
  ) as pd_max_grupo_previo,
  r.pd_min < lag(r.pd_max) over (
    partition by r.idx_mes, r.producto, r.modelo
    order by r.pd_min
  ) as solapa
from rangos r;

compute stats proceso.cortes_por_producto;
