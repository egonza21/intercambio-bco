-- ============================================================================
-- Perfilado: ¿hasta qué mes llega la tabla fuente?
-- ----------------------------------------------------------------------------
-- La página de Construcción lo pone al lado del último mes construido. Si la
-- fuente va más adelante, llegó una partición nueva y hay que reconstruir.
--
-- Lleva el filtro `ingestion_day >= 15` como todo el repo (ver CLAUDE.md, "El
-- filtro de ingestion_day"): una carga parcial de principios de mes NO cuenta
-- como mes disponible. Es justo el caso que haría aparecer un mes vacío.
--
-- El `>= {DESDE}` no es un filtro de negocio: es para que Impala pode
-- particiones. Sin él, un max() sobre una columna que no es de partición
-- (ingestion_day está en el where) recorre la tabla entera. Con él, lee solo
-- las particiones desde el último mes construido en adelante, que son una o
-- dos. Si no hay nada nuevo, devuelve ese mismo mes; si no hay nada en
-- absoluto desde ahí, devuelve NULL, y eso también hay que mirarlo.
--
-- Parámetros:
--   {DESDE} -- mes desde el que buscar, en ingestion_year*12+ingestion_month
-- ============================================================================

select
  max(c.ingestion_year * 12 + c.ingestion_month) as ultimo_mes
from resultados_riesgos.maestro_calificaciones_pn c
where c.ingestion_year * 12 + c.ingestion_month >= {DESDE}
  and c.ingestion_day >= 15;
