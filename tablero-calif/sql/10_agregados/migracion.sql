-- ============================================================================
-- Agregado: matriz de migración de grupo de riesgo, con rezago parametrizable
-- ----------------------------------------------------------------------------
-- Produce una fila por
--   mes destino + segmento_anterior + segmento_actual + producto +
--   grupo_base_origen + grupo_base_destino + categoria
-- con el conteo de clientes. Alimenta la matriz 8x8, la estabilidad (traza de
-- la matriz) y el deterioro neto (masa bajo la diagonal menos masa sobre
-- ella).
--
-- ----------------------------------------------------------------------------
-- Dos columnas de segmento, no una coalescida
-- ----------------------------------------------------------------------------
-- `segmento_anterior` (el del mes origen) y `segmento_actual` (el del mes
-- destino) viajan por separado. Con una sola columna coalescida se pierde el
-- cambio de segmento, y eso importa: **un cliente que cambia de segmento no
-- cambió de riesgo**, pero al filtrar la matriz por un segmento aparece
-- saliendo de uno y entrando al otro, indistinguible de una pérdida y una
-- ganancia de elegibilidad reales.
--
-- Con las dos columnas se aísla con `segmento_anterior <> segmento_actual`,
-- y se puede elegir entre mirar la migración a segmento constante o incluir
-- los movimientos entre segmentos.
--
-- En las filas de `entrada` el `segmento_anterior` queda NULL, y en las de
-- `salida` el `segmento_actual`: no hay mes del otro lado de donde sacarlo.
--
-- Parámetros:
--   {DESDE}, {HASTA} -- rango de meses DESTINO, en ingestion_year*12+ingestion_month
--   {REZAGO}         -- meses hacia atrás contra los que se compara
--
-- ----------------------------------------------------------------------------
-- {REZAGO}: mensual y semestral son análisis distintos, NO encadenables
-- ----------------------------------------------------------------------------
-- El join va contra `idx_mes - {REZAGO}`, no contra `idx_mes - 1`. Con
-- {REZAGO} = 1 da la migración mensual; con {REZAGO} = 6, la semestral.
--
-- **Las matrices mensuales NO se suman para obtener la semestral.** Un
-- cliente que va G3 -> G4 -> G3 aporta dos movimientos en las mensuales y
-- cero en la semestral. Son preguntas distintas: la mensual mide rotación,
-- la semestral mide desplazamiento neto a seis meses. En Power Query van
-- como DOS consultas separadas apuntando a este mismo archivo, cada una con
-- su valor de rezago fijo (ver powerbi/notas_modelo.md).
--
-- **Ventana sin comparación.** El origen sale de `idx_mes - {REZAGO}`, así
-- que los primeros {REZAGO} meses de la tabla no tienen contra qué
-- compararse. La tabla arranca en 2025-05: con {REZAGO} = 6 la primera
-- matriz semestral válida es la de 2025-11. Si se deja {DESDE} en el primer
-- mes disponible, esos meses salen con TODO clasificado como 'entrada', que
-- es un artefacto del borde, no un dato. Poner
-- {DESDE} >= primer_mes_disponible + {REZAGO}.
--
-- ----------------------------------------------------------------------------
-- Las cuatro categorías
-- ----------------------------------------------------------------------------
-- Un grupo que aparece o desaparece tiene dos causas distintas que hay que
-- separar (CLAUDE.md, "Distinción pendiente en la matriz de migración"):
--
--   movimiento             el cliente tiene grupo en los dos meses.
--                          grupo_base_origen y grupo_base_destino poblados.
--                          Es la matriz propiamente dicha; la diagonal es
--                          estabilidad.
--   entrada                no estaba en la tabla en el mes origen. Cambio de
--                          población. grupo_base_origen NULL.
--   ganancia_elegibilidad  estaba en la tabla en el mes origen, pero sin
--                          grupo en ESE producto. Decisión del modelo, no
--                          cambio de población. grupo_base_origen NULL.
--   salida                 no está en la tabla en el mes destino. Cambio de
--                          población. grupo_base_destino NULL.
--   perdida_elegibilidad   está en la tabla en el mes destino, pero sin grupo
--                          en ESE producto. Decisión del modelo.
--                          grupo_base_destino NULL.
--
-- Distinguir salida de perdida_elegibilidad (y entrada de
-- ganancia_elegibilidad) exige cruzar contra la base de clientes del mes, no
-- solo contra la larga: por eso el CTE `base_mes`.
--
-- ----------------------------------------------------------------------------
-- grupo_base como llave del grano
-- ----------------------------------------------------------------------------
-- `grupo_base` aparece en la salida porque ES el eje de la matriz, no un
-- atributo derivado que viaje al lado de `grupo`. La regla de dejar
-- grupo_base y grupo_orden fuera de los agregados aplica a los hechos cuyo
-- grano es `grupo`; aquí el grano es el par origen-destino en la escala
-- colapsada de 8 categorías, que es la única forma de que un producto sufi
-- (con G7/G8 abiertos en B/M/A) sea comparable contra uno que no lo está, y
-- de que la matriz sea 8x8 y no 14x14.
--
-- `grupo_orden` NO va: el orden de los ejes sale de la dimensión. Ojo con que
-- esa dimensión no es la dim_grupo de 14 filas (llave `grupo`), sino una de 8
-- filas sobre `grupo_base`, y hace falta dos veces (origen y destino) como
-- dimensión de rol. Ver powerbi/notas_modelo.md.
--
-- Los lados sin contraparte quedan con grupo_base NULL, no con un centinela:
-- `categoria` ya dice qué son, y un centinela ensuciaría el dominio de
-- grupo_base.
--
-- ----------------------------------------------------------------------------
-- Costo: esta query toca la tabla tres veces
-- ----------------------------------------------------------------------------
-- Impala no materializa los CTEs, los inlinea. `calificados` se referencia
-- dos veces (destino y origen), así que el unpivot corre dos veces; `base_mes`
-- agrega una tercera lectura, esa sí barata porque solo lee tres columnas.
-- Es inherente a un self-join sin tablas temporales, y CLAUDE.md ya lo
-- anticipa. Es la query más cara del repo: medirla aparte.
--
-- El filtro de partición se amplía {REZAGO} meses hacia atrás respecto de los
-- demás agregados, porque el mes origen tiene que entrar en la lectura.
--
-- Contra la copia canónica de sql/_fragmentos/cte_productos.sql esta copia
-- difiere en dos cosas: ese filtro, y que `largo` se queda solo con las
-- columnas que la query usa (sin `grupo_orden`, sin `pd`, sin
-- `familia_producto`). **Los tres bloques `case p.idx` del mapeo sí son
-- idénticos**, que es lo único que tiene que mantenerse alineado entre
-- copias y lo que valida sql/00_perfilado/validacion_mapeo.sql.
--
-- `count(*)` cuenta clientes: el full outer join es sobre
-- cliente + producto + mes, que es llave única a cada lado, así que cada
-- cliente-producto aporta una sola fila. El left join contra `base_mes`
-- tampoco multiplica, porque hay una sola fila por cliente + mes.
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
  where c.ingestion_year * 12 + c.ingestion_month
        between {DESDE} - {REZAGO} and {HASTA}
),

-- Solo `grupo_base`, que es el eje de la matriz. `grupo_orden` NO se calcula:
-- esta query no lo selecciona, y sería aritmética sobre las ~240 MM de
-- expansiones del cross join para nada. El orden de los ejes sale de la
-- dimensión en Power BI.
largo as (
  select
    r.num_doc,
    r.tipo_doc,
    r.ingestion_year,
    r.ingestion_month,
    r.segmento,
    r.producto,
    r.grupo,
    regexp_replace(r.grupo, '_[BMA]$', '') as grupo_base
  from largo_raw r
),

-- ----------------------------------------------------------------------------
-- Filas con calificación vigente, en cualquier mes de la ventana ampliada.
-- Se referencia dos veces más abajo (destino y origen): ahí está el doble
-- costo del unpivot.
-- ----------------------------------------------------------------------------

calificados as (
  select
    l.num_doc,
    l.tipo_doc,
    l.segmento,
    l.producto,
    l.ingestion_year * 12 + l.ingestion_month as idx_mes,
    l.grupo_base
  from largo l
  where l.grupo is not null
),

destino as (
  select
    c.num_doc,
    c.tipo_doc,
    c.segmento,
    c.producto,
    c.idx_mes,
    c.grupo_base
  from calificados c
  where c.idx_mes between {DESDE} and {HASTA}
),

-- `idx_mes_destino` deja el join como igualdad simple contra destino.idx_mes.
origen as (
  select
    c.num_doc,
    c.tipo_doc,
    c.segmento,
    c.producto,
    c.idx_mes + {REZAGO} as idx_mes_destino,
    c.grupo_base
  from calificados c
  where c.idx_mes between {DESDE} - {REZAGO} and {HASTA} - {REZAGO}
),

-- ----------------------------------------------------------------------------
-- Presencia del cliente en la tabla, mes a mes. Lee solo tres columnas de la
-- tabla ancha, sin cross join: es lo que permite separar un cambio de
-- población (entrada / salida) de una decisión del modelo
-- (ganancia_elegibilidad / perdida_elegibilidad).
-- ----------------------------------------------------------------------------

base_mes as (
  select
    c.num_doc,
    c.tipo_doc,
    c.ingestion_year * 12 + c.ingestion_month as idx_mes
  from resultados_riesgos.maestro_calificaciones_pn c
  where c.ingestion_year * 12 + c.ingestion_month
        between {DESDE} - {REZAGO} and {HASTA}
),

-- ----------------------------------------------------------------------------
-- `idx_mes_presencia` es el mes cuya presencia hay que verificar, y depende
-- del lado que falte: si no hay destino, se pregunta por el mes destino; si
-- no hay origen, por el mes origen. Para los movimientos queda NULL y el
-- left join no encuentra nada, que es lo correcto porque no se usa.
-- ----------------------------------------------------------------------------

par as (
  select
    coalesce(d.num_doc,  o.num_doc)          as num_doc,
    coalesce(d.tipo_doc, o.tipo_doc)         as tipo_doc,
    coalesce(d.producto, o.producto)         as producto,
    o.segmento                               as segmento_anterior,
    d.segmento                               as segmento_actual,
    coalesce(d.idx_mes,  o.idx_mes_destino)  as idx_mes_destino,
    o.grupo_base                             as grupo_base_origen,
    d.grupo_base                             as grupo_base_destino,
    case
      when d.num_doc is null then o.idx_mes_destino
      when o.num_doc is null then d.idx_mes - {REZAGO}
    end                                      as idx_mes_presencia
  from destino d
  full outer join origen o
    on  d.num_doc  = o.num_doc
    and d.tipo_doc = o.tipo_doc
    and d.producto = o.producto
    and d.idx_mes  = o.idx_mes_destino
),

clasificado as (
  select
    p.producto,
    p.segmento_anterior,
    p.segmento_actual,
    p.idx_mes_destino,
    cast(floor((p.idx_mes_destino - 1) / 12) as smallint) as ingestion_year,
    p.grupo_base_origen,
    p.grupo_base_destino,
    case
      when p.grupo_base_origen is not null
       and p.grupo_base_destino is not null       then 'movimiento'
      when p.grupo_base_origen is null
       and b.num_doc is null                      then 'entrada'
      when p.grupo_base_origen is null            then 'ganancia_elegibilidad'
      when b.num_doc is null                      then 'salida'
      else                                             'perdida_elegibilidad'
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
  c.segmento_anterior,
  c.segmento_actual,
  c.producto,
  c.grupo_base_origen,
  c.grupo_base_destino,
  c.categoria,
  count(*) as clientes
from clasificado c
group by
  c.ingestion_year,
  c.idx_mes_destino,
  c.segmento_anterior,
  c.segmento_actual,
  c.producto,
  c.grupo_base_origen,
  c.grupo_base_destino,
  c.categoria;
