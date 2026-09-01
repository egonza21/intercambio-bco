-- ============================================================================
-- CONSTRUCCIÓN: proceso.pd_por_modelo
-- ----------------------------------------------------------------------------
-- Distribución de las DOS PD, por segmento, serie y modelo, en bins fijos.
-- Alimenta el histograma de PD y el PSI.
--
-- NO depende de largo_calificaciones y no debe: la PD es un atributo del
-- CLIENTE, no del producto (CLAUDE.md, "La PD no es por producto"). El cross
-- join es contra 2 series, no contra 16 productos, y el filtro es
-- `pd IS NOT NULL`, no `grupo IS NOT NULL` -- la población correcta acá es la
-- que el modelo alcanzó a calificar, tenga o no grupo en algún producto.
--
-- El modelo se toma con un CASE que sigue el MISMO orden que el COALESCE de la
-- PD, para que ambos vengan de la misma columna.
--
-- Bins logarítmicos para probabilidad (20 por década) y lineales de 50 para
-- puntaje. Bordes FIJOS: es la condición para que el PSI signifique algo.
--
-- La escala sale de una LISTA EXPLÍCITA de modelos. Hay que actualizarla
-- cuando entre un modelo nuevo de puntaje; el síntoma de olvidarlo es un
-- histograma con bins absurdos, no un error. Ver CLAUDE.md, "Modelos y su
-- escala", y el chequeo 3 de la página de salud del dato.
--
-- SIN PARÁMETROS: toda la ventana disponible.
-- ============================================================================

drop table if exists proceso.pd_por_modelo purge;

create table proceso.pd_por_modelo
stored as parquet
as
with series as (
              select 1 as idx, 'general'  as serie_pd
    union all select 2,        'vivienda'
),

pd_cliente as (
  select
    c.ingestion_year,
    c.ingestion_month,
    c.segmento,
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
    p.ingestion_year,
    p.ingestion_month,
    p.segmento,
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
),

escalado as (
  select
    sp.ingestion_year,
    sp.ingestion_month,
    sp.segmento,
    sp.serie_pd,
    sp.modelo,
    sp.pd,
    case when sp.modelo in ('ADVANCE_1_1', 'ADVANCE_INCLUSION')
         then 'puntaje_0_999'
         else 'probabilidad_0_1' end as escala
  from series_pd sp
  where sp.pd is not null
),

binned as (
  select
    e.ingestion_year,
    e.ingestion_month,
    e.segmento,
    e.serie_pd,
    e.modelo,
    e.escala,
    e.pd,
    case when e.escala = 'puntaje_0_999'
         then least(cast(floor(e.pd / 50.0) as int), 19)
         else cast(floor(log10(greatest(e.pd, 0.000001)) * 20) as int)
    end as bin
  from escalado e
)

select
  b.ingestion_year,
  b.ingestion_month,
  b.ingestion_year * 12 + b.ingestion_month as idx_mes,
  b.segmento,
  b.serie_pd,
  b.modelo,
  b.escala,
  b.bin,
  case when b.escala = 'puntaje_0_999'
       then b.bin * 50.0
       else pow(10, b.bin / 20.0)
  end as bin_min,
  case when b.escala = 'puntaje_0_999'
       then (b.bin + 1) * 50.0
       else pow(10, (b.bin + 1) / 20.0)
  end as bin_max,
  count(*)   as clientes,
  sum(b.pd)  as pd_suma,
  min(b.pd)  as pd_min,
  max(b.pd)  as pd_max
from binned b
group by
  b.ingestion_year,
  b.ingestion_month,
  b.segmento,
  b.serie_pd,
  b.modelo,
  b.escala,
  b.bin;

compute stats proceso.pd_por_modelo;
