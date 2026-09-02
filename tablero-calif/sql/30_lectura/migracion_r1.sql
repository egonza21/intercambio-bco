-- ============================================================================
-- LECTURA: proceso.migracion_r1_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Matriz de migración de grupo, rezago 1 mes: mide ROTACIÓN.
--
-- SIN FILTROS y SIN PARÁMETROS a propósito. Se trae la tabla entera y la app
-- filtra en pandas: son decenas de miles de filas, caben en memoria de sobra,
-- y así st.cache_data cachea una vez y los filtros del sidebar salen
-- instantáneos porque no vuelven a Impala.
--
-- Columnas explícitas y no `select *`, por la regla del repo. Acá cumple una
-- función extra: si la construcción cambia el esquema, esta consulta falla
-- ruidosamente en vez de arrastrar una columna nueva o perder una vieja en
-- silencio.
--
-- La construye sql/20_construccion/. Si falla con "table does not exist", o la
-- construcción no se corrió, o está corriendo justo ahora: el drop/create deja
-- la tabla inexistente mientras dura.
-- ============================================================================

select
  t.ingestion_year,
  t.ingestion_month,
  t.idx_mes,
  t.segmento_anterior,
  t.segmento_actual,
  t.producto,
  t.grupo_base_origen,
  t.grupo_base_destino,
  t.modelo_anterior,
  t.modelo_actual,
  t.categoria,
  t.clientes
from proceso.migracion_r1_{IDUNICO} t;
