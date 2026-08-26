-- ============================================================================
-- Agregado: distribución de las dos PD, por modelo (histograma y PSI)
-- ----------------------------------------------------------------------------
-- Produce una fila por
--   ingestion_year + ingestion_month + serie_pd + modelo + bin
-- con el conteo de clientes y los estadísticos del bin. Alimenta el
-- histograma de PD y el PSI por modelo, con umbrales en 0,1 y 0,25.
--
-- Es un agregado de PÁGINA DE MODELOS (seguimiento técnico). Ver
-- powerbi/notas_modelo.md, "Dos audiencias, dos bloques de páginas".
--
-- Parámetros:
--   {DESDE}, {HASTA} -- rango de meses, en ingestion_year*12+ingestion_month
--
-- ----------------------------------------------------------------------------
-- Solo hay DOS PD, no 16 -- y por eso esta query no despivota por producto
-- ----------------------------------------------------------------------------
-- Verificado 2026-08-25: la PD se replica idéntica en los 12 productos
-- no-vivienda, y los 4 de vivienda comparten la suya. La PD es un atributo
-- del CLIENTE, no del producto; lo que sí es por producto es el `grupo`, que
-- sale de traducir esa PD con los cortes de cada producto (ver
-- cortes_por_producto.sql).
--
-- Consecuencias directas sobre esta query:
--
--   - NO hay cross join contra los 16 productos. Se cruza contra un CTE de
--     2 series, así que el volumen se duplica en vez de multiplicarse por 16.
--     Es ~8 veces más barata que la versión anterior y mide lo mismo.
--   - `producto` NO está en el grano: no significa nada aquí. Un histograma
--     de PD "de consumo" y uno "de tdc" eran el mismo histograma repetido.
--   - El grano es `serie_pd` + `modelo`. Dos series:
--       general   la PD de los 12 productos no-vivienda
--       vivienda  la PD de hip_vis, hip_novis, lea_hab_vis, lea_hab_novis
--
-- Cada serie se toma con COALESCE sobre las columnas de su grupo, no de una
-- sola columna representativa. Si la replicación es exacta el coalesce es
-- inocuo; si alguna columna llegara nula donde otra tiene valor, lo recupera
-- en vez de perder la fila. El costo es nulo y protege contra el único modo
-- de falla plausible de la premisa.
--
-- OJO: si la replicación dejara de cumplirse, esta query no lo detecta -- el
-- coalesce se queda con la primera no nula y sigue. Vale correr una
-- comparación columna a columna antes de dar por buena una carga nueva.
--
-- ----------------------------------------------------------------------------
-- El filtro es `pd IS NOT NULL`, NO `grupo IS NOT NULL`
-- ----------------------------------------------------------------------------
-- Es la excepción a la regla estándar del repo, y se sigue del hallazgo de
-- arriba: `grupo IS NOT NULL` responde "el cliente califica en ESTE
-- producto", que es una pregunta de producto. Aquí la población correcta es
-- la que el modelo alcanzó a calificar, tenga o no grupo en algún producto.
-- Filtrar por grupo de un producto cualquiera sesgaría la distribución hacia
-- la población elegible de ese producto.
--
-- ----------------------------------------------------------------------------
-- Escala y bins fijos, que es lo que el PSI exige
-- ----------------------------------------------------------------------------
-- El modelo "advanced" deja en pd el puntaje crudo, de 0 a 999, en vez de una
-- probabilidad en [0,1]. La escala se detecta con
-- `max(pd) over (partition by serie_pd, modelo)`: con función de ventana y no
-- con un segundo agregado, para no recorrer los datos dos veces.
--
-- 20 bins de ancho constante por escala: 0,05 para probabilidad (0 a 1) y 50
-- para puntaje (0 a 1000). Los bordes son FIJOS, no cuantiles del período.
--
-- Es deliberado: el PSI compara la distribución de un período contra otro
-- sobre los MISMOS bins. Si los bordes se recalcularan por período, cada
-- período quedaría equireparado por construcción y el PSI daría siempre ~0,
-- que es justo el resultado que se quiere detectar cuando no es cierto.
--
-- (Contraste deliberado con migracion_pd.sql, que SÍ usa deciles por período:
-- ahí la pregunta es de reordenamiento dentro del ranking, no de
-- desplazamiento de la distribución. Son análisis distintos y no
-- intercambiables.)
--
-- `least(..., 19)` agrupa en el último bin lo que caiga en el borde superior
-- o por encima, para que ningún cliente quede fuera del histograma.
--
-- El PSI se calcula en DAX sobre este agregado. Aquí solo van los conteos.
--
-- `count(*)` cuenta clientes: el grano de `series_pd` es cliente x mes x
-- serie, una fila por combinación.
--
-- Sin ORDER BY a propósito: Power BI importa y ordena en el modelo.
-- ============================================================================

with series as (
              select 1 as idx, 'general'  as serie_pd
    union all select 2,        'vivienda'
),

-- ----------------------------------------------------------------------------
-- Las dos PD del cliente, con su modelo. Una sola pasada de la tabla ancha,
-- sin unpivot por producto.
-- ----------------------------------------------------------------------------

pd_cliente as (
  select
    c.num_doc,
    c.tipo_doc,
    c.ingestion_year,
    c.ingestion_month,
    coalesce(c.pd_consumo,   c.pd_tdc,       c.pd_libranza,  c.pd_rota,
             c.pd_comercial, c.pd_micro,     c.pd_sobre,     c.pd_sufi_veh,
             c.pd_sufi_moto, c.pd_sufi_cpe,  c.pd_sufi_con,  c.pd_calm)
      as pd_general,
    coalesce(c.modelo_consumo,   c.modelo_tdc,      c.modelo_libranza,
             c.modelo_rota,      c.modelo_comercial, c.modelo_micro,
             c.modelo_sobre,     c.modelo_sufi_veh, c.modelo_sufi_moto,
             c.modelo_sufi_cpe,  c.modelo_sufi_con, c.modelo_calm)
      as modelo_general,
    coalesce(c.pd_hip_vis, c.pd_hip_novis,
             c.pd_lea_hab_vis, c.pd_lea_hab_novis)
      as pd_vivienda,
    coalesce(c.modelo_hip_vis, c.modelo_hip_novis,
             c.modelo_lea_hab_vis, c.modelo_lea_hab_novis)
      as modelo_vivienda
  from resultados_riesgos.maestro_calificaciones_pn c
  where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}
),

-- Cross join contra 2 filas, no 16: duplica el volumen, no lo multiplica.
series_pd as (
  select
    p.ingestion_year,
    p.ingestion_month,
    s.serie_pd,
    case s.idx
      when 1 then p.pd_general
      when 2 then p.pd_vivienda
    end as pd,
    case s.idx
      when 1 then p.modelo_general
      when 2 then p.modelo_vivienda
    end as modelo
  from pd_cliente p
  cross join series s
),

-- La ventana se evalúa después del WHERE, así que `pd_max_modelo` es el
-- máximo entre las filas que efectivamente entran al histograma.
calificados as (
  select
    sp.ingestion_year,
    sp.ingestion_month,
    sp.serie_pd,
    sp.modelo,
    sp.pd,
    max(sp.pd) over (partition by sp.serie_pd, sp.modelo) as pd_max_modelo
  from series_pd sp
  where sp.pd is not null
),

escalado as (
  select
    c.ingestion_year,
    c.ingestion_month,
    c.serie_pd,
    c.modelo,
    c.pd,
    case when c.pd_max_modelo > 1 then 'puntaje_0_999'
         else 'probabilidad_0_1' end as escala,
    case when c.pd_max_modelo > 1 then 50.0
         else 0.05 end as bin_ancho
  from calificados c
),

binned as (
  select
    e.ingestion_year,
    e.ingestion_month,
    e.serie_pd,
    e.modelo,
    e.pd,
    e.escala,
    e.bin_ancho,
    least(cast(floor(e.pd / e.bin_ancho) as int), 19) as bin
  from escalado e
)

select
  b.ingestion_year,
  b.ingestion_month,
  b.serie_pd,
  b.modelo,
  b.escala,
  b.bin,
  b.bin * b.bin_ancho         as bin_min,
  (b.bin + 1) * b.bin_ancho   as bin_max,
  count(*)                    as clientes,
  sum(b.pd)                   as pd_suma,
  min(b.pd)                   as pd_min,
  max(b.pd)                   as pd_max
from binned b
group by
  b.ingestion_year,
  b.ingestion_month,
  b.serie_pd,
  b.modelo,
  b.escala,
  b.bin,
  b.bin_ancho;
