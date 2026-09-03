-- ============================================================================
-- CONSTRUCCIÓN: proceso.puente_base_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Descomposición de la base de clientes mes a mes: cuántos siguen, cuántos
-- entraron y cuántos salieron, por segmento. Alimenta la cascada de la página
-- de Evolución.
--
-- Sabemos que la base cae 9% en la ventana, pero no POR QUÉ. La cascada lo
-- separa: si la caída viene de que se van clientes, se ve en `salida`.
--
-- NO se puede sacar de proceso.migracion_*: esas tablas están al grano de
-- PRODUCTO, así que un cliente que entra aparece en cada producto para el que
-- califica y sumarlos cuenta de más. La entrada y la salida son hechos del
-- CLIENTE, así que salen de la tabla ancha, que trae una fila por cliente y
-- mes.
--
-- El segmento de una salida es el que tenía en el mes en que estaba; el de una
-- entrada, el del mes en que aparece. Por eso el coalesce: cada categoría se
-- atribuye al segmento donde el movimiento es observable.
--
-- SIN PARÁMETROS: toda la ventana disponible.
-- ============================================================================

drop table if exists proceso.tmp_puente_mes_{IDUNICO} purge;

create table proceso.tmp_puente_mes_{IDUNICO}
stored as parquet
as
select
  c.num_doc,
  c.tipo_doc,
  c.segmento,
  c.ingestion_year * 12 + c.ingestion_month as idx_mes
from resultados_riesgos.maestro_calificaciones_pn c;

compute stats proceso.tmp_puente_mes_{IDUNICO};

drop table if exists proceso.puente_base_{IDUNICO} purge;

create table proceso.puente_base_{IDUNICO}
stored as parquet
as
with par as (
  select
    coalesce(a.idx_mes, b.idx_mes + 1)   as idx_mes,
    coalesce(a.segmento, b.segmento)     as segmento,
    case
      when b.num_doc is null then 'entrada'
      when a.num_doc is null then 'salida'
      else 'permanece'
    end                                  as categoria
  from proceso.tmp_puente_mes_{IDUNICO} a
  full outer join proceso.tmp_puente_mes_{IDUNICO} b
    on  a.num_doc  = b.num_doc
    and a.tipo_doc = b.tipo_doc
    and a.idx_mes  = b.idx_mes + 1
)

select
  cast(floor((p.idx_mes - 1) / 12) as smallint) as ingestion_year,
  cast(p.idx_mes - 12 * cast(floor((p.idx_mes - 1) / 12) as smallint)
       as tinyint)                              as ingestion_month,
  p.idx_mes,
  p.segmento,
  p.categoria,
  count(*) as clientes
from par p
group by
  p.idx_mes,
  p.segmento,
  p.categoria;

compute stats proceso.puente_base_{IDUNICO};

drop table if exists proceso.tmp_puente_mes_{IDUNICO} purge;
