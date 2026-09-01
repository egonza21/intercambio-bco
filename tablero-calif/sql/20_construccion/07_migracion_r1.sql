-- ============================================================================
-- CONSTRUCCIÓN: proceso.migracion_r1_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Matriz de migración de grupo con rezago de 1 mes.
--
-- DEPENDE de proceso.largo_calificaciones_{IDUNICO}. Ver 00_orden.md.
--
-- El rezago NO se parametriza: se construyen DOS tablas, migracion_r1 y
-- migracion_r6. Son análisis distintos y NO encadenables -- las matrices
-- mensuales no se suman para obtener la semestral, porque un cliente que va
-- G3 -> G4 -> G3 aporta dos movimientos en las mensuales y cero en la
-- semestral. La mensual mide rotación; la semestral, desplazamiento neto.
--
-- Los primeros 1 mes de la tabla no tienen mes de origen, así que
-- simplemente no producen filas: el full outer join no encuentra pareja y esos
-- meses no aparecen como destino. Antes esto era un borde peligroso porque el
-- rango se pasaba por parámetro y un rango mal puesto llenaba de "entrada"
-- falsas; construyendo todo el histórico el problema desaparece solo.
--
-- LAS CATEGORÍAS
--   movimiento             tiene grupo en los dos meses. Es la matriz.
--   entrada                no estaba en la tabla en el mes origen.
--   ganancia_elegibilidad  estaba, pero sin grupo en ESE producto.
--   salida                 no está en la tabla en el mes destino.
--   perdida_elegibilidad   está, pero sin grupo en ESE producto.
-- Separar cambio de población de decisión del modelo exige cruzar contra la
-- base de clientes del mes: de ahí el CTE base_mes, que lee la tabla ancha.
--
-- DOS SEGMENTOS, no uno coalescido: un cliente que cambia de segmento no
-- cambió de riesgo, pero con una sola columna aparece como salida y entrada.
-- En `entrada` el segmento_anterior queda NULL; en `salida`, el actual.
--
-- SIN PARÁMETROS de fecha: toda la ventana disponible.
-- ============================================================================

drop table if exists proceso.migracion_r1_{IDUNICO} purge;

create table proceso.migracion_r1_{IDUNICO}
stored as parquet
as
with destino as (
  select
    l.num_doc, l.tipo_doc, l.segmento, l.producto, l.idx_mes, l.grupo_base
  from proceso.largo_calificaciones_{IDUNICO} l
),

origen as (
  select
    l.num_doc, l.tipo_doc, l.segmento, l.producto,
    l.idx_mes + 1 as idx_mes_destino,
    l.grupo_base
  from proceso.largo_calificaciones_{IDUNICO} l
),

base_mes as (
  select
    c.num_doc,
    c.tipo_doc,
    c.ingestion_year * 12 + c.ingestion_month as idx_mes
  from resultados_riesgos.maestro_calificaciones_pn c
),

par as (
  select
    coalesce(d.num_doc,  o.num_doc)          as num_doc,
    coalesce(d.tipo_doc, o.tipo_doc)         as tipo_doc,
    coalesce(d.producto, o.producto)         as producto,
    o.segmento                               as segmento_anterior,
    d.segmento                               as segmento_actual,
    coalesce(d.idx_mes,  o.idx_mes_destino)  as idx_mes_destino,
    o.grupo_base                             as grupo_base_origen,
    d.grupo_base                             as grupo_base_destino,
    case
      when d.num_doc is null then o.idx_mes_destino
      when o.num_doc is null then d.idx_mes - 1
    end                                      as idx_mes_presencia
  from destino d
  full outer join origen o
    on  d.num_doc  = o.num_doc
    and d.tipo_doc = o.tipo_doc
    and d.producto = o.producto
    and d.idx_mes  = o.idx_mes_destino
),

clasificado as (
  select
    p.producto,
    p.segmento_anterior,
    p.segmento_actual,
    p.idx_mes_destino,
    cast(floor((p.idx_mes_destino - 1) / 12) as smallint) as ingestion_year,
    p.grupo_base_origen,
    p.grupo_base_destino,
    case
      when p.grupo_base_origen is not null
       and p.grupo_base_destino is not null       then 'movimiento'
      when p.grupo_base_origen is null
       and b.num_doc is null                      then 'entrada'
      when p.grupo_base_origen is null            then 'ganancia_elegibilidad'
      when b.num_doc is null                      then 'salida'
      else                                             'perdida_elegibilidad'
    end as categoria
  from par p
  left join base_mes b
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
  c.categoria;

compute stats proceso.migracion_r1_{IDUNICO};
