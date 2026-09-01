-- ============================================================================
-- Perfilado: validación del mapeo idx -> producto del unpivot
-- ----------------------------------------------------------------------------
-- Compara, para UN mes, los 16 `count(g_*)` de la tabla ancha contra el
-- conteo por producto en la tabla larga con `grupo IS NOT NULL`. Produce 16
-- filas con `conteo_ancho`, `conteo_largo` y `diferencia`.
--
-- **Todas las diferencias deben dar 0.** Cualquier fila distinta de 0 señala
-- un CASE desalineado en el unpivot.
--
-- Parámetros:
--   {DESDE}, {HASTA} -- rango de meses, en ingestion_year*12+ingestion_month
--
-- Se parametriza por rango como el resto del repo, pero OJO: el lado ancho
-- son 16 agregados, uno por rama del UNION ALL, así que el costo se
-- multiplica por la cantidad de meses del rango. Correrla sobre UN mes
-- (desde = hasta) salvo que haga falta explícitamente cubrir más.
--
-- ----------------------------------------------------------------------------
-- Por qué esta query existe
-- ----------------------------------------------------------------------------
-- Un `CASE ... WHEN` desalineado en el unpivot NO produce error: la query
-- corre, devuelve el número de filas correcto, y simplemente etiqueta los
-- datos con el producto equivocado. Es el punto más frágil del repo
-- (CLAUDE.md, "Mapeo idx -> producto"). Contar por ambos caminos y comparar
-- es la única forma de atraparlo.
--
-- Estado al 2026-08-25: `consumo` validado a mano contra la tabla ancha
-- (15.118.320 en 202608, cuadre exacto). Faltan los otros 15, que es lo que
-- automatiza este archivo.
--
-- ----------------------------------------------------------------------------
-- El lado ancho NO usa idx ni CASE -- ese es todo el punto
-- ----------------------------------------------------------------------------
-- `conteos_ancho` es un UNION ALL de 16 ramas, cada una con el nombre del
-- producto escrito LITERALMENTE al lado de su columna:
--
--     select 'rotativo', count(c.g_rota) ...
--
-- No hay posición, ni índice, ni CASE. Por eso el desalineo del fragmento
-- canónico no se puede replicar aquí: no existe nada que replicar. Una
-- versión anterior de este archivo usaba un segundo `case p.idx`, y eso la
-- hacía validarse contra sí misma -- si el error se copiaba a los dos lados,
-- los dos conteos quedaban mal igual y la diferencia daba 0.
--
-- **No introducir un CASE por idx en este archivo bajo ningún concepto**,
-- aunque parezca que ahorra líneas. Las 48 líneas repetitivas son el
-- mecanismo, no un descuido.
--
-- Los dos lugares donde el nombre del producto NO coincide con el sufijo de
-- la columna son `rotativo` -> `g_rota` y `sobregiro` -> `g_sobre`. Son los
-- candidatos más probables a un desalineo silencioso.
--
-- ----------------------------------------------------------------------------
-- Costo
-- ----------------------------------------------------------------------------
-- El precio de la independencia son 16 agregados sobre el mismo mes, uno por
-- rama del UNION ALL. Cada uno lee UNA sola columna, así que sobre Parquet
-- son 16 lecturas de ~1/48 de los datos, no 16 lecturas completas. El lado
-- largo hace su propia pasada con el unpivot. Sobre un mes es barato;
-- correrla sobre la ventana entera no tendría sentido, por eso conviene desde = hasta.
--
-- El CTE `largo` de este archivo no calcula `grupo_base` ni `grupo_orden`:
-- no se usan aquí y serían un regexp_replace sobre las expansiones del cross
-- join para nada. Los tres bloques `case p.idx` sí son idénticos al
-- fragmento canónico, que es lo que esta query valida.
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
),

conteo_largo as (
  select
    l.producto,
    count(*) as conteo_largo
  from largo l
  where l.grupo is not null
  group by l.producto
),

-- ----------------------------------------------------------------------------
-- Lado ancho. Nombre literal junto a su columna, sin idx y sin CASE.
-- `count(columna)` ignora nulos.
-- ----------------------------------------------------------------------------

conteos_ancho as (
              select 'consumo' as producto, count(c.g_consumo) as conteo_ancho
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'tdc', count(c.g_tdc)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'libranza', count(c.g_libranza)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'rotativo', count(c.g_rota)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'hip_vis', count(c.g_hip_vis)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'hip_novis', count(c.g_hip_novis)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'lea_hab_vis', count(c.g_lea_hab_vis)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'lea_hab_novis', count(c.g_lea_hab_novis)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'comercial', count(c.g_comercial)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'micro', count(c.g_micro)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'sobregiro', count(c.g_sobre)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'sufi_veh', count(c.g_sufi_veh)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'sufi_moto', count(c.g_sufi_moto)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'sufi_cpe', count(c.g_sufi_cpe)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'sufi_con', count(c.g_sufi_con)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}

    union all select 'calm', count(c.g_calm)
              from resultados_riesgos.maestro_calificaciones_pn c
              where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}
)

select
  a.producto,
  a.conteo_ancho,
  coalesce(l.conteo_largo, 0) as conteo_largo,
  a.conteo_ancho - coalesce(l.conteo_largo, 0) as diferencia
from conteos_ancho a
left join conteo_largo l
  on a.producto = l.producto
order by a.producto;
