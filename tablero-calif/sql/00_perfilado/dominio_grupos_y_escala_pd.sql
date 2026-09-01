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
-- Lista cada valor de grupo que aparece por producto, con su conteo.
--
-- Resuelto 2026-08-25: el dominio NO es G1-G8 plano en todos los productos.
-- sufi_moto, sufi_cpe y sufi_con abren G7 y G8 en G7_B/G7_M/G7_A y
-- G8_B/G8_M/G8_A (severidad ascendente B < M < A); los demás productos sí
-- usan G1-G8 planos. Resuelto en sql/_fragmentos/cte_productos.sql con las
-- columnas grupo_base (apertura colapsada) y grupo_orden (severidad
-- numérica). Esta query se conserva como verificación: si aparece un valor
-- fuera de {G1..G8} y de las seis aperturas conocidas, hay que decidir
-- explícitamente qué hacer con él y revisar grupo_orden, porque su cálculo
-- aritmético asume ese formato.
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
-- Min, máximo y promedio de pd por producto.
--
-- Resuelto 2026-08-25: la escala NO es uniforme, y el eje que la determina
-- no es el producto sino el modelo. `ADVANCE_1_1` y `ADVANCE_INCLUSION` dejan
-- en `pd` el puntaje crudo (0 a 999) en vez de una probabilidad [0,1]; su
-- traducción a grupo sí llega normalizada a G1-G8 vía traductores. Por eso el
-- histograma de PD y el PSI deben segmentar por `modelo`, nunca mezclar
-- modelos de escala distinta en un mismo eje.
--
-- **Esta query es el control de la lista manual de modelos de puntaje.**
-- sql/10_agregados/pd_por_modelo.sql clasifica la escala con un IN contra esa
-- lista, y nada en la tabla marca la escala de un modelo. Correr este bloque
-- agrupando por modelo cuando cambie la vigencia de modelos: **si aparece un
-- modelo con pd_max > 1 que no esté en la lista, hay que agregarlo ahí**. El
-- síntoma de no hacerlo no es un error, es un histograma con bins absurdos.
-- Ver CLAUDE.md, "Modelos en escala de puntaje".
--
-- Para ver qué modelo trae qué escala hace falta agrupar por modelo, no solo
-- por producto: un mismo producto puede traer varias versiones de modelo. Si
-- se necesita ese corte, agregar `l.modelo` al select y al group by (implica
-- llevar el CASE de modelo al CTE, hoy omitido porque este bloque solo mira
-- pd).
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
