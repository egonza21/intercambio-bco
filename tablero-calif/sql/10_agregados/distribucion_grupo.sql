-- ============================================================================
-- Agregado: distribución de clientes por grupo de riesgo
-- ----------------------------------------------------------------------------
-- Produce una fila por
--   ingestion_year + ingestion_month + segmento + producto + grupo + modelo
-- con el conteo de clientes. Alimenta los visuales de composición (barra
-- apilada 100% de grupo por producto), el heatmap segmento x grupo y la
-- vigencia de modelos.
--
-- Es un agregado de PÁGINA FUNCIONAL (equipo comercial / negocio): responde
-- "cómo se reparten los clientes entre grupos", no "cómo se comporta el
-- modelo". Ver powerbi/notas_modelo.md, "Dos audiencias, dos bloques de
-- páginas".
--
-- Parámetros:
--   {DESDE}, {HASTA} -- rango de meses, en ingestion_year*12+ingestion_month
--
-- ----------------------------------------------------------------------------
-- Qué NO lleva, y por qué
-- ----------------------------------------------------------------------------
-- - **Nada de `pd`.** Verificado 2026-08-25: la PD se replica idéntica en los
--   12 productos no-vivienda, y los 4 de vivienda comparten la suya. Solo hay
--   DOS PD por cliente, no 16. Traer pd_suma / pd_min / pd_max con `producto`
--   en el grano invitaba a que Power BI sumara la misma PD 12 veces al
--   agregar sobre productos: un número sin significado que además parecía
--   correcto. La PD vive ahora en pd_por_modelo.sql y migracion_pd.sql, con
--   su grano real. Ver CLAUDE.md, "La PD no es por producto".
-- - `grupo_base` y `grupo_orden`: van en una dim_grupo que se arma aparte en
--   Power Query (ver powerbi/notas_modelo.md). Este agregado lleva `grupo`
--   como llave y nada más; las dos derivadas se resuelven en el modelo, no
--   por fila del hecho.
-- - `familia_producto`: está determinada por `producto`, así que vive en la
--   dimensión de producto. Repetirla aquí solo engorda el hecho.
--
-- **Esta copia del fragmento canónico no lleva el CTE `largo`.** Como aquí no
-- se usa ninguna columna derivada, calcular `grupo_base` y `grupo_orden`
-- sería un regexp_replace más aritmética de strings sobre las ~240 MM de
-- expansiones que produce el cross join cada mes, para descartarlas después.
-- Una versión anterior las dejaba puestas confiando en que Impala podaría las
-- columnas no referenciadas; eso era una suposición, no un hecho verificado,
-- y no vale el riesgo cuando quitarlas es gratis.
--
-- Lo que SÍ se mantiene idéntico al fragmento canónico son los tres bloques
-- `case p.idx` del mapeo: es lo único que tiene que estar alineado entre
-- copias, y lo que valida sql/00_perfilado/validacion_mapeo.sql.
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
-- - `clientes` SÍ se puede sumar entre productos, pero lo que da es
--   pares cliente-producto, no clientes: un cliente con grupo en 5 productos
--   aporta 5. Para contar clientes hay que fijar un producto, o usar
--   base_clientes.sql. Es la misma advertencia de siempre, y ahora es la
--   única métrica del agregado, así que conviene tenerla presente.
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

-- Sin CTE `largo`: esta query no usa ninguna columna derivada, así que el
-- SELECT final consume `largo_raw` directo. Ver el encabezado.

select
  r.ingestion_year,
  r.ingestion_month,
  r.segmento,
  r.producto,
  r.grupo,
  -- '' y NULL son lo mismo: ausencia de modelo. Ver "El modelo vacío"
  -- en CLAUDE.md.
  nullif(trim(r.modelo), '') as modelo,
  count(*) as clientes
from largo_raw r
where r.grupo is not null
group by
  r.ingestion_year,
  r.ingestion_month,
  r.segmento,
  r.producto,
  r.grupo,
  nullif(trim(r.modelo), '');
