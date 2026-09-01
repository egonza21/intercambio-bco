-- ============================================================================
-- Fragmento canónico: CTE de productos
-- ----------------------------------------------------------------------------
-- Impala no tiene stack() ni includes, así que este bloque se copia en cada
-- query que necesite despivotar resultados_riesgos.maestro_calificaciones_pn.
-- ESTA ES LA COPIA DE REFERENCIA: cualquier cambio en el mapeo idx -> producto
-- se hace aquí primero y luego se propaga a los demás archivos.
--
-- El acoplamiento peligroso está en los CASE que acompañan a este CTE: el
-- orden de los WHEN tiene que coincidir con el idx de aquí. Un desalineo no
-- produce error, solo datos mal etiquetados. Por eso el unpivot va partido en
-- dos CTEs: `largo_raw` escribe el mapeo idx -> columna UNA sola vez por cada
-- una de pd, grupo y modelo, y `largo` deriva de ahí las columnas calculadas.
-- Impala no permite referenciar un alias del mismo SELECT, y repetir el CASE
-- para derivar una columna de otra multiplicaría el punto frágil del repo.
-- Si alguna vez hay que tocar el mapeo: son tres bloques CASE, ni uno más.
--
-- ----------------------------------------------------------------------------
-- Qué tiene que ser idéntico en las copias, y qué no
-- ----------------------------------------------------------------------------
-- **Idéntico: los tres bloques `case p.idx` de `largo_raw`.** Es lo único que
-- tiene que estar alineado entre copias, y lo que valida
-- sql/00_perfilado/validacion_mapeo.sql.
--
-- **NO idéntico: el CTE `largo`.** Cada consumidor se queda solo con las
-- columnas derivadas que usa, y las que no usa las omite:
--
--   distribucion_grupo.sql   no lleva `largo`: no usa ninguna derivada
--   cortes_por_producto.sql  no lleva `largo`: ordena por pd_min
--   validacion_mapeo.sql     no lleva `largo`: solo necesita grupo
--   migracion.sql            solo `grupo_base`, que es el eje de la matriz
--
-- `regexp_replace` y la aritmética de `grupo_orden` corren sobre las ~240 MM
-- de filas que produce el cross join cada mes. Dejarlas calculadas "por
-- simetría con el fragmento" cuando nadie las selecciona es trabajo puro de
-- más: no dar por sentado que el planner las poda.
--
-- El filtro de partición también cambia donde hace falta: migracion.sql lo
-- amplía {REZAGO} meses hacia atrás, y validacion_mapeo.sql usa un solo mes.
--
-- producto          = detalle individual, 16 valores.
-- familia_producto  = agrupación gruesa, 4 valores. Forma jerarquía con
--                     producto en el tablero (drill down).
--                     PROPUESTA, pendiente de confirmar con la clasificación
--                     oficial del banco (pendiente 6, abierto).
--
-- Hallazgos del perfilado incorporados aquí (verificados 2026-08-25, ver
-- CLAUDE.md secciones "Decisiones ya tomadas" y "Pendientes por resolver"):
--
--   - DEDUPLICACIÓN: no hace falta. Un mes puntual llegó con dos ingestiones
--     totales (reproceso controlado, una de ellas un ensayo); fue un caso
--     único, ya corregido a mano borrando la ingestión del ensayo, y no se
--     va a repetir. El código asume una fila por num_doc + tipo_doc + mes y
--     no lleva row_number().
--   - GRUPO_BASE / GRUPO_ORDEN: sufi_moto, sufi_cpe y sufi_con abren G7 y G8
--     en G7_B/G7_M/G7_A y G8_B/G8_M/G8_A (severidad ascendente: B mejor, M
--     intermedio, A peor). Los demás productos usan G1-G8 planos. El CTE
--     expone tres vistas de lo mismo:
--       grupo        valor crudo, con la apertura donde exista. Es el que
--                    usa el visual de composición.
--       grupo_base   la apertura colapsada a G7/G8 planos, para que la
--                    matriz de migración 8x8 y las comparaciones
--                    cross-producto usen una escala común de 8 categorías.
--       grupo_orden  entero de severidad ascendente, para ordenar `grupo`
--                    en Power BI ("Ordenar por columna"). Sin él Power BI
--                    ordena alfabéticamente y deja G7_A, G7_B, G7_M: el peor
--                    grupo primero y el intermedio al final, lo que rompe el
--                    apilado de las barras y desalinea el eje de la matriz
--                    de migración (la diagonal deja de ser estabilidad y el
--                    deterioro neto sale mal calculado).
--   - PD: el modelo "advanced" devuelve el puntaje crudo en `pd` (0 a 999,
--     no 0 a 1); la traducción a `grupo`/`grupo_base` sí llega normalizada
--     a G1-G8 vía tablas traductoras externas al alcance de este fragmento.
--     `pd` NO es comparable entre productos ni entre modelos dentro del
--     mismo producto: cualquier histograma o PSI sobre `pd` debe segmentar
--     por `modelo`, no asumir escala [0,1] uniforme.
--   - NULOS: el filtro base para "el cliente califica en este producto" es
--     `grupo IS NOT NULL`, no `pd IS NOT NULL`. Un producto tiene 726 casos
--     con pd nula y grupo poblado; en el resto de los casos ambas
--     coinciden. Los nulos-como-cadena ('NA', '', 'SIN CALIFICACION') dieron
--     0 casos en todos los productos, así que `IS NULL` alcanza, sin CASE
--     adicional. Ese filtro sigue sin ir en este CTE (va en la query que
--     consume `largo`), pero el criterio ya está resuelto:
--     `grupo IS NOT NULL`.
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

-- ----------------------------------------------------------------------------
-- Unpivot puro. ÚNICO lugar donde vive el mapeo idx -> columna: un bloque
-- CASE para pd, uno para grupo, uno para modelo. Nada derivado va aquí.
-- El filtro de partición va en este CTE, antes del cross join, para que
-- Impala pode particiones y no lea la tabla completa.
-- ----------------------------------------------------------------------------

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

-- ----------------------------------------------------------------------------
-- Columnas derivadas de `grupo`. Se referencia `largo_raw` una sola vez, así
-- que el hecho de que Impala no materialice los CTEs no cuesta nada aquí.
--
-- grupo_orden: decena = dígito del grupo, unidad = apertura.
--   G1 -> 10 ... G6 -> 60 ... G8 -> 80
--   G7_B -> 71   G7_M -> 72   G7_A -> 73
--   G8_B -> 81   G8_M -> 82   G8_A -> 83
-- Los planos caen en la misma escala (unidad 0), así que ordenan contra los
-- abiertos sin tratamiento aparte: G6 (60) < G7_B (71) < G8_A (83). El
-- cálculo es aritmético a propósito, no un CASE con los 20 valores: un
-- cuarto bloque de mapeo sería justo lo que este archivo trata de evitar.
-- Si `grupo` viniera con un formato inesperado el CAST da NULL y la fila
-- queda sin orden, visible en el tablero en vez de ordenada en silencio.
--
-- OJO: el filtro de nulos NO va en este CTE, va en la query que lo consume,
-- y el criterio es `grupo IS NOT NULL` (ver hallazgo NULOS arriba).
-- ----------------------------------------------------------------------------

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

-- Uso: continuar con el SELECT final que consume `largo`, aplicando
-- `grupo IS NOT NULL` como filtro de nulos.
