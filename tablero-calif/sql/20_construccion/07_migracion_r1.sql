-- ============================================================================
-- CONSTRUCCIÓN: proceso.migracion_r1_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Matriz de migración de grupo con rezago de 1 mes.
--
-- DEPENDE de proceso.largo_calificaciones_{IDUNICO}.
--
-- El rezago NO se parametriza: son dos tablas, r1 y r6. Son análisis distintos
-- y NO encadenables -- un cliente que va G3 -> G4 -> G3 aporta dos movimientos
-- en las mensuales y cero en la semestral. La mensual mide rotación; la
-- semestral, desplazamiento neto.
--
-- Los primeros 1 mes no tienen mes de origen, así que no producen filas.
--
-- CATEGORÍAS
--   movimiento             tiene grupo en los dos meses. Es la matriz.
--   entrada                no estaba en la tabla en el mes origen.
--   ganancia_elegibilidad  estaba, pero sin grupo en ESE producto.
--   salida                 no está en la tabla en el mes destino.
--   perdida_elegibilidad   está, pero sin grupo en ESE producto.
-- Separar población de decisión del modelo exige cruzar contra la base del
-- mes: de ahí tmp_migracion_r1_base.
--
-- DOS SEGMENTOS y DOS MODELOS, no coalescidos: un cliente que cambia de
-- segmento no cambió de riesgo, y el par de modelos permite distinguir
-- reasignación de deriva. OJO con el tamaño: cuatro columnas más en el grano.
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

drop table if exists proceso.tmp_migracion_r1_destino_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r1_origen_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r1_base_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r1_par_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r1_clasificado_{IDUNICO} purge;

-- --- 1. lado destino --------------------------------------------------------
create table proceso.tmp_migracion_r1_destino_{IDUNICO}
stored as parquet
as
select
    l.num_doc, l.tipo_doc, l.segmento, l.producto, l.idx_mes,
    l.grupo_base, l.modelo
  from proceso.largo_calificaciones_{IDUNICO} l;

compute stats proceso.tmp_migracion_r1_destino_{IDUNICO};

-- --- 2. lado origen, con el mes ya desplazado --------------------------------
create table proceso.tmp_migracion_r1_origen_{IDUNICO}
stored as parquet
as
select
    l.num_doc, l.tipo_doc, l.segmento, l.producto, l.modelo,
    l.idx_mes + 1 as idx_mes_destino,
    l.grupo_base
  from proceso.largo_calificaciones_{IDUNICO} l;

compute stats proceso.tmp_migracion_r1_origen_{IDUNICO};

-- --- 3. presencia del cliente por mes ----------------------------------------
create table proceso.tmp_migracion_r1_base_{IDUNICO}
stored as parquet
as
select
    c.num_doc,
    c.tipo_doc,
    c.ingestion_year * 12 + c.ingestion_month as idx_mes
  from resultados_riesgos.maestro_calificaciones_pn c
  -- Salvaguarda contra ingestas parciales de principios de mes. Ver CLAUDE.md,
  -- "El filtro de ingestion_day". HOY NO DESCARTA NADA: los días observados van
  -- de 19 a 24. Está justamente para el día en que aparezca una carga a medias,
  -- y por eso queda escrito para qué sirve -- si no, dentro de seis meses
  -- alguien lo borra por parecer inútil.
  where c.ingestion_day >= 15;

compute stats proceso.tmp_migracion_r1_base_{IDUNICO};

-- --- 4. el full outer join ---------------------------------------------------
create table proceso.tmp_migracion_r1_par_{IDUNICO}
stored as parquet
as
select
  coalesce(d.num_doc,  o.num_doc)          as num_doc,
  coalesce(d.tipo_doc, o.tipo_doc)         as tipo_doc,
  coalesce(d.producto, o.producto)         as producto,
  o.segmento                               as segmento_anterior,
  d.segmento                               as segmento_actual,
  coalesce(d.idx_mes,  o.idx_mes_destino)  as idx_mes_destino,
  o.grupo_base                             as grupo_base_origen,
  d.grupo_base                             as grupo_base_destino,
  o.modelo                                 as modelo_anterior,
  d.modelo                                 as modelo_actual,
  case
    when d.num_doc is null then o.idx_mes_destino
    when o.num_doc is null then d.idx_mes - 1
  end                                      as idx_mes_presencia
from proceso.tmp_migracion_r1_destino_{IDUNICO} d
full outer join proceso.tmp_migracion_r1_origen_{IDUNICO} o
  on  d.num_doc  = o.num_doc
  and d.tipo_doc = o.tipo_doc
  and d.producto = o.producto
  and d.idx_mes  = o.idx_mes_destino;

compute stats proceso.tmp_migracion_r1_par_{IDUNICO};

-- --- 5. clasificación --------------------------------------------------------
create table proceso.tmp_migracion_r1_clasificado_{IDUNICO}
stored as parquet
as
select
  p.producto,
  p.segmento_anterior,
  p.segmento_actual,
  p.idx_mes_destino,
  cast(floor((p.idx_mes_destino - 1) / 12) as smallint) as ingestion_year,
  p.grupo_base_origen,
  p.grupo_base_destino,
  p.modelo_anterior,
  p.modelo_actual,
  case
    when p.grupo_base_origen is not null
     and p.grupo_base_destino is not null       then 'movimiento'
    when p.grupo_base_origen is null
     and b.num_doc is null                      then 'entrada'
    when p.grupo_base_origen is null            then 'ganancia_elegibilidad'
    when b.num_doc is null                      then 'salida'
    else                                             'perdida_elegibilidad'
  end as categoria
from proceso.tmp_migracion_r1_par_{IDUNICO} p
left join proceso.tmp_migracion_r1_base_{IDUNICO} b
  on  b.num_doc  = p.num_doc
  and b.tipo_doc = p.tipo_doc
  and b.idx_mes  = p.idx_mes_presencia;

compute stats proceso.tmp_migracion_r1_clasificado_{IDUNICO};

-- --- 6. tabla final ----------------------------------------------------------
drop table if exists proceso.migracion_r1_{IDUNICO} purge;

create table proceso.migracion_r1_{IDUNICO}
stored as parquet
as
select
  c.ingestion_year,
  cast(c.idx_mes_destino - 12 * c.ingestion_year as tinyint) as ingestion_month,
  c.idx_mes_destino as idx_mes,
  c.segmento_anterior,
  c.segmento_actual,
  c.producto,
  c.grupo_base_origen,
  c.grupo_base_destino,
  c.modelo_anterior,
  c.modelo_actual,
  c.categoria,
  count(*) as clientes
from proceso.tmp_migracion_r1_clasificado_{IDUNICO} c
group by
  c.ingestion_year,
  c.idx_mes_destino,
  c.segmento_anterior,
  c.segmento_actual,
  c.producto,
  c.grupo_base_origen,
  c.grupo_base_destino,
  c.modelo_anterior,
  c.modelo_actual,
  c.categoria;

compute stats proceso.migracion_r1_{IDUNICO};

-- --- 7. limpieza -------------------------------------------------------------
drop table if exists proceso.tmp_migracion_r1_destino_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r1_origen_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r1_base_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r1_par_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r1_clasificado_{IDUNICO} purge;
