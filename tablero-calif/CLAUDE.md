# Tablero de riesgo — calificaciones mensuales de clientes

Contexto y reglas para trabajar en este repo. Léelo completo antes de escribir SQL.

## Qué es esto

Repo de queries SQL (Impala) que alimentan un tablero de Power BI sobre las
calificaciones de riesgo que se asignan a clientes mes a mes para ofertarles
productos.

- ~15 MM de clientes por fecha de análisis.
- 16 productos, cada uno con su probabilidad de default (`pd`), su grupo de
  riesgo (`g`, de G1 a G8) y el modelo que produjo esa PD.
- Un cliente aparece en varias fechas: se recalifica mensualmente.
- Llave de cliente: `num_doc` + `tipo_doc`.
- Partición: `ingestion_year` + `ingestion_month`. La calificación es mensual,
  así que "mes anterior" siempre es el mes calendario inmediatamente previo.

## Restricciones del entorno — no negociables

1. **Sin permisos de escritura.** No hay `CREATE TABLE`, `INSERT`, ni tablas
   temporales en ninguna zona. Todo se resuelve dentro de un `SELECT`.
2. **Sin vistas.** No están disponibles en la plataforma.
3. **El repo no contiene datos.** Ni resultados, ni muestras, ni extractos, ni
   conteos reales. Solo código SQL y documentación. Las queries se escriben y
   versionan aquí, pero se ejecutan en otro entorno.
4. **Motor: Impala.** No Hive, no Spark SQL, no Trino. Ver la sección de
   particularidades más abajo.

## Reglas de código SQL

- **Nunca `SELECT *`.** Siempre columnas explícitas.
- **Nunca subconsultas en el `FROM`.** Usar CTEs con `WITH`.
- Calificar las columnas con el alias de su tabla o CTE.
- `GROUP BY` con nombres de columna explícitos, no ordinales.
- Un archivo `.sql` por consulta, con un comentario de encabezado que diga qué
  produce y qué parámetros espera.
- Los parámetros de rango de meses se marcan como `{DESDE}` y `{HASTA}` en el
  SQL; Power Query los sustituye por texto.

## Particularidades de Impala a tener presentes

- **No existe `stack()`** (es UDTF de Hive) ni `LATERAL VIEW EXPLODE` sobre
  arreglos construidos en línea. El unpivot se hace con `CROSS JOIN` contra un
  CTE de productos más `CASE`.
- **`CROSS JOIN` debe ser explícito.** El producto cartesiano implícito está
  bloqueado.
- **Los CTEs no se materializan.** Impala los inlinea en el plan; referenciar
  el mismo CTE dos veces lo ejecuta dos veces. Importa en la matriz de
  migración, que toca la tabla dos veces.
- **El nombre de un CTE no puede chocar** con una tabla existente en la base
  activa. Verificar antes de fijar nombres.
- **No acepta dos `COUNT(DISTINCT)` en la misma consulta** salvo que se active
  `APPX_COUNT_DISTINCT`. Usar `NDV()` si hace falta aproximado, o reformular.
- **El filtro de particiones va lo más adentro posible**, antes del cross join,
  para que Impala pode particiones y no lea toda la tabla.
- `COUNT(columna)` ignora nulos — es la forma directa de medir cobertura.

## Esquema de la tabla ancha

Tabla fuente: `calificaciones` (nombre real por confirmar).

```
num_doc           bigint    Número de identificación de 15 caracteres
tipo_doc          tinyint   Tipo identificación del cliente
segmento          string    Segmento al que pertenece el cliente
pd_consumo        double    Probabilidad default consumo
g_consumo         string    Grupo riesgo consumo
modelo_consumo    string    Modelo consumo
pd_tdc            double    Probabilidad default tarjeta de credito
g_tdc             string    Grupo riesgo tarjeta de credito
modelo_tdc        string    Modelo tarjeta de credito
pd_libranza       double    Probabilidad default libranza
g_libranza        string    Grupo riesgo libranza
modelo_libranza   string    Modelo libranza
pd_rota           double    Probabilidad default rotativo
g_rota            string    Grupo riesgo rotativo
modelo_rota       string    Modelo rotativo
pd_hip_vis        double    Probabilidad default hipotecario vis
g_hip_vis         string    Grupo riesgo hipotecario vis
modelo_hip_vis    string    Modelo hipotecario vis
pd_hip_novis      double    Probabilidad default hipotecario no vis
g_hip_novis       string    Grupo riesgo hipotecario no vis
modelo_hip_novis  string    Modelo hipotecario no vis
pd_lea_hab_vis    double    Probabilidad default leasing habitacional vis
g_lea_hab_vis     string    Grupo riesgo leasing habitacional vis
modelo_lea_hab_vis    string    Modelo leasing habitacional vis
pd_lea_hab_novis      double    Probabilidad default leasing habitacional no vis
g_lea_hab_novis       string    Grupo riesgo leasing habitacional no vis
modelo_lea_hab_novis  string    Modelo leasing habitacional no vis
pd_comercial      double    Probabilidad default comercial
g_comercial       string    Grupo riesgo comercial
modelo_comercial  string    Modelo comercial
pd_micro          double    Probabilidad default micro credito
g_micro           string    Grupo riesgo micro credito
modelo_micro      string    Modelo micro credito
pd_sobre          double    Probabilidad default sobregiro
g_sobre           string    Grupo riesgo sobregiro
modelo_sobre      string    Modelo sobregiro
pd_sufi_veh       double    Probabilidad default sufi vehiculo
g_sufi_veh        string    Grupo riesgo sufi vehiculo
modelo_sufi_veh   string    Modelo sufi vehiculo
pd_sufi_moto      double    Probabilidad default sufi moto
g_sufi_moto       string    Grupo riesgo sufi moto
modelo_sufi_moto  string    Modelo sufi moto
pd_sufi_cpe       double    Probabilidad default sufi cartera para estudiante
g_sufi_cpe        string    Grupo riesgo sufi cartera para estudiante
modelo_sufi_cpe   string    Modelo sufi cartera para estudiante
pd_sufi_con       double    Probabilidad default sufi consumo
g_sufi_con        string    Grupo riesgo sufi consumo
modelo_sufi_con   string    Modelo sufi consumo
pd_calm           double    Probabilidad default credito a la mano
g_calm            string    Grupo riesgo credito a la mano
modelo_calm       string    Modelo credito a la mano
ingestion_day     tinyint   Día de ingestión
ingestion_year    smallint  Año de ingestión y campo partición
ingestion_month   tinyint   Mes de ingestión y campo partición
```

## Mapeo idx → producto — fuente de verdad

Este mapeo se repite en cada archivo que hace unpivot. **Es el punto más
frágil del repo**: si un `CASE ... WHEN` queda desalineado, la query no falla,
simplemente etiqueta mal los datos. La copia canónica vive en
`sql/_fragmentos/cte_productos.sql` y cualquier cambio debe propagarse a todos
los archivos que lo usen.

| idx | producto        | columnas                                                       | familia    |
|-----|-----------------|----------------------------------------------------------------|------------|
| 1   | consumo         | pd_consumo / g_consumo / modelo_consumo                        | consumo    |
| 2   | tdc             | pd_tdc / g_tdc / modelo_tdc                                    | consumo    |
| 3   | libranza        | pd_libranza / g_libranza / modelo_libranza                     | consumo    |
| 4   | rotativo        | pd_rota / g_rota / modelo_rota                                 | consumo    |
| 5   | hip_vis         | pd_hip_vis / g_hip_vis / modelo_hip_vis                        | vivienda   |
| 6   | hip_novis       | pd_hip_novis / g_hip_novis / modelo_hip_novis                  | vivienda   |
| 7   | lea_hab_vis     | pd_lea_hab_vis / g_lea_hab_vis / modelo_lea_hab_vis            | vivienda   |
| 8   | lea_hab_novis   | pd_lea_hab_novis / g_lea_hab_novis / modelo_lea_hab_novis      | vivienda   |
| 9   | comercial       | pd_comercial / g_comercial / modelo_comercial                  | comercial  |
| 10  | micro           | pd_micro / g_micro / modelo_micro                              | comercial  |
| 11  | sobregiro       | pd_sobre / g_sobre / modelo_sobre                              | comercial  |
| 12  | sufi_veh        | pd_sufi_veh / g_sufi_veh / modelo_sufi_veh                     | sufi       |
| 13  | sufi_moto       | pd_sufi_moto / g_sufi_moto / modelo_sufi_moto                  | sufi       |
| 14  | sufi_cpe        | pd_sufi_cpe / g_sufi_cpe / modelo_sufi_cpe                     | sufi       |
| 15  | sufi_con        | pd_sufi_con / g_sufi_con / modelo_sufi_con                     | sufi       |
| 16  | calm            | pd_calm / g_calm / modelo_calm                                 | consumo    |

**La columna `familia` es una suposición a partir de los nombres. Confirmar
antes de usarla en el tablero.**

## Decisiones ya tomadas

- **La tabla larga no se materializa.** El unpivot es un CTE dentro de cada
  query de agregado. Power BI nunca consume detalle a nivel cliente.
- **Power BI consume agregados**, del orden de decenas de miles de filas por
  ventana de meses. Importados, no DirectQuery.
- **Filtro de meses parametrizado** con `ingestion_year * 12 + ingestion_month`
  entre `{DESDE}` y `{HASTA}`. Evita `date_add` y funciona como llave de
  partición.
- **Nulos por producto son normales**: un cliente no califica para los 16
  productos. El cross join genera 16 filas por cliente y el filtro de nulos
  descarta las que no aplican. Un cliente con solo consumo y tarjeta aporta 2
  filas, no 16.
- **La base de clientes se cuenta aparte**, sobre la tabla ancha. En la tabla
  larga `COUNT(*)` cuenta pares cliente-producto, no clientes.
- **La cobertura se calcula sobre la tabla ancha**, porque el filtro de nulos
  la borra de la larga.
- **Migración**: `full outer join` contra el mes anterior, con categorías
  explícitas de entrada y salida, para que la matriz reconcilie contra la base
  del mes.

## Pendientes por resolver — en este orden

El perfilado va primero porque su resultado cambia el resto del código.

1. **¿Hay más de un `ingestion_day` por mes?** Si sí, hay que deduplicar con
   `row_number()` quedándose con el último día, antes del cross join. Si no,
   esa window sobre 15 MM de filas se omite.
2. **¿`pd` nulo y `g` nulo coinciden siempre?** Si hay filas con PD nula y
   grupo poblado (o al revés), el criterio de filtro cambia a
   `grupo IS NOT NULL`, que es lo que manda para el tablero.
3. **¿Los nulos vienen como cadena?** En columnas `string` como `g_*` y
   `modelo_*` es frecuente encontrar `'NA'`, `''`, `'SIN CALIFICACION'`.
   `IS NULL` no los atrapa.
4. **¿El dominio de los grupos es exactamente G1–G8?** Cualquier valor fuera de
   ese rango necesita una decisión explícita: categoría propia o descarte.
   Afecta a todos los porcentajes del tablero.
5. **¿Las PD están en la misma escala entre productos?** Si unas van de 0 a 1 y
   otras de 0 a 100, los bins del histograma y el cálculo de PSI se rompen.

## Distinción pendiente en la matriz de migración

Un cliente puede tener grupo en un producto en un mes y nulo al siguiente sin
haberse ido del banco: dejó de calificar para ese producto. Son dos fenómenos
distintos que hay que separar en la matriz:

- **Pérdida de elegibilidad**: el cliente está en `calificaciones` ese mes,
  pero sin grupo en ese producto. Es una decisión del modelo.
- **Salida**: el cliente no está en `calificaciones` ese mes. Es un cambio de
  población.

Requiere cruzar contra la base de clientes del mes, no solo contra la larga.

## Visuales que alimenta el tablero

Composición: distribución G1–G8 por producto (barra apilada 100%), heatmap
segmento × grupo, cobertura por producto, histograma de PD por modelo,
distribución de cuántos productos son ofertables por cliente.

Evolución: mezcla de riesgo en el tiempo (área apilada), PD promedio ponderada
por producto, PSI por modelo con umbrales en 0.1 y 0.25, vigencia de modelos
(% de población por versión de `modelo_*`).

Migración: matriz 8×8 (más entradas y salidas), estabilidad como traza de la
matriz, deterioro neto como masa bajo la diagonal menos masa sobre ella.

Consistencia: heatmap de grupo en un producto contra grupo en otro, perfil
consolidado por cliente (mejor grupo, peor grupo, dispersión).

## Estructura del repo

```
sql/
  00_perfilado/      resuelve los pendientes de arriba; va primero
  10_agregados/      lo que consume Power BI
  _fragmentos/       cte_productos.sql — copia canónica del mapeo
powerbi/
  notas_modelo.md    esquema estrella, parámetros M, relaciones
```

## Notas de modelado en Power BI

- Esquema estrella: dimensión producto, dimensión modelo, dimensión fecha, más
  las tablas de agregados como hechos.
- La consulta nativa (`Value.NativeQuery`) pide aprobación cada vez que cambia
  el texto por parámetros. Se resuelve en Opciones → Seguridad, o desde la
  configuración del origen de datos.
- El refresco incremental con `RangeStart`/`RangeEnd` es frágil sobre consulta
  nativa. Si no pliega, refrescar la ventana completa: son megabytes.
- Los parámetros M dinámicos (que el usuario cambie el rango desde el reporte)
  solo funcionan en DirectQuery. En Import el rango se fija al publicar.
- La migración va como consulta aparte, con su propio parámetro de rango, para
  que no arrastre al resto del refresco.