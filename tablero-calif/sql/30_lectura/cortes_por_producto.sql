-- ============================================================================
-- LECTURA: proceso.cortes_por_producto_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Fronteras de corte de PD por producto y grupo, con la marca de solapamiento.
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
  t.producto,
  t.modelo,
  t.grupo,
  t.clientes,
  t.pd_min,
  t.pd_max,
  t.pd_max_grupo_previo,
  t.solapa
from proceso.cortes_por_producto_{IDUNICO} t;
