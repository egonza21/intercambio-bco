-- ============================================================================
-- CONSTRUCCIÓN: proceso.cortes_por_producto_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Fronteras de corte de PD por producto y grupo. Alimenta el visual de
-- sensibilidad de cortes y la tabla de solapamientos.
--
-- DEPENDE de proceso.largo_calificaciones_{IDUNICO}.
--
-- El max de un grupo y el min del siguiente son la frontera. `solapa` marca
-- donde el rango de un grupo se cruza con el del anterior: dos clientes con la
-- misma PD en grupos distintos, o sea que el corte no depende solo de la PD.
-- El orden es por pd_min, no por grupo_orden, para que la validación sea
-- independiente de la convención de nombres.
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

drop table if exists proceso.tmp_cortes_rangos_{IDUNICO} purge;

-- --- 1. rango de PD por celda ------------------------------------------------
create table proceso.tmp_cortes_rangos_{IDUNICO}
stored as parquet
as
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
  from proceso.largo_calificaciones_{IDUNICO} l
  where l.pd is not null
  group by
    l.ingestion_year,
    l.ingestion_month,
    l.idx_mes,
    l.producto,
    l.modelo,
    l.grupo;

compute stats proceso.tmp_cortes_rangos_{IDUNICO};

-- --- 2. tabla final, con la marca de solapamiento ----------------------------
drop table if exists proceso.cortes_por_producto_{IDUNICO} purge;

create table proceso.cortes_por_producto_{IDUNICO}
stored as parquet
as
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
from proceso.tmp_cortes_rangos_{IDUNICO} r;

compute stats proceso.cortes_por_producto_{IDUNICO};

-- --- 3. limpieza -------------------------------------------------------------
drop table if exists proceso.tmp_cortes_rangos_{IDUNICO} purge;
