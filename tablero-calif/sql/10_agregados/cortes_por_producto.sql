-- ============================================================================
-- Agregado: fronteras de corte de PD por producto y grupo
-- ----------------------------------------------------------------------------
-- Produce una fila por
--   ingestion_year + ingestion_month + producto + modelo + grupo
-- con el rango de PD observado en ese grupo (min y max) y el conteo de
-- clientes. Alimenta el visual de sensibilidad de cortes y sirve como
-- validación de que los cortes son puramente por PD.
--
-- Es un agregado de PÁGINA DE MODELOS (seguimiento técnico). Ver
-- powerbi/notas_modelo.md, "Dos audiencias, dos bloques de páginas".
--
-- Parámetros:
--   {DESDE}, {HASTA} -- rango de meses, en ingestion_year*12+ingestion_month
--
-- ----------------------------------------------------------------------------
-- Qué es un "corte" y por qué esta query lo revela
-- ----------------------------------------------------------------------------
-- Solo hay dos PD (la de los 12 productos no-vivienda y la de los 4 de
-- vivienda), pero dieciséis columnas de grupo. Lo que hace producto-específico
-- al grupo son los CORTES: cada producto traduce la misma PD a grupo con sus
-- propios umbrales. Ver CLAUDE.md, "La PD no es por producto".
--
-- Esos umbrales no están en ninguna tabla del alcance de este repo, pero se
-- pueden inferir de los datos: **el max de un grupo y el min del siguiente
-- son la frontera de corte**. Ordenando los grupos de un producto por su
-- `pd_min`, la sucesión de (pd_max, pd_min siguiente) reconstruye la tabla de
-- cortes vigente ese mes.
--
-- Por eso el mes está en el grano: si los cortes de un producto cambian entre
-- dos meses, se ve como un salto en la frontera, y es exactamente la clase de
-- cambio que hay que poder fechar.
--
-- ----------------------------------------------------------------------------
-- La validación: `solapa`
-- ----------------------------------------------------------------------------
-- Si el corte fuera puramente por PD, los rangos de dos grupos consecutivos
-- no pueden solaparse: todo cliente con PD por encima del corte cae en el
-- grupo siguiente, sin excepción.
--
-- La columna `solapa` marca las filas donde `pd_min` es MENOR que el `pd_max`
-- del grupo inmediatamente anterior. Una fila con `solapa = true` significa
-- que dos clientes con la misma PD quedaron en grupos distintos, y por lo
-- tanto **el corte de ese producto no depende solo de la PD**: entra otra
-- variable (política comercial, comportamiento, override manual).
--
-- No es necesariamente un error -- puede ser una regla de negocio legítima --
-- pero cambia cómo se lee todo el tablero, así que tiene que ser una
-- decisión explícita y no un descubrimiento tardío.
--
-- El orden se establece por `pd_min` ascendente, NO por `grupo_orden`: así la
-- validación es independiente de la convención de nombres y funciona igual en
-- los productos sufi con G7/G8 abiertos. `pd_max_grupo_previo` viaja en la
-- salida para poder ver el tamaño del solapamiento, no solo su existencia.
--
-- Nota sobre la igualdad: `solapa` usa `<` estricto. Que el `pd_max` de un
-- grupo sea EXACTAMENTE igual al `pd_min` del siguiente no es solapamiento,
-- es un corte con borde inclusivo de un lado; es esperable y no se marca.
--
-- ----------------------------------------------------------------------------
-- Filtro y grano
-- ----------------------------------------------------------------------------
-- El filtro es `grupo IS NOT NULL AND pd IS NOT NULL`: el grupo porque define
-- de qué corte estamos hablando, la pd porque sin valor no hay frontera que
-- inferir. Eso saca las 726 filas con pd nula y grupo poblado, que aquí no
-- aportan.
--
-- `segmento` NO entra en el grano: los cortes son del producto, no del
-- segmento. Si un mismo producto mostrara cortes distintos por segmento, eso
-- aparecería como `solapa = true` al mirar el producto completo, que es
-- justamente la señal que esta query busca.
--
-- Sin ORDER BY a propósito: Power BI importa y ordena en el modelo. La
-- ventana de `lag` no depende del orden de salida.
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

rangos as (
  select
    l.ingestion_year,
    l.ingestion_month,
    l.producto,
    l.modelo,
    l.grupo,
    count(*)   as clientes,
    min(l.pd)  as pd_min,
    max(l.pd)  as pd_max
  from largo l
  where l.grupo is not null
    and l.pd is not null
  group by
    l.ingestion_year,
    l.ingestion_month,
    l.producto,
    l.modelo,
    l.grupo
)

select
  r.ingestion_year,
  r.ingestion_month,
  r.producto,
  r.modelo,
  r.grupo,
  r.clientes,
  r.pd_min,
  r.pd_max,
  lag(r.pd_max) over (
    partition by r.ingestion_year, r.ingestion_month, r.producto, r.modelo
    order by r.pd_min
  ) as pd_max_grupo_previo,
  r.pd_min < lag(r.pd_max) over (
    partition by r.ingestion_year, r.ingestion_month, r.producto, r.modelo
    order by r.pd_min
  ) as solapa
from rangos r;
