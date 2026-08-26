-- ============================================================================
-- Agregado: distribución de PD por modelo (histograma y PSI)
-- ----------------------------------------------------------------------------
-- Produce una fila por
--   ingestion_year + ingestion_month + producto + modelo + bin
-- con el conteo de clientes y los estadísticos de PD del bin. Alimenta el
-- histograma de PD y el cálculo de PSI por modelo, con umbrales en 0,1 y
-- 0,25.
--
-- Parámetros:
--   {DESDE}, {HASTA} -- rango de meses, en ingestion_year*12+ingestion_month
--
-- ----------------------------------------------------------------------------
-- Siempre segmentado por modelo, y por qué eso no es opcional
-- ----------------------------------------------------------------------------
-- El modelo "advanced" deja en `pd` el puntaje crudo, de 0 a 999, en vez de
-- una probabilidad en [0,1]. Mezclar sus filas con las de un modelo de
-- probabilidad en un mismo eje da un histograma sin significado y un PSI
-- inventado. Por eso `modelo` está en el grano y el ancho del bin se decide
-- POR MODELO, no global.
--
-- La escala se detecta con `max(pd) over (partition by producto, modelo)`:
-- si el máximo del modelo en toda la ventana pasa de 1, es un puntaje
-- 0-999; si no, es una probabilidad. Se hace con función de ventana y no con
-- un segundo agregado para no recorrer el unpivot dos veces. Es un umbral
-- estable -- un modelo entrega puntajes o probabilidades, no ambos -- pero
-- si algún día un modelo de probabilidad tuviera máximo exactamente 1,0 y
-- otro puntaje llegara a 1, esta detección es lo primero a revisar.
--
-- NO se normaliza dividiendo por 1000: los bins salen en las unidades
-- originales del modelo. `escala` viaja en la salida para que Power BI pueda
-- separar o excluir explícitamente los modelos que no comparten unidad.
--
-- ----------------------------------------------------------------------------
-- Bins fijos, que es lo que el PSI exige
-- ----------------------------------------------------------------------------
-- 20 bins de ancho constante por escala: 0,05 para probabilidad (0 a 1) y 50
-- para puntaje (0 a 1000). Los bordes son FIJOS, no cuantiles del período.
--
-- Es deliberado: el PSI compara la distribución de un período contra otro
-- sobre los MISMOS bins. Si los bordes se recalcularan por período (ntile,
-- deciles del mes), cada período quedaría equireparado por construcción y el
-- PSI daría siempre ~0, que es justo el resultado que se quiere detectar
-- cuando no es cierto. Bordes fijos también sobreviven a un cambio de
-- ventana de refresco: los bins de {DESDE}-{HASTA} de hoy son los mismos que
-- los de mañana.
--
-- `least(..., 19)` agrupa en el último bin cualquier valor en el borde
-- superior o por encima de él, para que ningún cliente quede fuera del
-- histograma.
--
-- El PSI se calcula en DAX sobre este agregado: proporción del bin en el
-- período contra proporción del bin en el período base, sumando
-- (p_act - p_base) * ln(p_act / p_base). Aquí solo van los conteos.
--
-- ----------------------------------------------------------------------------
-- Grano: sin segmento, y con filtro por grupo
-- ----------------------------------------------------------------------------
-- `segmento` NO entra en el grano: multiplicaría las filas por cada segmento
-- sin que el PSI por modelo lo necesite. Si hiciera falta un PSI por
-- segmento, se agrega la columna aquí y al group by, asumiendo el costo.
--
-- El filtro es `grupo IS NOT NULL AND pd IS NOT NULL`. El primero es el
-- criterio estándar de "el cliente califica"; el segundo saca las 726 filas
-- con pd nula y grupo poblado, que no tienen valor que binear. Por eso
-- `clientes` de este agregado NO cuadra contra el de distribucion_grupo.sql:
-- este cuenta los que tienen PD, aquel cuenta los que tienen grupo.
--
-- Sin ORDER BY a propósito: Power BI importa y ordena en el modelo.
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
),

-- La ventana se evalúa después del WHERE, así que `pd_max_modelo` es el
-- máximo entre las filas que efectivamente entran al histograma.
calificados as (
  select
    l.ingestion_year,
    l.ingestion_month,
    l.producto,
    l.modelo,
    l.pd,
    max(l.pd) over (partition by l.producto, l.modelo) as pd_max_modelo
  from largo l
  where l.grupo is not null
    and l.pd is not null
),

escalado as (
  select
    c.ingestion_year,
    c.ingestion_month,
    c.producto,
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
    e.producto,
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
  b.producto,
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
  b.producto,
  b.modelo,
  b.escala,
  b.bin,
  b.bin_ancho;
