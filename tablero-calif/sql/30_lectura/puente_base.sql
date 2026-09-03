-- ============================================================================
-- LECTURA: proceso.puente_base_{IDUNICO}
-- ----------------------------------------------------------------------------
-- Descomposición de la base por mes y segmento: permanece, entrada, salida.
-- Alimenta la cascada de Evolución.
--
-- SIN FILTROS y SIN PARÁMETROS: la app filtra en pandas.
-- ============================================================================

select
  t.ingestion_year,
  t.ingestion_month,
  t.idx_mes,
  t.segmento,
  t.categoria,
  t.clientes
from proceso.puente_base_{IDUNICO} t;
