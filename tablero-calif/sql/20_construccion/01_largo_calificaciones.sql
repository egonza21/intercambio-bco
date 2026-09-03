-- ============================================================================
-- CONSTRUCCIÓN: proceso.largo_calificaciones_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Materializa el unpivot. Es la tabla sobre la que se apoyan los agregados que
-- necesitan detalle por producto: el cross join contra los 16 productos se
-- paga UNA vez por construcción en vez de repetirse en cada agregado.
--
-- La consumen: 04, 06, 07 y 08. Tiene que existir antes que ellas.
--
-- Lleva `grupo IS NOT NULL`, así que NO sirve para medir cobertura: esa
-- necesita justamente las filas sin grupo y sale de la tabla ancha en 03.
--
-- El mapeo idx -> columna es el de sql/_fragmentos/cte_productos.sql. Los tres
-- bloques `case p.idx` tienen que estar alineados con esa copia; es lo que
-- valida sql/00_perfilado/validacion_mapeo.sql.
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

drop table if exists proceso.tmp_productos_{IDUNICO} purge;
drop table if exists proceso.tmp_largo_raw_{IDUNICO} purge;

-- --- 1. el mapeo idx -> producto, como tabla de 16 filas ---------------------
create table proceso.tmp_productos_{IDUNICO}
stored as parquet
as
              select 1  as idx, 'consumo' as producto, 'consumo' as familia_producto
    union all select 2,  'tdc',           'consumo'
    union all select 3,  'libranza',      'consumo'
    union all select 4,  'rotativo',      'consumo'
    union all select 5,  'hip_vis',       'vivienda'
    union all select 6,  'hip_novis',     'vivienda'
    union all select 7,  'lea_hab_vis',   'vivienda'
    union all select 8,  'lea_hab_novis', 'vivienda'
    union all select 9,  'comercial',     'comercial'
    union all select 10, 'micro',         'comercial'
    union all select 11, 'sobregiro',     'comercial'
    union all select 12, 'sufi_veh',      'sufi'
    union all select 13, 'sufi_moto',     'sufi'
    union all select 14, 'sufi_cpe',      'sufi'
    union all select 15, 'sufi_con',      'sufi'
    union all select 16, 'calm',          'consumo';

compute stats proceso.tmp_productos_{IDUNICO};

-- --- 2. el unpivot crudo ----------------------------------------------------
create table proceso.tmp_largo_raw_{IDUNICO}
stored as parquet
as
select
    c.num_doc,
    c.tipo_doc,
    c.ingestion_year,
    c.ingestion_month,
    c.segmento,
    p.producto,
    p.familia_producto,
    case p.idx
      when  1 then c.pd_consumo        when  2 then c.pd_tdc
      when  3 then c.pd_libranza       when  4 then c.pd_rota
      when  5 then c.pd_hip_vis        when  6 then c.pd_hip_novis
      when  7 then c.pd_lea_hab_vis    when  8 then c.pd_lea_hab_novis
      when  9 then c.pd_comercial      when 10 then c.pd_micro
      when 11 then c.pd_sobre          when 12 then c.pd_sufi_veh
      when 13 then c.pd_sufi_moto      when 14 then c.pd_sufi_cpe
      when 15 then c.pd_sufi_con       when 16 then c.pd_calm
    end as pd,
    case p.idx
      when  1 then c.g_consumo         when  2 then c.g_tdc
      when  3 then c.g_libranza        when  4 then c.g_rota
      when  5 then c.g_hip_vis         when  6 then c.g_hip_novis
      when  7 then c.g_lea_hab_vis     when  8 then c.g_lea_hab_novis
      when  9 then c.g_comercial       when 10 then c.g_micro
      when 11 then c.g_sobre           when 12 then c.g_sufi_veh
      when 13 then c.g_sufi_moto       when 14 then c.g_sufi_cpe
      when 15 then c.g_sufi_con        when 16 then c.g_calm
    end as grupo,
    case p.idx
      when  1 then c.modelo_consumo       when  2 then c.modelo_tdc
      when  3 then c.modelo_libranza      when  4 then c.modelo_rota
      when  5 then c.modelo_hip_vis       when  6 then c.modelo_hip_novis
      when  7 then c.modelo_lea_hab_vis   when  8 then c.modelo_lea_hab_novis
      when  9 then c.modelo_comercial     when 10 then c.modelo_micro
      when 11 then c.modelo_sobre         when 12 then c.modelo_sufi_veh
      when 13 then c.modelo_sufi_moto     when 14 then c.modelo_sufi_cpe
      when 15 then c.modelo_sufi_con      when 16 then c.modelo_calm
    end as modelo
  from resultados_riesgos.maestro_calificaciones_pn c
  cross join proceso.tmp_productos_{IDUNICO} p
  -- Salvaguarda contra ingestas parciales de principios de mes. Ver CLAUDE.md,
  -- "El filtro de ingestion_day". HOY NO DESCARTA NADA: los días observados van
  -- de 19 a 24. Está justamente para el día en que aparezca una carga a medias,
  -- y por eso queda escrito para qué sirve -- si no, dentro de seis meses
  -- alguien lo borra por parecer inútil.
  where c.ingestion_day >= 15;

compute stats proceso.tmp_largo_raw_{IDUNICO};

-- --- 3. tabla final ---------------------------------------------------------
drop table if exists proceso.largo_calificaciones_{IDUNICO} purge;

create table proceso.largo_calificaciones_{IDUNICO}
stored as parquet
as
select
  r.num_doc,
  r.tipo_doc,
  r.ingestion_year,
  r.ingestion_month,
  r.ingestion_year * 12 + r.ingestion_month as idx_mes,
  r.segmento,
  r.producto,
  r.familia_producto,
  r.pd,
  r.grupo,
  regexp_replace(r.grupo, '_[BMA]$', '') as grupo_base,
  nullif(trim(r.modelo), '') as modelo
from proceso.tmp_largo_raw_{IDUNICO} r
where r.grupo is not null;

compute stats proceso.largo_calificaciones_{IDUNICO};

-- --- 4. limpieza ------------------------------------------------------------
drop table if exists proceso.tmp_productos_{IDUNICO} purge;
drop table if exists proceso.tmp_largo_raw_{IDUNICO} purge;
