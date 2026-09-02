-- ============================================================================
-- CONSTRUCCIÓN: proceso.migracion_pd_r1_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Matriz de migración de DECILES DE PD con rezago de 1 mes.
--
-- NO depende de largo_calificaciones: la PD es del cliente, no del producto,
-- así que el cross join es contra 2 series y no contra 16 productos.
--
-- ----------------------------------------------------------------------------
-- POR QUÉ ESTÁ PARTIDO EN TABLAS INTERMEDIAS
-- ----------------------------------------------------------------------------
-- Mismo motivo que la migración de grupo, más uno propio: el `ntile` obliga a
-- un sort completo por partición, y encadenarlo con el full outer join en el
-- mismo plan es lo que hace que Impala se quede sin memoria.
--
--   tmp_migracion_pd_r1_deciles  el ntile, materializado UNA vez
--   tmp_migracion_pd_r1_base     presencia del cliente por mes
--   tmp_migracion_pd_r1_par      el full outer join
--
-- Materializar los deciles tiene una ganancia extra: antes el CTE se
-- referenciaba dos veces (origen y destino) y, como Impala inlinea, el sort
-- corría DOS veces. Ahora corre una.
--
-- El `compute stats` de cada intermedia va antes del join que la usa.
-- Las intermedias se borran al final; los drop del arranque limpian las que
-- hayan quedado de una corrida interrumpida.
--
-- ----------------------------------------------------------------------------
-- DECILES POR PERÍODO, a diferencia de los bins fijos de pd_por_modelo. Acá la
-- pregunta es de reordenamiento del ranking, no de desplazamiento de la
-- distribución: una diagonal fuerte dice que el orden se mantuvo, NO que la PD
-- no se movió. Eso lo dice el PSI.
--
-- El ntile se particiona TAMBIÉN por modelo: ADVANCE_1_1 y ADVANCE_INCLUSION
-- entregan puntaje 0-999 y el resto probabilidad 0-1, así que rankearlos
-- juntos mandaría a esos clientes a los deciles altos por escala, no por
-- riesgo.
-- ============================================================================

drop table if exists proceso.tmp_migracion_pd_r1_deciles_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_pd_r1_base_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_pd_r1_par_{IDUNICO} purge;

-- --- 1. las dos PD del cliente y su decil, materializados --------------------
create table proceso.tmp_migracion_pd_r1_deciles_{IDUNICO}
stored as parquet
as
with series as (
              select 1 as idx, 'general'  as serie_pd
    union all select 2,        'vivienda'
),

pd_cliente as (
  select
    c.num_doc,
    c.tipo_doc,
    c.ingestion_year * 12 + c.ingestion_month as idx_mes,
    coalesce(c.pd_consumo,   c.pd_tdc,       c.pd_libranza,  c.pd_rota,
             c.pd_comercial, c.pd_micro,     c.pd_sobre,     c.pd_sufi_veh,
             c.pd_sufi_moto, c.pd_sufi_cpe,  c.pd_sufi_con,  c.pd_calm)
      as pd_general,
    case
      when c.pd_consumo   is not null then c.modelo_consumo
      when c.pd_tdc       is not null then c.modelo_tdc
      when c.pd_libranza  is not null then c.modelo_libranza
      when c.pd_rota      is not null then c.modelo_rota
      when c.pd_comercial is not null then c.modelo_comercial
      when c.pd_micro     is not null then c.modelo_micro
      when c.pd_sobre     is not null then c.modelo_sobre
      when c.pd_sufi_veh  is not null then c.modelo_sufi_veh
      when c.pd_sufi_moto is not null then c.modelo_sufi_moto
      when c.pd_sufi_cpe  is not null then c.modelo_sufi_cpe
      when c.pd_sufi_con  is not null then c.modelo_sufi_con
      when c.pd_calm      is not null then c.modelo_calm
    end as modelo_general,
    coalesce(c.pd_hip_vis, c.pd_hip_novis,
             c.pd_lea_hab_vis, c.pd_lea_hab_novis)
      as pd_vivienda,
    case
      when c.pd_hip_vis       is not null then c.modelo_hip_vis
      when c.pd_hip_novis     is not null then c.modelo_hip_novis
      when c.pd_lea_hab_vis   is not null then c.modelo_lea_hab_vis
      when c.pd_lea_hab_novis is not null then c.modelo_lea_hab_novis
    end as modelo_vivienda
  from resultados_riesgos.maestro_calificaciones_pn c
),

series_pd as (
  select
    p.num_doc,
    p.tipo_doc,
    p.idx_mes,
    s.serie_pd,
    case s.idx
      when 1 then p.pd_general
      when 2 then p.pd_vivienda
    end as pd,
    nullif(trim(case s.idx
      when 1 then p.modelo_general
      when 2 then p.modelo_vivienda
    end), '') as modelo
  from pd_cliente p
  cross join series s
)

select
  sp.num_doc,
  sp.tipo_doc,
  sp.idx_mes,
  sp.serie_pd,
  sp.modelo,
  ntile(10) over (
    partition by sp.serie_pd, sp.modelo, sp.idx_mes
    order by sp.pd
  ) as decil
from series_pd sp
where sp.pd is not null;

compute stats proceso.tmp_migracion_pd_r1_deciles_{IDUNICO};

-- --- 2. presencia del cliente por mes ---------------------------------------
create table proceso.tmp_migracion_pd_r1_base_{IDUNICO}
stored as parquet
as
select
  c.num_doc,
  c.tipo_doc,
  c.ingestion_year * 12 + c.ingestion_month as idx_mes
from resultados_riesgos.maestro_calificaciones_pn c;

compute stats proceso.tmp_migracion_pd_r1_base_{IDUNICO};

-- --- 3. el full outer join, materializado -----------------------------------
create table proceso.tmp_migracion_pd_r1_par_{IDUNICO}
stored as parquet
as
select
  coalesce(d.num_doc,  o.num_doc)              as num_doc,
  coalesce(d.tipo_doc, o.tipo_doc)             as tipo_doc,
  coalesce(d.serie_pd, o.serie_pd)             as serie_pd,
  coalesce(d.idx_mes,  o.idx_mes + 1)      as idx_mes_destino,
  o.modelo                                     as modelo_origen,
  d.modelo                                     as modelo_destino,
  o.decil                                      as decil_origen,
  d.decil                                      as decil_destino,
  case
    when d.num_doc is null then o.idx_mes + 1
    when o.num_doc is null then d.idx_mes - 1
  end                                          as idx_mes_presencia
from proceso.tmp_migracion_pd_r1_deciles_{IDUNICO} d
full outer join proceso.tmp_migracion_pd_r1_deciles_{IDUNICO} o
  on  d.num_doc  = o.num_doc
  and d.tipo_doc = o.tipo_doc
  and d.serie_pd = o.serie_pd
  and d.idx_mes  = o.idx_mes + 1;

compute stats proceso.tmp_migracion_pd_r1_par_{IDUNICO};

-- --- 4. clasificación y agregado final --------------------------------------
drop table if exists proceso.migracion_pd_r1_{IDUNICO} purge;

create table proceso.migracion_pd_r1_{IDUNICO}
stored as parquet
as
with clasificado as (
  select
    p.serie_pd,
    p.idx_mes_destino,
    cast(floor((p.idx_mes_destino - 1) / 12) as smallint) as ingestion_year,
    p.modelo_origen,
    p.modelo_destino,
    p.decil_origen,
    p.decil_destino,
    case
      when p.decil_origen is not null
       and p.decil_destino is not null       then 'movimiento'
      when p.decil_origen is null
       and b.num_doc is null                 then 'entrada'
      when p.decil_origen is null            then 'ganancia_pd'
      when b.num_doc is null                 then 'salida'
      else                                        'perdida_pd'
    end as categoria
  from proceso.tmp_migracion_pd_r1_par_{IDUNICO} p
  left join proceso.tmp_migracion_pd_r1_base_{IDUNICO} b
    on  b.num_doc  = p.num_doc
    and b.tipo_doc = p.tipo_doc
    and b.idx_mes  = p.idx_mes_presencia
)

select
  c.ingestion_year,
  cast(c.idx_mes_destino - 12 * c.ingestion_year as tinyint) as ingestion_month,
  c.idx_mes_destino as idx_mes,
  c.serie_pd,
  c.modelo_origen,
  c.modelo_destino,
  c.decil_origen,
  c.decil_destino,
  c.categoria,
  count(*) as clientes
from clasificado c
group by
  c.ingestion_year,
  c.idx_mes_destino,
  c.serie_pd,
  c.modelo_origen,
  c.modelo_destino,
  c.decil_origen,
  c.decil_destino,
  c.categoria;

compute stats proceso.migracion_pd_r1_{IDUNICO};

-- --- 5. las intermedias ya no hacen falta ------------------------------------
drop table if exists proceso.tmp_migracion_pd_r1_deciles_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_pd_r1_base_{IDUNICO} purge;
drop table if exists proceso.tmp_migracion_pd_r1_par_{IDUNICO} purge;
