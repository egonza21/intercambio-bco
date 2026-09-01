-- ============================================================================
-- CONSTRUCCIÓN: proceso.largo_calificaciones
-- ----------------------------------------------------------------------------
-- Materializa el unpivot. Es la tabla intermedia sobre la que se apoyan los
-- agregados que necesitan el detalle por producto, y la razón principal por la
-- que vale la pena tener permisos de escritura: el cross join contra los 16
-- productos se paga UNA vez por construcción en vez de repetirse en cada
-- agregado.
--
-- La consumen: 04_distribucion_grupo, 06_cortes_por_producto,
-- 07_migracion_r1 y 08_migracion_r6. Tiene que existir antes que ellas.
-- Ver 00_orden.md.
--
-- SIN PARÁMETROS: construye toda la ventana disponible. El filtro de meses lo
-- hace la app en pandas, sobre el resultado ya cargado en memoria.
--
-- ----------------------------------------------------------------------------
-- Qué lleva y qué no
-- ----------------------------------------------------------------------------
-- Lleva el filtro `grupo IS NOT NULL`: es el criterio estándar de "el cliente
-- califica en este producto" (CLAUDE.md, "Filtro de nulos estándar"). Eso saca
-- del orden de 240 MM de filas por mes a las que efectivamente tienen
-- calificación, que es de lo que se puede hacer una tabla.
--
-- OJO: por eso mismo esta tabla NO sirve para medir cobertura. La cobertura
-- necesita justamente las filas sin grupo, y se calcula sobre la tabla ancha
-- en 03_cobertura_producto.
--
-- Lleva `grupo_base` porque la matriz de migración lo usa como eje y conviene
-- calcularlo una vez. NO lleva `grupo_orden`: es presentacional, lo reconstruye
-- la app desde theme.DIM_GRUPO.
--
-- Lleva `idx_mes` ya calculado: la migración se une contra idx_mes - rezago y
-- así el join no repite la aritmética en cada fila.
--
-- El mapeo idx -> columna es el de sql/_fragmentos/cte_productos.sql. Los tres
-- bloques `case p.idx` tienen que estar alineados con esa copia; es lo que
-- valida sql/00_perfilado/validacion_mapeo.sql.
-- ============================================================================

drop table if exists proceso.largo_calificaciones purge;

create table proceso.largo_calificaciones
stored as parquet
as
with productos as (
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
    union all select 16, 'calm',          'consumo'
),

largo_raw as (
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
  cross join productos p
)

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
from largo_raw r
where r.grupo is not null;

-- Sin estadísticas, Impala elige planes de join malos. Se nota sobre todo en
-- la migración, que cruza esta tabla contra sí misma.
compute stats proceso.largo_calificaciones;
