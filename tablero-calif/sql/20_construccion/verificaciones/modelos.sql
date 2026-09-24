-- ============================================================================
-- VERIFICACIÓN: escala de cada modelo contra lo que trae el dato
-- ----------------------------------------------------------------------------
-- La corre la app en medio de 05_pd_por_modelo.sql, donde está el marcador
-- `-- @verificacion modelos`, apenas existe tmp_pd_escalado. No es un script
-- de construcción: vive en esta subcarpeta justamente para que el glob de
-- scripts no la tome como uno.
--
-- Devuelve el rango de PD de cada modelo. La comparación contra
-- config/modelos.csv se hace en Python (data.clasificar_modelos), que es donde
-- está la lista.
--
-- `modelo` puede venir nulo: es la ausencia de modelo (ver CLAUDE.md, "El
-- modelo vacío"). Se devuelve igual, con su rango, para que se vea.
--
-- Parámetros: ninguno. {IDUNICO} lo resuelve la app.
-- ============================================================================

select
  e.modelo,
  min(e.pd)  as pd_min,
  max(e.pd)  as pd_max,
  count(*)   as filas
from proceso.tmp_pd_escalado_{IDUNICO} e
group by e.modelo;
