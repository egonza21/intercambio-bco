-- ============================================================================
-- Agregado: cobertura por producto (salida ancha)
-- ----------------------------------------------------------------------------
-- Produce una fila por ingestion_year + ingestion_month + segmento con 16
-- columnas de cobertura, una por producto, más el total de clientes del
-- cruce. Alimenta el visual de cobertura por producto.
--
-- **La salida es ANCHA a propósito y se despivota en Power Query** (Anular
-- dinamización de columnas sobre las 16 `cob_*`). Así este agregado no
-- necesita el cross join contra productos: son 16 count() sobre la misma
-- pasada de la tabla ancha, sin explotar las filas x16.
--
-- Parámetros:
--   {DESDE}, {HASTA} -- rango de meses, en ingestion_year*12+ingestion_month
--
-- ----------------------------------------------------------------------------
-- Por qué la tabla ancha y no la larga
-- ----------------------------------------------------------------------------
-- La cobertura se calcula sobre la ancha porque el filtro `grupo IS NOT NULL`
-- de la larga borra justamente las filas que hay que contar como "no
-- cubierto". `count(columna)` ignora nulos, así que cada `count(g_*)` da
-- directo los clientes con calificación en ese producto, y `clientes` da el
-- denominador.
--
-- Se cuenta `g_*`, NO `pd_*`. El criterio de cobertura del tablero es tener
-- grupo, y hay un producto con 726 casos de pd nula con grupo poblado:
-- contar `pd_*` los dejaría fuera. Ver CLAUDE.md, "Filtro de nulos estándar".
--
-- ----------------------------------------------------------------------------
-- Cómo leerlo
-- ----------------------------------------------------------------------------
-- La cobertura baja de `comercial`, `micro` y `sobregiro` es ESPERADA: esos
-- productos aplican a personas naturales con pequeño negocio. No es una falla
-- del pipeline.
--
-- El nombre de la columna sigue al PRODUCTO, no al sufijo de la columna
-- fuente: `cob_rotativo` cuenta `g_rota` y `cob_sobregiro` cuenta `g_sobre`.
-- Son los dos únicos casos donde producto y sufijo no coinciden, y son el
-- lugar más probable de un desalineo al editar este archivo.
--
-- Sin ORDER BY a propósito: Power BI importa y ordena en el modelo.
-- ============================================================================

with base as (
  select
    c.ingestion_year,
    c.ingestion_month,
    c.segmento,
    c.g_consumo,
    c.g_tdc,
    c.g_libranza,
    c.g_rota,
    c.g_hip_vis,
    c.g_hip_novis,
    c.g_lea_hab_vis,
    c.g_lea_hab_novis,
    c.g_comercial,
    c.g_micro,
    c.g_sobre,
    c.g_sufi_veh,
    c.g_sufi_moto,
    c.g_sufi_cpe,
    c.g_sufi_con,
    c.g_calm
  from resultados_riesgos.maestro_calificaciones_pn c
  where c.ingestion_year * 12 + c.ingestion_month between {DESDE} and {HASTA}
)

select
  b.ingestion_year,
  b.ingestion_month,
  b.segmento,
  count(*)                  as clientes,
  count(b.g_consumo)        as cob_consumo,
  count(b.g_tdc)            as cob_tdc,
  count(b.g_libranza)       as cob_libranza,
  count(b.g_rota)           as cob_rotativo,
  count(b.g_hip_vis)        as cob_hip_vis,
  count(b.g_hip_novis)      as cob_hip_novis,
  count(b.g_lea_hab_vis)    as cob_lea_hab_vis,
  count(b.g_lea_hab_novis)  as cob_lea_hab_novis,
  count(b.g_comercial)      as cob_comercial,
  count(b.g_micro)          as cob_micro,
  count(b.g_sobre)          as cob_sobregiro,
  count(b.g_sufi_veh)       as cob_sufi_veh,
  count(b.g_sufi_moto)      as cob_sufi_moto,
  count(b.g_sufi_cpe)       as cob_sufi_cpe,
  count(b.g_sufi_con)       as cob_sufi_con,
  count(b.g_calm)           as cob_calm
from base b
group by
  b.ingestion_year,
  b.ingestion_month,
  b.segmento;
