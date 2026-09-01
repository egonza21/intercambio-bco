-- ============================================================================
-- Agregado: distribución de las dos PD, por modelo (histograma y PSI)
-- ----------------------------------------------------------------------------
-- Produce una fila por
--   ingestion_year + ingestion_month + segmento + serie_pd + modelo + bin
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
-- Por eso el cross join es contra 2 series, no contra 16 productos, y
-- `producto` NO está en el grano: un histograma "de consumo" y uno "de tdc"
-- eran el mismo histograma repetido.
--
--   general   la PD de los 12 productos no-vivienda
--   vivienda  la PD de hip_vis, hip_novis, lea_hab_vis, lea_hab_novis
--
-- La PD se toma con COALESCE sobre las columnas de su grupo, y el modelo
-- **con un CASE que sigue el MISMO orden**, no con un coalesce aparte. Es
-- deliberado: dos coalesce independientes pueden salir de columnas
-- distintas -- si `pd_consumo` viene nula y `modelo_consumo` no, la PD sale
-- de tdc y el modelo de consumo, y quedan emparejados mal. El CASE
-- `when pd_X is not null then modelo_X` garantiza que el modelo venga de la
-- misma columna que aportó la PD.
--
-- OJO: si la replicación dejara de cumplirse, esta query no lo detecta.
-- Vale comparar las columnas entre sí antes de dar por buena una carga nueva.
--
-- ----------------------------------------------------------------------------
-- El filtro es `pd IS NOT NULL`, NO `grupo IS NOT NULL`
-- ----------------------------------------------------------------------------
-- Es la excepción a la regla estándar del repo: `grupo IS NOT NULL` responde
-- "el cliente califica en ESTE producto", que es una pregunta de producto.
-- Aquí la población correcta es la que el modelo alcanzó a calificar.
--
-- ----------------------------------------------------------------------------
-- Bins: logarítmicos para probabilidad, lineales para puntaje
-- ----------------------------------------------------------------------------
-- **Las PD observadas se concentran en el extremo bajo del rango**, en una
-- franja estrecha muy por debajo de 0,05, no repartidas sobre [0,1]. Con bins
-- lineales de 0,05 el 100% de los clientes cae en el bin 0: el histograma es
-- una sola barra y el PSI da cero SIEMPRE, porque compara una distribución
-- degenerada contra otra idéntica. Es un cero que parece estabilidad y en
-- realidad es ceguera del instrumento.
--
-- Binning para `probabilidad_0_1`: **logarítmico, 20 bins por década**.
--
--     bin = floor(log10(pd) * 20)
--
-- Cada bin abarca un factor de 10^(1/20) = 1,122, o sea pasos de ~12%. La
-- resolución es relativa, no absoluta: el ancho del bin se encoge junto con
-- la PD, así que la franja donde se concentra la población queda repartida
-- en decenas de bins en vez de colapsar en uno. Correr
-- sql/00_perfilado/dominio_grupos_y_escala_pd.sql da el rango vigente si hace
-- falta confirmar que el binning lo cubre.
--
-- Los índices salen negativos porque pd < 1 (una PD de una milésima cae
-- alrededor del bin -60). No es un problema: son etiquetas de bin, y
-- `bin_min` / `bin_max` viajan en la salida con el valor real de PD de cada
-- borde, que es lo que se muestra en el eje.
--
-- Binning para `puntaje_0_999`: **lineal de ancho 50**, 20 bins sobre
-- 0-1000. Ahí el problema no existe porque el puntaje sí usa todo su rango.
--
-- **Los bordes son FIJOS y no dependen de los datos ni del período.** Es
-- condición necesaria del PSI: si se recalcularan por período (deciles del
-- mes, o un rango derivado de min/max), cada período quedaría equireparado
-- por construcción y el PSI volvería a dar ~0. Un bin sin clientes
-- simplemente no produce fila, así que definir una escala generosa no cuesta
-- nada.
--
-- (Contraste deliberado con migracion_pd.sql, que SÍ usa deciles por
-- período: ahí la pregunta es de reordenamiento dentro del ranking, no de
-- desplazamiento de la distribución.)
--
-- `greatest(pd, 0.000001)` protege el log10 de un pd = 0, que no se espera
-- pero daría -infinito. Cae en el bin -120, visible y aislado.
--
-- ----------------------------------------------------------------------------
-- La escala sale de una LISTA EXPLÍCITA de modelos
-- ----------------------------------------------------------------------------
-- Los modelos `ADVANCE_1_1` y `ADVANCE_INCLUSION` dejan en pd el puntaje
-- crudo, de 0 a 999, en vez de una probabilidad. El resto entrega [0,1].
--
-- Antes esto se detectaba con `max(pd) over (partition by ...)` sobre decenas
-- de millones de filas: caro (un shuffle completo solo para clasificar) y
-- frágil (dependía de que el máximo observado cruzara 1 en cada ventana).
--
-- La lista es un **mapeo manual, deliberadamente cerrado**. NO usar un LIKE
-- con comodín:
--   - Un `like '%advance%'` atraparía cualquier modelo futuro con "advance"
--     en el nombre aunque venga en escala 0-1, y lo binearía mal.
--   - La versión anterior de este archivo usaba `like '%advanced%'` -- con
--     "d" final -- y los modelos reales se llaman ADVANCE, sin "d". No
--     matcheaba ninguno: los dos modelos de puntaje se estaban bineando como
--     probabilidad, sin error visible. Es exactamente el modo de falla que
--     una lista explícita hace imposible.
--
-- La comparación es exacta y sensible a mayúsculas, contra el valor tal como
-- viene en las columnas `modelo_*`.
--
-- **Hay que actualizar esta lista cuando entre un modelo nuevo en escala de
-- puntaje.** El síntoma de olvidarlo NO es un error: es un histograma con
-- bins absurdos -- el modelo nuevo queda etiquetado `probabilidad_0_1` y sus
-- puntajes de 0 a 999 se bineen con la escala logarítmica, cayendo en bins
-- positivos junto a los negativos de las PD reales, en el mismo eje.
-- `sql/00_perfilado/dominio_grupos_y_escala_pd.sql` es la query que lo
-- detecta: si el pd_max de un modelo pasa de 1 y no está en esta lista, hay
-- que agregarlo aquí. Ver CLAUDE.md, "Modelos en escala de puntaje".
--
-- ----------------------------------------------------------------------------
-- Grano
-- ----------------------------------------------------------------------------
-- `segmento` SÍ entra: el PSI por segmento es una pregunta legítima de
-- seguimiento (un modelo puede degradarse en un segmento y no en otro), y sin
-- la columna en el hecho no hay forma de reconstruirlo desde Power BI.
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
-- Las dos PD del cliente, cada una con el modelo de la MISMA columna que
-- aportó la PD. Una sola pasada de la tabla ancha, sin unpivot por producto.
-- ----------------------------------------------------------------------------

pd_cliente as (
  select
    c.ingestion_year,
    c.ingestion_month,
    c.segmento,
    coalesce(c.pd_consumo,   c.pd_tdc,       c.pd_libranza,  c.pd_rota,
             c.pd_comercial, c.pd_micro,     c.pd_sobre,     c.pd_sufi_veh,
             c.pd_sufi_moto, c.pd_sufi_cpe,  c.pd_sufi_con,  c.pd_calm)
      as pd_general,
    case
      when c.pd_consumo   is not null then c.modelo_consumo
      when c.pd_tdc       is not null then c.modelo_tdc
      when c.pd_libranza  is not null then c.modelo_libranza
      when c.pd_rota      is not null then c.modelo_rota
      when c.pd_comercial is not null then c.modelo_comercial
      when c.pd_micro     is not null then c.modelo_micro
      when c.pd_sobre     is not null then c.modelo_sobre
      when c.pd_sufi_veh  is not null then c.modelo_sufi_veh
      when c.pd_sufi_moto is not null then c.modelo_sufi_moto
      when c.pd_sufi_cpe  is not null then c.modelo_sufi_cpe
      when c.pd_sufi_con  is not null then c.modelo_sufi_con
      when c.pd_calm      is not null then c.modelo_calm
    end as modelo_general,
    coalesce(c.pd_hip_vis, c.pd_hip_novis,
             c.pd_lea_hab_vis, c.pd_lea_hab_novis)
      as pd_vivienda,
    case
      when c.pd_hip_vis       is not null then c.modelo_hip_vis
      when c.pd_hip_novis     is not null then c.modelo_hip_novis
      when c.pd_lea_hab_vis   is not null then c.modelo_lea_hab_vis
      when c.pd_lea_hab_novis is not null then c.modelo_lea_hab_novis
    end as modelo_vivienda
  from resultados_riesgos.maestro_calificaciones_pn c
  where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}
),

-- Cross join contra 2 filas, no 16: duplica el volumen, no lo multiplica.
series_pd as (
  select
    p.ingestion_year,
    p.ingestion_month,
    p.segmento,
    s.serie_pd,
    case s.idx
      when 1 then p.pd_general
      when 2 then p.pd_vivienda
    end as pd,
    -- `''` y NULL son lo mismo -- ausencia de modelo -- y sin normalizar
    -- serían dos categorías distintas en el tablero. Ver "El modelo vacío"
    -- en CLAUDE.md.
    nullif(trim(case s.idx
      when 1 then p.modelo_general
      when 2 then p.modelo_vivienda
    end), '') as modelo
  from pd_cliente p
  cross join series s
),

-- La escala sale del nombre del modelo, no de un max() sobre los datos.
escalado as (
  select
    sp.ingestion_year,
    sp.ingestion_month,
    sp.segmento,
    sp.serie_pd,
    sp.modelo,
    sp.pd,
    case when sp.modelo in ('ADVANCE_1_1', 'ADVANCE_INCLUSION')
         then 'puntaje_0_999'
         else 'probabilidad_0_1' end as escala
  from series_pd sp
  where sp.pd is not null
),

binned as (
  select
    e.ingestion_year,
    e.ingestion_month,
    e.segmento,
    e.serie_pd,
    e.modelo,
    e.escala,
    e.pd,
    case when e.escala = 'puntaje_0_999'
         then least(cast(floor(e.pd / 50.0) as int), 19)
         else cast(floor(log10(greatest(e.pd, 0.000001)) * 20) as int)
    end as bin
  from escalado e
)

select
  b.ingestion_year,
  b.ingestion_month,
  b.segmento,
  b.serie_pd,
  b.modelo,
  b.escala,
  b.bin,
  case when b.escala = 'puntaje_0_999'
       then b.bin * 50.0
       else pow(10, b.bin / 20.0)
  end as bin_min,
  case when b.escala = 'puntaje_0_999'
       then (b.bin + 1) * 50.0
       else pow(10, (b.bin + 1) / 20.0)
  end as bin_max,
  count(*)   as clientes,
  sum(b.pd)  as pd_suma,
  min(b.pd)  as pd_min,
  max(b.pd)  as pd_max
from binned b
group by
  b.ingestion_year,
  b.ingestion_month,
  b.segmento,
  b.serie_pd,
  b.modelo,
  b.escala,
  b.bin;
