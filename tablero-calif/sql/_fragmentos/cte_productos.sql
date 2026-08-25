-- ============================================================================
-- Fragmento canónico: CTE de productos
-- ----------------------------------------------------------------------------
-- Impala no tiene stack() ni includes, así que este bloque se copia en cada
-- query que necesite despivotar la tabla ancha. ESTA ES LA COPIA DE
-- REFERENCIA: cualquier cambio en el mapeo idx -> producto se hace aquí
-- primero y luego se propaga.
--
-- El acoplamiento peligroso está en los CASE que acompañan a este CTE: el
-- orden de los WHEN tiene que coincidir con el idx de aquí. Un desalineo no
-- produce error, solo datos mal etiquetados.
--
-- La columna familia es una suposición a partir de los nombres de producto.
-- Confirmar con negocio antes de usarla en el tablero.
-- ============================================================================

with productos as (
              select 1  as idx, 'consumo'       as producto, 'consumo'   as familia
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

-- ----------------------------------------------------------------------------
-- CTE de unpivot que acompaña al anterior. El filtro de particiones va aquí,
-- antes del cross join, para que Impala pode particiones.
--
-- OJO: el filtro de nulos NO va en este CTE, va en la query que lo consume.
-- La razón es que el criterio correcto (pd IS NOT NULL vs grupo IS NOT NULL)
-- depende del resultado de sql/00_perfilado/nulos_pd_vs_grupo.sql, y la query
-- de cobertura necesita justamente las filas nulas.
-- ----------------------------------------------------------------------------

largo as (
  select
    c.num_doc,
    c.tipo_doc,
    c.ingestion_year,
    c.ingestion_month,
    c.segmento,
    p.producto,
    p.familia,
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
  from calificaciones c
  cross join productos p
  where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}
)

-- Uso: continuar con el SELECT final que consume `largo`, aplicando el filtro
-- de nulos que corresponda.