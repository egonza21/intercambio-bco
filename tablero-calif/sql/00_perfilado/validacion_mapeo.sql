-- ============================================================================
-- Perfilado: validación del mapeo idx -> producto del unpivot
-- ----------------------------------------------------------------------------
-- Compara, para UN mes, los 16 `count(g_*)` de la tabla ancha contra el
-- conteo por producto en `largo` con `grupo IS NOT NULL`. Produce 16 filas
-- con `conteo_ancho`, `conteo_largo` y `diferencia`.
--
-- **Todas las diferencias deben dar 0.** Cualquier fila distinta de 0 señala
-- un CASE desalineado en el unpivot.
--
-- Parámetros:
--   {MES} -- un solo mes, en ingestion_year*12+ingestion_month
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
-- Límite de esta validación -- leer antes de confiar en ella
-- ----------------------------------------------------------------------------
-- El lado ancho usa su propio CASE idx -> conteo, así que hay DOS mapeos en
-- juego. La query atrapa un desalineo introducido en uno de los dos, que es
-- el caso realista: alguien edita el fragmento canónico y desplaza un WHEN.
-- NO atrapa un desalineo idéntico copiado en ambos.
--
-- Por eso el CASE de `ancho_por_producto` se escribe siguiendo la tabla de
-- CLAUDE.md, NO copiando el bloque del fragmento. Si alguna vez hay que
-- tocarlo, transcribirlo de nuevo desde la tabla en lugar de copiar y pegar
-- del otro lado del archivo.
--
-- Los dos lugares donde el nombre del producto NO coincide con el sufijo de
-- la columna son `rotativo` -> `g_rota` (idx 4) y `sobregiro` -> `g_sobre`
-- (idx 11). Son los candidatos más probables a un desalineo silencioso, y la
-- razón de que valga la pena correr esto en vez de leer el CASE a ojo.
--
-- ----------------------------------------------------------------------------
-- Costo
-- ----------------------------------------------------------------------------
-- `conteos_ancho` agrega a UNA fila de 16 columnas y se referencia una sola
-- vez; el cross join contra `productos` la abre a 16 filas sin releer nada.
-- El lado largo hace su propia pasada con el unpivot. Son dos lecturas de un
-- mes, no de la ventana completa: correrla mes a mes es barato.
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
  where c.ingestion_year * 12 + c.ingestion_month = {MES}
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
-- Lado ancho: una sola fila con 16 conteos. `count(columna)` ignora nulos.
-- ----------------------------------------------------------------------------

conteos_ancho as (
  select
    count(c.g_consumo)        as n_consumo,
    count(c.g_tdc)            as n_tdc,
    count(c.g_libranza)       as n_libranza,
    count(c.g_rota)           as n_rota,
    count(c.g_hip_vis)        as n_hip_vis,
    count(c.g_hip_novis)      as n_hip_novis,
    count(c.g_lea_hab_vis)    as n_lea_hab_vis,
    count(c.g_lea_hab_novis)  as n_lea_hab_novis,
    count(c.g_comercial)      as n_comercial,
    count(c.g_micro)          as n_micro,
    count(c.g_sobre)          as n_sobre,
    count(c.g_sufi_veh)       as n_sufi_veh,
    count(c.g_sufi_moto)      as n_sufi_moto,
    count(c.g_sufi_cpe)       as n_sufi_cpe,
    count(c.g_sufi_con)       as n_sufi_con,
    count(c.g_calm)           as n_calm
  from resultados_riesgos.maestro_calificaciones_pn c
  where c.ingestion_year * 12 + c.ingestion_month = {MES}
),

-- ----------------------------------------------------------------------------
-- Abre esa fila única a 16, una por producto. Este CASE se transcribe de la
-- tabla de CLAUDE.md, no se copia del bloque de arriba: ver "Límite de esta
-- validación" en el encabezado.
-- ----------------------------------------------------------------------------

ancho_por_producto as (
  select
    p.producto,
    case p.idx
      when  1 then a.n_consumo        when  2 then a.n_tdc
      when  3 then a.n_libranza       when  4 then a.n_rota
      when  5 then a.n_hip_vis        when  6 then a.n_hip_novis
      when  7 then a.n_lea_hab_vis    when  8 then a.n_lea_hab_novis
      when  9 then a.n_comercial      when 10 then a.n_micro
      when 11 then a.n_sobre          when 12 then a.n_sufi_veh
      when 13 then a.n_sufi_moto      when 14 then a.n_sufi_cpe
      when 15 then a.n_sufi_con       when 16 then a.n_calm
    end as conteo_ancho
  from conteos_ancho a
  cross join productos p
)

select
  a.producto,
  a.conteo_ancho,
  coalesce(l.conteo_largo, 0) as conteo_largo,
  a.conteo_ancho - coalesce(l.conteo_largo, 0) as diferencia
from ancho_por_producto a
left join conteo_largo l
  on a.producto = l.producto
order by a.producto;
