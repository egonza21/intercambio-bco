-- ============================================================================
-- CONSTRUCCIÓN: proceso.migracion_r6_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Matriz de migración de grupo con rezago de 6 meses.
--
-- DEPENDE de proceso.largo_calificaciones_{IDUNICO}. Ver 00_orden.md.
--
-- ----------------------------------------------------------------------------
-- POR QUÉ ESTÁ PARTIDO EN TABLAS INTERMEDIAS
-- ----------------------------------------------------------------------------
-- La versión anterior era un solo CREATE TABLE AS con todo encadenado en CTEs,
-- y se cancelaba por memoria: Impala no materializa los CTEs, así que el
-- full outer join, el left join contra la base y la agregación final quedaban
-- todos en el mismo plan, con los datos intermedios en memoria.
--
-- Ahora cada paso pesado va a disco:
--
--   tmp_migracion_r6_origen     el lado origen, con el mes ya desplazado
--   tmp_migracion_r6_destino    el lado destino
--   tmp_migracion_r6_base       presencia del cliente por mes
--   tmp_migracion_r6_par        el resultado del full outer join
--
-- El `compute stats` de cada intermedia va ANTES del join que la usa. Eso es
-- buena parte de la ganancia: con estadísticas Impala sabe los tamaños y
-- elige la estrategia de join (broadcast contra particionado) en vez de
-- adivinar. Sin stats, un broadcast de la tabla equivocada es justamente lo
-- que revienta la memoria.
--
-- Las intermedias se BORRAN al final, cuando la tabla definitiva ya existe. Si
-- el script se interrumpe a la mitad pueden quedar huérfanas; los drop del
-- arranque las limpian en la corrida siguiente.
--
-- ----------------------------------------------------------------------------
-- {REZAGO}: mensual y semestral NO son encadenables
-- ----------------------------------------------------------------------------
-- Rezago 1 da la migración mensual; rezago 6, la semestral. Las mensuales NO
-- se suman para obtener la semestral: un cliente que va G3 -> G4 -> G3 aporta
-- dos movimientos en las mensuales y cero en la semestral. La mensual mide
-- rotación; la semestral, desplazamiento neto.
--
-- Los primeros 6 meses no tienen mes de origen, así que no producen
-- filas: el full outer join no encuentra pareja y esos meses no aparecen como
-- destino.
--
-- LAS CATEGORÍAS
--   movimiento             tiene grupo en los dos meses. Es la matriz.
--   entrada                no estaba en la tabla en el mes origen.
--   ganancia_elegibilidad  estaba, pero sin grupo en ESE producto.
--   salida                 no está en la tabla en el mes destino.
--   perdida_elegibilidad   está, pero sin grupo en ESE producto.
--
-- DOS SEGMENTOS y DOS MODELOS, no coalescidos: un cliente que cambia de
-- segmento no cambió de riesgo, y el par de modelos es lo que permite
-- distinguir reasignación de deriva. OJO con el tamaño: son cuatro columnas
-- más en el grano. MEDIR el conteo de filas tras la primera construcción.
-- ============================================================================

-- --- limpieza defensiva: intermedias de una corrida interrumpida ------------
drop table if exists proceso.tmp_migracion_r6_origen_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r6_destino_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r6_base_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r6_par_{IDUNICO} purge;

-- --- 1. lado destino --------------------------------------------------------
create table proceso.tmp_migracion_r6_destino_{IDUNICO}
stored as parquet
as
select
  l.num_doc, l.tipo_doc, l.segmento, l.producto, l.idx_mes,
  l.grupo_base, l.modelo
from proceso.largo_calificaciones_{IDUNICO} l;

compute stats proceso.tmp_migracion_r6_destino_{IDUNICO};

-- --- 2. lado origen, con el mes ya desplazado -------------------------------
create table proceso.tmp_migracion_r6_origen_{IDUNICO}
stored as parquet
as
select
  l.num_doc, l.tipo_doc, l.segmento, l.producto, l.modelo,
  l.idx_mes + 6 as idx_mes_destino,
  l.grupo_base
from proceso.largo_calificaciones_{IDUNICO} l;

compute stats proceso.tmp_migracion_r6_origen_{IDUNICO};

-- --- 3. presencia del cliente por mes ---------------------------------------
create table proceso.tmp_migracion_r6_base_{IDUNICO}
stored as parquet
as
select
  c.num_doc,
  c.tipo_doc,
  c.ingestion_year * 12 + c.ingestion_month as idx_mes
from resultados_riesgos.maestro_calificaciones_pn c;

compute stats proceso.tmp_migracion_r6_base_{IDUNICO};

-- --- 4. el full outer join, materializado -----------------------------------
create table proceso.tmp_migracion_r6_par_{IDUNICO}
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
    when o.num_doc is null then d.idx_mes - 6
  end                                      as idx_mes_presencia
from proceso.tmp_migracion_r6_destino_{IDUNICO} d
full outer join proceso.tmp_migracion_r6_origen_{IDUNICO} o
  on  d.num_doc  = o.num_doc
  and d.tipo_doc = o.tipo_doc
  and d.producto = o.producto
  and d.idx_mes  = o.idx_mes_destino;

compute stats proceso.tmp_migracion_r6_par_{IDUNICO};

-- --- 5. clasificación y agregado final --------------------------------------
drop table if exists proceso.migracion_r6_{IDUNICO} purge;

create table proceso.migracion_r6_{IDUNICO}
stored as parquet
as
with clasificado as (
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
  from proceso.tmp_migracion_r6_par_{IDUNICO} p
  left join proceso.tmp_migracion_r6_base_{IDUNICO} b
    on  b.num_doc  = p.num_doc
    and b.tipo_doc = p.tipo_doc
    and b.idx_mes  = p.idx_mes_presencia
)

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
from clasificado c
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

compute stats proceso.migracion_r6_{IDUNICO};

-- --- 6. las intermedias ya no hacen falta ------------------------------------
drop table if exists proceso.tmp_migracion_r6_origen_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r6_destino_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r6_base_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_r6_par_{IDUNICO} purge;
