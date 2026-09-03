-- ============================================================================
-- CONSTRUCCIÓN: proceso.puente_base_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Descomposición de la base mes a mes: cuántos siguen, cuántos entraron y
-- cuántos salieron, por segmento. Alimenta la cascada de Evolución.
--
-- NO se puede sacar de proceso.migracion_*: esas tablas están al grano de
-- PRODUCTO, así que un cliente que entra aparece en cada producto para el que
-- califica y sumarlos cuenta de más. Entrada y salida son hechos del CLIENTE.
--
-- El segmento de una salida es el que tenía cuando estaba; el de una entrada,
-- el del mes en que aparece. De ahí el coalesce.
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

drop table if exists proceso.tmp_puente_mes_{IDUNICO} purge;
drop table if exists proceso.tmp_puente_par_{IDUNICO} purge;

-- --- 1. presencia del cliente por mes ----------------------------------------
create table proceso.tmp_puente_mes_{IDUNICO}
stored as parquet
as
select
    c.num_doc,
    c.tipo_doc,
    c.segmento,
    c.ingestion_year * 12 + c.ingestion_month as idx_mes
  from resultados_riesgos.maestro_calificaciones_pn c
  -- Salvaguarda contra ingestas parciales de principios de mes. Ver CLAUDE.md,
  -- "El filtro de ingestion_day". HOY NO DESCARTA NADA: los días observados van
  -- de 19 a 24. Está justamente para el día en que aparezca una carga a medias,
  -- y por eso queda escrito para qué sirve -- si no, dentro de seis meses
  -- alguien lo borra por parecer inútil.
  where c.ingestion_day >= 15;

compute stats proceso.tmp_puente_mes_{IDUNICO};

-- --- 2. cada cliente contra su mes anterior ----------------------------------
create table proceso.tmp_puente_par_{IDUNICO}
stored as parquet
as
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
    and a.idx_mes  = b.idx_mes + 1;

compute stats proceso.tmp_puente_par_{IDUNICO};

-- --- 3. tabla final ----------------------------------------------------------
drop table if exists proceso.puente_base_{IDUNICO} purge;

create table proceso.puente_base_{IDUNICO}
stored as parquet
as
select
  cast(floor((p.idx_mes - 1) / 12) as smallint) as ingestion_year,
  cast(p.idx_mes - 12 * cast(floor((p.idx_mes - 1) / 12) as smallint)
       as tinyint)                              as ingestion_month,
  p.idx_mes,
  p.segmento,
  p.categoria,
  count(*) as clientes
from proceso.tmp_puente_par_{IDUNICO} p
group by
  p.idx_mes,
  p.segmento,
  p.categoria;

compute stats proceso.puente_base_{IDUNICO};

-- --- 4. limpieza -------------------------------------------------------------
drop table if exists proceso.tmp_puente_mes_{IDUNICO} purge;
drop table if exists proceso.tmp_puente_par_{IDUNICO} purge;
