-- ============================================================================
-- CONSTRUCCIÓN: proceso.pd_por_modelo_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Distribución de las DOS PD, por segmento, serie y modelo, en bins fijos.
-- Alimenta el histograma de PD y el PSI de nivel 3.
--
-- NO depende de largo_calificaciones y no debe: la PD es un atributo del
-- CLIENTE, no del producto. El cross join es contra 2 series, no contra 16
-- productos, y el filtro es `pd IS NOT NULL`, no `grupo IS NOT NULL`.
--
-- El modelo se toma con un CASE que sigue el MISMO orden que el COALESCE de la
-- PD, para que ambos vengan de la misma columna.
--
-- Bins logarítmicos para probabilidad (20 por década) y lineales de 50 para
-- puntaje. Bordes FIJOS: condición para que el PSI signifique algo.
--
-- La escala sale de config/modelos.csv, que es la ÚNICA lista de modelos del
-- repo: antes estaba acá como un IN literal y otra vez en data.py, y las dos
-- se desincronizaban. La app convierte el CSV en tmp_modelos al construir
-- (marcador {MODELOS_DECLARADOS}, paso 0) y valida cada nombre antes de
-- interpolarlo: solo letras, números y guion bajo, como {IDUNICO}.
--
-- Un modelo que no esté en el CSV cae a probabilidad_0_1. Eso ya no pasa en
-- silencio: después del paso 4 la app verifica la escala contra el dato (ver
-- el marcador @verificacion) y, si un modelo trae PD mayor a 1 sin estar
-- declarado como puntaje, la construcción FALLA y borra la tabla. Ver
-- CLAUDE.md, "Modelos y su escala".
--
-- Este script NO se puede correr a mano con impala-shell tal cual está: los
-- marcadores {IDUNICO} y {MODELOS_DECLARADOS} los resuelve la app, y la
-- verificación también. Correrlo desde la página de Construcción.
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

drop table if exists proceso.tmp_modelos_{IDUNICO} purge;
drop table if exists proceso.tmp_pd_series_{IDUNICO} purge;
drop table if exists proceso.tmp_pd_cliente_{IDUNICO} purge;
drop table if exists proceso.tmp_pd_larga_{IDUNICO} purge;
drop table if exists proceso.tmp_pd_escalado_{IDUNICO} purge;
drop table if exists proceso.tmp_pd_binned_{IDUNICO} purge;

-- --- 1. las dos series -------------------------------------------------------
-- --- 0. modelos declarados, desde config/modelos.csv --------------------------
-- La app reemplaza el marcador por un `select ... union all select ...` con
-- una fila por modelo: (modelo, escala) con escala ya en el vocabulario de la
-- tabla, 'probabilidad_0_1' o 'puntaje_0_999'.
create table proceso.tmp_modelos_{IDUNICO}
stored as parquet
as
{MODELOS_DECLARADOS};

compute stats proceso.tmp_modelos_{IDUNICO};

create table proceso.tmp_pd_series_{IDUNICO}
stored as parquet
as
              select 1 as idx, 'general'  as serie_pd
    union all select 2,        'vivienda';

compute stats proceso.tmp_pd_series_{IDUNICO};

-- --- 2. las dos PD del cliente, cada una con SU modelo -----------------------
create table proceso.tmp_pd_cliente_{IDUNICO}
stored as parquet
as
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
  -- Salvaguarda contra ingestas parciales de principios de mes. Ver CLAUDE.md,
  -- "El filtro de ingestion_day". HOY NO DESCARTA NADA: los días observados van
  -- de 19 a 24. Está justamente para el día en que aparezca una carga a medias,
  -- y por eso queda escrito para qué sirve -- si no, dentro de seis meses
  -- alguien lo borra por parecer inútil.
  where c.ingestion_day >= 15;

compute stats proceso.tmp_pd_cliente_{IDUNICO};

-- --- 3. a formato largo: 2 filas por cliente ---------------------------------
create table proceso.tmp_pd_larga_{IDUNICO}
stored as parquet
as
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
  from proceso.tmp_pd_cliente_{IDUNICO} p
  cross join proceso.tmp_pd_series_{IDUNICO} s;

compute stats proceso.tmp_pd_larga_{IDUNICO};

-- --- 4. escala por modelo ----------------------------------------------------
create table proceso.tmp_pd_escalado_{IDUNICO}
stored as parquet
as
select
    l.ingestion_year,
    l.ingestion_month,
    l.segmento,
    l.serie_pd,
    l.modelo,
    l.pd,
    -- Un modelo sin declarar cae a probabilidad. La verificación de abajo es
    -- lo que impide que eso esconda un modelo de puntaje.
    coalesce(m.escala, 'probabilidad_0_1') as escala
  from proceso.tmp_pd_larga_{IDUNICO} l
  left join proceso.tmp_modelos_{IDUNICO} m
    on m.modelo = l.modelo
  where l.pd is not null;

compute stats proceso.tmp_pd_escalado_{IDUNICO};

-- @verificacion modelos
-- La app corre sql/20_construccion/verificaciones/modelos.sql sobre
-- tmp_pd_escalado y compara la PD de cada modelo contra lo declarado. Si un
-- modelo trae PD > 1 sin estar declarado como puntaje, ABORTA acá: ejecuta
-- todos los drop de este script, incluida la tabla final, y no construye nada.
-- Es mejor no tener la tabla que tenerla con los bins mal.

-- --- 5. bin de cada fila -----------------------------------------------------
create table proceso.tmp_pd_binned_{IDUNICO}
stored as parquet
as
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
  from proceso.tmp_pd_escalado_{IDUNICO} e;

compute stats proceso.tmp_pd_binned_{IDUNICO};

-- --- 6. tabla final ----------------------------------------------------------
drop table if exists proceso.pd_por_modelo_{IDUNICO} purge;

create table proceso.pd_por_modelo_{IDUNICO}
stored as parquet
as
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
from proceso.tmp_pd_binned_{IDUNICO} b
group by
  b.ingestion_year,
  b.ingestion_month,
  b.segmento,
  b.serie_pd,
  b.modelo,
  b.escala,
  b.bin;

compute stats proceso.pd_por_modelo_{IDUNICO};

-- --- 7. limpieza -------------------------------------------------------------
drop table if exists proceso.tmp_modelos_{IDUNICO} purge;
drop table if exists proceso.tmp_pd_series_{IDUNICO} purge;
drop table if exists proceso.tmp_pd_cliente_{IDUNICO} purge;
drop table if exists proceso.tmp_pd_larga_{IDUNICO} purge;
drop table if exists proceso.tmp_pd_escalado_{IDUNICO} purge;
drop table if exists proceso.tmp_pd_binned_{IDUNICO} purge;
