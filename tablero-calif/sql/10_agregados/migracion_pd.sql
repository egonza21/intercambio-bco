-- ============================================================================
-- Agregado: migración de PD por deciles, con rezago parametrizable
-- ----------------------------------------------------------------------------
-- Produce una fila por
--   mes destino + serie_pd + modelo_origen + modelo_destino +
--   decil_origen + decil_destino + categoria
-- con el conteo de clientes. Alimenta la matriz 10x10 de migración de PD de
-- las páginas de seguimiento de modelos.
--
-- Es un agregado de PÁGINA DE MODELOS (seguimiento técnico). Ver
-- powerbi/notas_modelo.md, "Dos audiencias, dos bloques de páginas".
--
-- Parámetros:
--   {DESDE}, {HASTA} -- rango de meses DESTINO, en ingestion_year*12+ingestion_month
--   {REZAGO}         -- meses hacia atrás contra los que se compara
--
-- ----------------------------------------------------------------------------
-- Qué mide, y en qué se diferencia de migracion.sql
-- ----------------------------------------------------------------------------
-- migracion.sql mueve clientes entre GRUPOS por producto: es la pregunta de
-- negocio, "cómo se recalifica la cartera". Esta query mueve clientes entre
-- DECILES de PD: es la pregunta de modelo, "cómo se reordena el puntaje".
--
-- Son distintas porque solo hay dos PD y dieciséis grupos: un cliente puede
-- cambiar de grupo en un producto sin que su PD se mueva (si cambian los
-- cortes del producto), y puede moverse de decil sin cambiar de grupo. Ver
-- CLAUDE.md, "La PD no es por producto".
--
-- ----------------------------------------------------------------------------
-- Deciles POR PERÍODO -- deliberadamente distinto de pd_por_modelo.sql
-- ----------------------------------------------------------------------------
-- `ntile(10)` se calcula dentro de cada serie + modelo + mes, así que los
-- deciles son de RANKING, no de bandas fijas de PD. Cada decil tiene el 10%
-- de la población de su mes por construcción.
--
-- Eso es lo correcto AQUÍ y sería un error en pd_por_modelo.sql:
--   - Esta matriz pregunta por reordenamiento: quién estaba en el decil más
--     riesgoso hace {REZAGO} meses y dónde está ahora. La diagonal es
--     estabilidad del ranking.
--   - El PSI pregunta por desplazamiento de la distribución, y con bins
--     por período daría siempre ~0. Por eso pd_por_modelo.sql usa bins fijos.
-- No mezclar las dos lecturas: una matriz de deciles con diagonal fuerte NO
-- dice que la distribución no se movió, solo que el orden se mantuvo.
--
-- El `ntile` se particiona TAMBIÉN por modelo, no solo por serie y mes. Es
-- obligatorio: ADVANCE_1_1 y ADVANCE_INCLUSION entregan puntaje 0-999 y el
-- resto probabilidad 0-1, así que rankearlos juntos mandaría a todos los
-- clientes de esos dos modelos a los deciles altos por escala, no por riesgo.
--
-- Ojo con la diferencia respecto de pd_por_modelo.sql: aquí NO hace falta
-- clasificar la escala, porque particionar por `modelo` ya aísla cada escala
-- en su propio ranking. Por eso esta query no tiene la lista de modelos de
-- puntaje y no se rompe si esa lista queda desactualizada.
--
-- ----------------------------------------------------------------------------
-- {REZAGO}: mensual y semestral NO son encadenables
-- ----------------------------------------------------------------------------
-- Igual que en migracion.sql: rezago 1 da la mensual, rezago 6 la semestral,
-- y las mensuales no se suman para obtener la semestral. Los primeros
-- {REZAGO} meses no tienen contra qué compararse: con la tabla arrancando en
-- 2025-05, la primera matriz semestral válida es la de 2025-11. Regla:
-- {DESDE} >= 24305 + {REZAGO}.
--
-- ----------------------------------------------------------------------------
-- Las categorías
-- ----------------------------------------------------------------------------
--   movimiento    el cliente tiene PD en los dos meses. Es la matriz 10x10.
--   entrada       no estaba en la tabla en el mes origen. Cambio de población.
--   ganancia_pd   estaba en la tabla en el mes origen, pero sin PD en esa
--                 serie. Decisión del modelo, no cambio de población.
--   salida        no está en la tabla en el mes destino. Cambio de población.
--   perdida_pd    está en la tabla en el mes destino, pero sin PD en esa
--                 serie. Decisión del modelo.
--
-- Misma distinción que en migracion.sql y por la misma razón: separar un
-- cambio de población de una decisión del modelo exige cruzar contra la base
-- de clientes del mes, de ahí el CTE `base_mes`.
--
-- ----------------------------------------------------------------------------
-- Costo
-- ----------------------------------------------------------------------------
-- Sin cross join de 16: la PD es del cliente, así que solo se duplica por las
-- 2 series. Pero el `ntile` obliga a un sort completo por partición
-- (serie x modelo x mes) sobre ~15 MM de filas por mes, y `deciles` se
-- referencia dos veces (destino y origen), así que ese sort corre dos veces.
-- Impala no materializa los CTEs. Medir aparte antes de meterla al refresco.
--
-- `count(*)` cuenta clientes: el full outer join es sobre
-- cliente + serie + mes, llave única a cada lado.
--
-- Sin ORDER BY a propósito: Power BI importa y ordena en el modelo.
-- ============================================================================

with series as (
              select 1 as idx, 'general'  as serie_pd
    union all select 2,        'vivienda'
),

-- Las dos PD del cliente, cada una con el modelo de la MISMA columna que
-- aportó la PD: el CASE sigue el mismo orden que el COALESCE. Dos coalesce
-- independientes pueden salir de columnas distintas y emparejar mal la PD
-- con su modelo, lo que aquí además contaminaría la partición del ntile.
-- Ver pd_por_modelo.sql.
pd_cliente as (
  select
    c.num_doc,
    c.tipo_doc,
    c.ingestion_year * 12 + c.ingestion_month as idx_mes,
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
  where c.ingestion_year * 12 + c.ingestion_month
        between {DESDE} - {REZAGO} and {HASTA}
),

series_pd as (
  select
    p.num_doc,
    p.tipo_doc,
    p.idx_mes,
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

-- Deciles de ranking dentro de serie + modelo + mes. Se referencia dos veces
-- más abajo: ahí está el doble costo del sort.
deciles as (
  select
    sp.num_doc,
    sp.tipo_doc,
    sp.idx_mes,
    sp.serie_pd,
    sp.modelo,
    ntile(10) over (
      partition by sp.serie_pd, sp.modelo, sp.idx_mes
      order by sp.pd
    ) as decil
  from series_pd sp
  where sp.pd is not null
),

destino as (
  select
    d.num_doc,
    d.tipo_doc,
    d.serie_pd,
    d.idx_mes,
    d.modelo,
    d.decil
  from deciles d
  where d.idx_mes between {DESDE} and {HASTA}
),

origen as (
  select
    d.num_doc,
    d.tipo_doc,
    d.serie_pd,
    d.idx_mes + {REZAGO} as idx_mes_destino,
    d.modelo,
    d.decil
  from deciles d
  where d.idx_mes between {DESDE} - {REZAGO} and {HASTA} - {REZAGO}
),

-- Presencia del cliente en la tabla, mes a mes. Lee tres columnas, sin cross
-- join: separa el cambio de población de la decisión del modelo.
base_mes as (
  select
    c.num_doc,
    c.tipo_doc,
    c.ingestion_year * 12 + c.ingestion_month as idx_mes
  from resultados_riesgos.maestro_calificaciones_pn c
  where c.ingestion_year * 12 + c.ingestion_month
        between {DESDE} - {REZAGO} and {HASTA}
),

par as (
  select
    coalesce(d.num_doc,  o.num_doc)          as num_doc,
    coalesce(d.tipo_doc, o.tipo_doc)         as tipo_doc,
    coalesce(d.serie_pd, o.serie_pd)         as serie_pd,
    coalesce(d.idx_mes,  o.idx_mes_destino)  as idx_mes_destino,
    o.modelo                                 as modelo_origen,
    d.modelo                                 as modelo_destino,
    o.decil                                  as decil_origen,
    d.decil                                  as decil_destino,
    case
      when d.num_doc is null then o.idx_mes_destino
      when o.num_doc is null then d.idx_mes - {REZAGO}
    end                                      as idx_mes_presencia
  from destino d
  full outer join origen o
    on  d.num_doc  = o.num_doc
    and d.tipo_doc = o.tipo_doc
    and d.serie_pd = o.serie_pd
    and d.idx_mes  = o.idx_mes_destino
),

clasificado as (
  select
    p.serie_pd,
    p.idx_mes_destino,
    cast(floor((p.idx_mes_destino - 1) / 12) as smallint) as ingestion_year,
    p.modelo_origen,
    p.modelo_destino,
    p.decil_origen,
    p.decil_destino,
    case
      when p.decil_origen is not null
       and p.decil_destino is not null       then 'movimiento'
      when p.decil_origen is null
       and b.num_doc is null                 then 'entrada'
      when p.decil_origen is null            then 'ganancia_pd'
      when b.num_doc is null                 then 'salida'
      else                                        'perdida_pd'
    end as categoria
  from par p
  left join base_mes b
    on  b.num_doc  = p.num_doc
    and b.tipo_doc = p.tipo_doc
    and b.idx_mes  = p.idx_mes_presencia
)

select
  c.ingestion_year,
  cast(c.idx_mes_destino - 12 * c.ingestion_year as tinyint) as ingestion_month,
  c.serie_pd,
  c.modelo_origen,
  c.modelo_destino,
  c.decil_origen,
  c.decil_destino,
  c.categoria,
  count(*) as clientes
from clasificado c
group by
  c.ingestion_year,
  c.idx_mes_destino,
  c.serie_pd,
  c.modelo_origen,
  c.modelo_destino,
  c.decil_origen,
  c.decil_destino,
  c.categoria;
