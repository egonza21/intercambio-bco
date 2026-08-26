-- ============================================================================
-- Agregado: distribución de clientes por grupo de riesgo
-- ----------------------------------------------------------------------------
-- Produce una fila por
--   ingestion_year + ingestion_month + segmento + producto + grupo + modelo
-- con el conteo de clientes y los estadísticos de PD de ese cruce. Alimenta
-- los visuales de composición (barra apilada 100% de grupo por producto),
-- el heatmap segmento x grupo y la PD promedio ponderada.
--
-- Parámetros:
--   {DESDE}, {HASTA} -- rango de meses, en ingestion_year*12+ingestion_month
--
-- ----------------------------------------------------------------------------
-- Qué NO lleva, y por qué
-- ----------------------------------------------------------------------------
-- - `grupo_base` y `grupo_orden`: van en una dim_grupo que se arma aparte en
--   Power Query (ver powerbi/notas_modelo.md). Este agregado lleva `grupo`
--   como llave y nada más; las dos derivadas se resuelven en el modelo, no
--   por fila del hecho.
-- - `familia_producto`: está determinada por `producto`, así que vive en la
--   dimensión de producto. Repetirla aquí solo engorda el hecho.
--
-- El CTE `largo` sí sigue calculando `grupo_base` y `grupo_orden` porque esta
-- copia del fragmento canónico se mantiene textualmente idéntica a
-- sql/_fragmentos/cte_productos.sql -- así un diff entre las dos delata
-- cualquier desalineo del mapeo. El SELECT final no las referencia, y como
-- Impala inlinea los CTEs y poda columnas no usadas, no deberían costar
-- nada. Si el perfilado de esta query muestra lo contrario en el plan
-- (regexp_replace evaluándose sobre las ~240 MM de filas del cross join),
-- borrarlas de ESTA copia es seguro y es lo primero que hay que probar.
--
-- ----------------------------------------------------------------------------
-- Cómo leer las métricas
-- ----------------------------------------------------------------------------
-- - `clientes` es `count(*)`, no un COUNT(DISTINCT). Es válido porque el
--   grano de `largo` es cliente x mes x producto: para un
--   num_doc + tipo_doc + mes + producto hay exactamente una fila, y
--   segmento, grupo y modelo quedan determinados por ella. Esto DEPENDE de
--   que la tabla ancha traiga una sola fila por cliente + mes (ver CLAUDE.md,
--   "La deduplicación por ingestion_day NO se hace en SQL"). Si esa premisa
--   se rompiera, este conteo duplica en silencio.
-- - `clientes_con_pd` es `count(l.pd)`, que ignora nulos. NO es redundante
--   con `clientes`: hay un producto con 726 casos de pd nula y grupo
--   poblado, y esas filas entran al agregado (el filtro es por grupo). La
--   PD promedio ponderada es `pd_suma / clientes_con_pd`; dividir por
--   `clientes` da un promedio sesgado hacia abajo en ese producto.
-- - `pd_suma`, `pd_min` y `pd_max` son comparables SOLO dentro de un mismo
--   `modelo`. El modelo "advanced" deja en pd el puntaje crudo (0 a 999) en
--   vez de una probabilidad [0,1]. Como `modelo` está en el grano, cada fila
--   es internamente consistente, pero sumar `pd_suma` entre modelos de
--   escala distinta en Power BI produce un número sin significado. Ver
--   CLAUDE.md, "pd no es comparable entre modelos".
--
-- Sin ORDER BY a propósito: Power BI importa y ordena en el modelo, y un
-- sort distribuido sobre el resultado sería trabajo puro de más.
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
  where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}
),

largo as (
  select
    r.num_doc,
    r.tipo_doc,
    r.ingestion_year,
    r.ingestion_month,
    r.segmento,
    r.producto,
    r.familia_producto,
    r.pd,
    r.grupo,
    regexp_replace(r.grupo, '_[BMA]$', '') as grupo_base,
    cast(substr(r.grupo, 2, 1) as int) * 10
      + case substr(r.grupo, 4, 1)
          when 'B' then 1
          when 'M' then 2
          when 'A' then 3
          else 0
        end as grupo_orden,
    r.modelo
  from largo_raw r
)

select
  l.ingestion_year,
  l.ingestion_month,
  l.segmento,
  l.producto,
  l.grupo,
  l.modelo,
  count(*)       as clientes,
  count(l.pd)    as clientes_con_pd,
  sum(l.pd)      as pd_suma,
  min(l.pd)      as pd_min,
  max(l.pd)      as pd_max
from largo l
where l.grupo is not null
group by
  l.ingestion_year,
  l.ingestion_month,
  l.segmento,
  l.producto,
  l.grupo,
  l.modelo;
