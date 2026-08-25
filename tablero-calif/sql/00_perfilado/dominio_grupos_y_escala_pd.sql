-- ============================================================================
-- Perfilado: dominio de los grupos de riesgo y escala de la PD entre
-- productos
-- ----------------------------------------------------------------------------
-- Pendientes 4 y 5 de CLAUDE.md. Van en el mismo archivo porque comparten el
-- unpivot, pero son dos SELECT independientes (grados de agregación
-- distintos: el primero por producto + grupo, el segundo solo por producto),
-- así que se ejecutan por separado, no como una sola consulta.
--
-- Usa el mismo mapeo idx -> producto de sql/_fragmentos/cte_productos.sql,
-- copiado aquí porque Impala no soporta includes entre archivos. Cualquier
-- cambio en el mapeo canónico debe propagarse también a este archivo. El
-- filtro de partición va antes del cross join para que Impala pode
-- particiones.
--
-- Parámetros (los dos SELECT usan el mismo rango):
--   {DESDE}, {HASTA} -- rango de meses, en ingestion_year*12+ingestion_month
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Dominio de `grupo` (pendiente 4)
-- ----------------------------------------------------------------------------
-- Lista cada valor de grupo que aparece por producto, con su conteo. El
-- dominio esperado es G1-G8; cualquier otro valor no nulo (fuera de rango,
-- o los residuos de nulos-como-cadena que resuelve
-- sql/00_perfilado/nulos_pd_vs_grupo.sql) necesita una decisión explícita:
-- categoría propia o descarte. Afecta todos los porcentajes del tablero.
-- ----------------------------------------------------------------------------

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
      when  1 then c.g_consumo         when  2 then c.g_tdc
      when  3 then c.g_libranza        when  4 then c.g_rota
      when  5 then c.g_hip_vis         when  6 then c.g_hip_novis
      when  7 then c.g_lea_hab_vis     when  8 then c.g_lea_hab_novis
      when  9 then c.g_comercial       when 10 then c.g_micro
      when 11 then c.g_sobre           when 12 then c.g_sufi_veh
      when 13 then c.g_sufi_moto       when 14 then c.g_sufi_cpe
      when 15 then c.g_sufi_con        when 16 then c.g_calm
    end as grupo
  from resultados_riesgos.maestro_calificaciones_pn c
  cross join productos p
  where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}
)

select
  l.producto,
  l.grupo,
  count(*) as filas
from largo l
where l.grupo is not null
group by l.producto, l.grupo
order by l.producto, l.grupo;

-- ----------------------------------------------------------------------------
-- 2. Escala de `pd` por producto (pendiente 5)
-- ----------------------------------------------------------------------------
-- Min, máximo y promedio de pd por producto. Si todos los productos quedan
-- entre 0 y 1, la escala es consistente. Si algún producto muestra máximos
-- cercanos a 100 (o mínimos negativos, u otro rango que no sea [0,1]), los
-- bins del histograma de PD y el cálculo de PSI necesitan normalizar esa
-- columna antes de compararla con las demás.
-- ----------------------------------------------------------------------------

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
    end as pd
  from resultados_riesgos.maestro_calificaciones_pn c
  cross join productos p
  where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}
)

select
  l.producto,
  min(l.pd) as pd_min,
  max(l.pd) as pd_max,
  avg(l.pd) as pd_promedio
from largo l
where l.pd is not null
group by l.producto
order by l.producto;
