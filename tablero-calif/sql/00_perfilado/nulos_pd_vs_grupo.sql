-- ============================================================================
-- Perfilado: ¿coincide pd nulo con grupo nulo? ¿hay nulos representados como
-- cadena?
-- ----------------------------------------------------------------------------
-- Pendientes 2 y 3 de CLAUDE.md, sobre la misma tabla larga:
--
--   1. Si `pd_nulo_grupo_no_nulo` o `pd_no_nulo_grupo_nulo` salen distintos de
--      cero para algún producto, el criterio de filtro en el resto de las
--      queries cambia de `pd IS NOT NULL` a `grupo IS NOT NULL`, que es lo
--      que manda para el tablero (CLAUDE.md, "Decisiones ya tomadas").
--   2. Si `grupo_cadena_vacia`, `grupo_valor_na`, `modelo_cadena_vacia` o
--      `modelo_valor_na` salen distintos de cero, hay valores tipo 'NA', ''
--      o 'SIN CALIFICACION' que un IS NULL no atrapa y que hay que sumar
--      explícitamente al filtro de nulos.
--
-- Usa el mismo mapeo idx -> producto de sql/_fragmentos/cte_productos.sql,
-- copiado aquí porque Impala no soporta includes entre archivos. Cualquier
-- cambio en el mapeo canónico debe propagarse también a este archivo. El
-- filtro de partición va antes del cross join para que Impala pode
-- particiones.
--
-- Parámetros:
--   {DESDE}, {HASTA} -- rango de meses, en ingestion_year*12+ingestion_month
-- ============================================================================

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

largo as (
  select
    p.producto,
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
  where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}
)

select
  l.producto,
  count(*) as filas_totales,
  sum(case when l.pd is null then 1 else 0 end) as pd_nulo,
  sum(case when l.grupo is null then 1 else 0 end) as grupo_nulo,
  sum(case when l.pd is null and l.grupo is not null then 1 else 0 end)
    as pd_nulo_grupo_no_nulo,
  sum(case when l.pd is not null and l.grupo is null then 1 else 0 end)
    as pd_no_nulo_grupo_nulo,
  sum(case when l.grupo = '' then 1 else 0 end) as grupo_cadena_vacia,
  sum(case when upper(trim(l.grupo)) in ('NA', 'SIN CALIFICACION') then 1 else 0 end)
    as grupo_valor_na,
  sum(case when l.modelo = '' then 1 else 0 end) as modelo_cadena_vacia,
  sum(case when upper(trim(l.modelo)) in ('NA', 'SIN CALIFICACION') then 1 else 0 end)
    as modelo_valor_na
from largo l
group by l.producto
order by l.producto;
