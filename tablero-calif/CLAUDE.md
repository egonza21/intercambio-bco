# Tablero de riesgo — calificaciones mensuales de clientes

Contexto y reglas para trabajar en este repo. Léelo completo antes de escribir SQL.

## Qué es esto

Repo de queries SQL (Impala) que alimentan un tablero de Power BI sobre las
calificaciones de riesgo que se asignan a clientes mes a mes para ofertarles
productos.

- Tabla fuente: `resultados_riesgos.maestro_calificaciones_pn`
- Cubre **personas naturales**. Los productos `comercial`, `micro` y
  `sobregiro` aplican a quienes tienen pequeño negocio, así que su cobertura
  es estructuralmente baja frente a consumo o tarjeta. **Eso es lo esperado, no
  una falla del pipeline** — importante al leer el visual de cobertura.
- Entre 15 y 17 MM de clientes por fecha de análisis, y **bajando**: ver
  "Ventana de datos y contracción de la base".
- 16 productos, cada uno con una columna de probabilidad de default (`pd`),
  una de grupo de riesgo (`g`) y una de modelo. **Pero las 16 columnas de
  `pd` no son 16 PD distintas**: solo hay dos. Ver "La PD no es por
  producto", que es lo primero que hay que entender de esta tabla.
- El grupo va de G1 a G8, salvo en `sufi_moto`, `sufi_cpe` y `sufi_con`,
  donde G7 y G8 vienen abiertos en bajo/medio/alto (`G7_B`, `G7_M`, `G7_A` y
  equivalentes en G8). Ver "Mapeo idx → producto".
- Un cliente aparece en varias fechas: se recalifica mensualmente.
- Llave de cliente: `num_doc` + `tipo_doc`.
- Partición: `ingestion_year` + `ingestion_month`. La calificación es mensual,
  así que "mes anterior" siempre es el mes calendario inmediatamente previo.

## La PD no es por producto

Verificado 2026-08-25. **Es el hallazgo estructural del repo**: cambia qué
significa cada columna y qué agregados tienen sentido.

**La tabla tiene 16 columnas `pd_*` pero solo dos PD distintas:**

| serie      | columnas                                          | productos |
|------------|---------------------------------------------------|-----------|
| `general`  | `pd_consumo` … `pd_calm`, sin las de vivienda      | los 12 no-vivienda |
| `vivienda` | `pd_hip_vis`, `pd_hip_novis`, `pd_lea_hab_vis`, `pd_lea_hab_novis` | los 4 de vivienda |

La PD se replica **idéntica** dentro de cada grupo. Es un atributo del
**cliente**, no del producto.

Lo que sí es específico del producto es el **`grupo`**: cada producto traduce
la misma PD a grupo con **sus propios cortes**. Ahí está toda la variación
entre productos, y es lo que reconstruye `cortes_por_producto.sql`.

### Qué se rompe si se ignora

- **Sumar `pd` sobre productos cuenta la misma PD hasta 12 veces**, y el
  número resultante parece razonable. Por eso `distribucion_grupo.sql` ya no
  lleva ninguna columna de PD.
- **Un histograma de PD "por producto" son 12 copias del mismo histograma**
  (más 4 del de vivienda). El grano correcto es serie × modelo, no producto.
- **`producto` no es una dimensión válida para nada que sea PD.** Si un
  visual de PD tiene producto en algún eje o filtro, está mal construido.
- Un cliente puede cambiar de grupo en un producto **sin que su PD se mueva**,
  si cambian los cortes de ese producto. Migración de grupo y migración de PD
  son fenómenos distintos: `migracion.sql` y `migracion_pd.sql`.

### Cómo se toma cada serie en el SQL

Con `COALESCE` sobre todas las columnas de su grupo, no desde una columna
representativa. Si la replicación es exacta el coalesce es inocuo; si alguna
columna llegara nula donde otra tiene valor, lo recupera. **Lo que el coalesce
no hace es detectar que la replicación dejó de cumplirse** — se queda con la
primera no nula y sigue. Si llega una carga nueva y hay dudas, comparar las
columnas entre sí antes de confiar en los agregados de PD.

## Ventana de datos y contracción de la base

Verificado 2026-08-25.

**La tabla arranca en 2025-05 y llega hasta 2026-08: 16 meses.** Un solo
`ingestion_day` por mes en los 16, sin duplicados. Cualquier `{DESDE}` menor
a `2025 * 12 + 5 = 24305` no falla, simplemente no devuelve nada.

**La base viene bajando sostenidamente: 16,6 MM en 2025-05 a 15,2 MM en
2026-08, un -9% en 16 meses.** No es un salto puntual ni un problema de
ingestión; es tendencia.

Esto tiene una consecuencia directa sobre los visuales:

- **Los visuales de composición van en porcentaje, no en conteo absoluto.**
  Si se apilan conteos, la contracción de la base se lee como si el riesgo
  estuviera mejorando: menos clientes en G6 no significa menos deterioro
  cuando hay 1,4 MM de clientes menos en total.
- **El conteo absoluto va en su propio visual**, junto a la evolución de la
  base (`base_clientes.sql`), para que la caída se vea como lo que es.
- Lo mismo aplica al leer la matriz de migración: una masa de salidas
  creciente mes a mes es consistente con esta contracción, no necesariamente
  con un cambio de comportamiento de los modelos.

## Restricciones del entorno — no negociables

1. **Sí hay permisos de escritura** en el esquema `proceso`. Se pueden crear
   tablas. Esto cambió: el repo nació sin escritura y todo se resolvía dentro
   de un `SELECT`, con cada agregado repitiendo el mismo unpivot. Ver "Las dos
   capas".
2. **Sin vistas.** No están disponibles en la plataforma.
3. **El repo no contiene datos.** Ni resultados, ni muestras, ni extractos, ni
   conteos reales. Solo código SQL y documentación. Esto NO cambió y no cambia
   porque haya escritura: las tablas viven en Impala, el repo versiona los
   scripts que las crean. Los HTML que genera la app también contienen datos y
   por eso `exportes/` está en `.gitignore`.
4. **Motor: Impala.** No Hive, no Spark SQL, no Trino. Ver la sección de
   particularidades más abajo.

## Las dos capas

El SQL tiene dos capas con **ciclos de vida distintos**, y confundirlas es el
error a evitar:

| | `sql/20_construccion/` | `sql/30_lectura/` |
|---|---|---|
| Qué hace | CREA las tablas | SELECT sobre esas tablas |
| Cuándo corre | una vez al mes, al llegar la partición | en cada carga de la app |
| Parámetros | **ninguno** | **ninguno** |
| Quién lo corre | una persona, a mano | Streamlit |
| Costo | minutos | segundos |

**Los scripts de construcción no llevan `{DESDE}` ni `{HASTA}`.** Construyen
todo el histórico disponible y la app filtra en pandas: los agregados son de
decenas de miles de filas y caben enteros en memoria. Con eso `data.py` no
sustituye marcadores, `st.cache_data` cachea una vez, y mover un selector del
sidebar es instantáneo porque no vuelve a Impala.

La excepción es la migración, por el rezago: en vez de parametrizarlo se
construyen **dos tablas**, `proceso.migracion_r1` y `proceso.migracion_r6`
(y sus equivalentes de PD). Son análisis distintos y no encadenables, así que
tenerlos como tablas separadas además lo hace explícito.

### La tabla intermedia es la ganancia principal

`proceso.largo_calificaciones` materializa el unpivot con `grupo IS NOT NULL`
ya aplicado. Antes, cada agregado repetía el mismo cross join contra los 16
productos; ahora se paga una vez por construcción. Es la razón de más peso
para tener escritura.

Cuidado con lo que **no** puede leer de ahí: la cobertura necesita las filas
SIN grupo, y los agregados de PD trabajan sobre dos series de cliente, no
sobre 16 productos. Esos cinco leen la tabla ancha directo. El detalle está en
`sql/20_construccion/00_orden.md`.

### Forma de un script de construcción

```sql
drop table if exists proceso.<nombre> purge;

create table proceso.<nombre>
stored as parquet
as
select ...;

compute stats proceso.<nombre>;
```

**El `compute stats` no es opcional.** Sin estadísticas Impala elige planes de
join malos, y se nota en las tablas que se cruzan — la migración une
`largo_calificaciones` contra sí misma y contra la base de clientes.

Son tres sentencias, no una: si el cliente no acepta varias por llamada, hay
que separarlas y ejecutarlas en secuencia.

Los CTEs internos siguen existiendo dentro de cada `CREATE TABLE AS`: la regla
de no usar subconsultas en el `FROM` se mantiene. Lo que cambia es que los
pasos intermedios ahora pueden ser tablas físicas.

### La construcción NO es concurrente

El `drop` + `create` deja la tabla **inexistente** mientras dura. Si dos
personas construyen a la vez, o alguien construye mientras la app lee, se
rompe: la segunda escritura se pisa con la primera, o la app falla con "table
does not exist".

No hay bloqueo ni transacción que lo impida. **La construcción es un proceso
manual y controlado**: una persona, avisando, y sin nadie leyendo. Si algún día
molesta, el patrón es construir en `_nueva` y hacer swap con dos
`alter table ... rename`; no está implementado porque hoy es mensual y
coordinada.

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
- **No acepta dos o más agregados `COUNT(DISTINCT)` separados en la misma
  consulta** salvo que se active `APPX_COUNT_DISTINCT`. La forma multicolumna
  `COUNT(DISTINCT col_a, col_b)` sí es válida: cuenta combinaciones distintas
  y es un solo agregado. Si la fila tiene nulo en cualquiera de las dos
  expresiones, se ignora completa.
- **El filtro de particiones va lo más adentro posible**, antes del cross join,
  para que Impala pode particiones y no lea toda la tabla.
- `COUNT(columna)` ignora nulos — es la forma directa de medir cobertura.

## Esquema de la tabla ancha

`resultados_riesgos.maestro_calificaciones_pn`

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

| idx | producto        | familia_producto | columnas                                                  |
|-----|-----------------|------------------|-----------------------------------------------------------|
| 1   | consumo         | consumo          | pd_consumo / g_consumo / modelo_consumo                   |
| 2   | tdc             | consumo          | pd_tdc / g_tdc / modelo_tdc                               |
| 3   | libranza        | consumo          | pd_libranza / g_libranza / modelo_libranza                |
| 4   | rotativo        | consumo          | pd_rota / g_rota / modelo_rota                            |
| 5   | hip_vis         | vivienda         | pd_hip_vis / g_hip_vis / modelo_hip_vis                   |
| 6   | hip_novis       | vivienda         | pd_hip_novis / g_hip_novis / modelo_hip_novis             |
| 7   | lea_hab_vis     | vivienda         | pd_lea_hab_vis / g_lea_hab_vis / modelo_lea_hab_vis       |
| 8   | lea_hab_novis   | vivienda         | pd_lea_hab_novis / g_lea_hab_novis / modelo_lea_hab_novis |
| 9   | comercial       | comercial        | pd_comercial / g_comercial / modelo_comercial             |
| 10  | micro           | comercial        | pd_micro / g_micro / modelo_micro                         |
| 11  | sobregiro       | comercial        | pd_sobre / g_sobre / modelo_sobre                         |
| 12  | sufi_veh        | sufi             | pd_sufi_veh / g_sufi_veh / modelo_sufi_veh                |
| 13  | sufi_moto       | sufi             | pd_sufi_moto / g_sufi_moto / modelo_sufi_moto             |
| 14  | sufi_cpe        | sufi             | pd_sufi_cpe / g_sufi_cpe / modelo_sufi_cpe                |
| 15  | sufi_con        | sufi             | pd_sufi_con / g_sufi_con / modelo_sufi_con                |
| 16  | calm            | consumo          | pd_calm / g_calm / modelo_calm                            |

**Los valores de `familia_producto` son una propuesta a partir de los nombres
de producto. Confirmar contra la clasificación que use el banco.** El nombre
de la columna se eligió para que no se confunda con `producto`, que es el
detalle individual.

Las dos columnas conviven y forman una jerarquía en el tablero:
`familia_producto` (4 valores) arriba, `producto` (16 valores) abajo. Un mismo
visual arranca con cuatro barras y hace drill down al detalle, sin duplicar
páginas.

### Apertura de G7 y G8 en los productos sufi

**Verificado 2026-08-25 — `sufi_moto`, `sufi_cpe` y `sufi_con` abren G7 y G8.**
En vez de un valor plano `G7`/`G8`, estos tres productos (no `sufi_veh`)
devuelven `G7_B`, `G7_M`, `G7_A` y los equivalentes `G8_*`, con severidad
ascendente: **B (bajo, mejor) < M (medio) < A (alto, peor)**. Los demás
productos usan G1-G8 planos.

El fragmento canónico expone tres columnas para lo mismo:

| columna       | qué es                                   | dónde se usa                                 |
|---------------|------------------------------------------|----------------------------------------------|
| `grupo`       | valor crudo, con apertura donde exista    | composición, heatmap segmento × grupo        |
| `grupo_base`  | apertura colapsada a G7/G8 planos         | migración 8×8, comparaciones cross-producto  |
| `grupo_orden` | entero de severidad ascendente            | orden de `grupo` en Power BI                 |

**`grupo_orden` no es opcional.** Power BI ordena las categorías de texto
alfabéticamente, y sobre `grupo` eso daría `G7_A, G7_B, G7_M`: el peor grupo
primero y el intermedio al final. Rompe el apilado de las barras de
composición y, peor, desalinea el eje de la matriz de migración — la diagonal
deja de significar estabilidad y el deterioro neto (masa bajo la diagonal
menos masa sobre ella) sale mal calculado.

La escala es decena = dígito del grupo, unidad = apertura, de modo que los
grupos planos y los abiertos ordenan entre sí sin tratamiento aparte:

```
G1 -> 10   G2 -> 20   ...   G6 -> 60   G7 -> 70   G8 -> 80
G7_B -> 71   G7_M -> 72   G7_A -> 73
G8_B -> 81   G8_M -> 82   G8_A -> 83
```

Así `G1` (10) es el menor y `G8_A` (83) el mayor, y `G6` (60) < `G7_B` (71) <
`G8_A` (83) aunque vengan de productos distintos. Se calcula por aritmética
sobre el texto de `grupo`, no con un cuarto bloque de mapeo — ver la razón en
`sql/_fragmentos/cte_productos.sql`.

`grupo_base` no necesita columna de orden: `G1`…`G8` ya ordenan igual
alfabética que numéricamente.

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
- **Migración**: `full outer join` contra el mes de referencia, con categorías
  explícitas de entrada y salida, para que la matriz reconcilie contra la base
  del mes.
- **La migración se parametriza con `{REZAGO}`, no está fija en un mes.** El
  join va contra `idx_mes - {REZAGO}`: rezago 1 da la migración mensual,
  rezago 6 la semestral. Son análisis distintos y **NO encadenables** — las
  matrices mensuales no se suman para obtener la semestral, porque un cliente
  que va G3 → G4 → G3 aporta dos movimientos en las mensuales y cero en la
  semestral. La mensual mide rotación; la semestral, desplazamiento neto.
  En Power Query son dos consultas del mismo archivo con distinto rezago fijo.
- **Los primeros `{REZAGO}` meses no tienen comparación, y eso no es un dato
  faltante.** Con la tabla arrancando en 2025-05, la primera matriz semestral
  válida es la de **2025-11**; la mensual arranca en 2025-06. Si se deja
  `{DESDE}` en el primer mes disponible, esos meses salen con todo
  clasificado como `entrada`, que es un artefacto del borde de la ventana.
  Regla: `{DESDE} >= 24305 + {REZAGO}`.
- **Filtro de nulos estándar: `grupo IS NOT NULL`, no `pd IS NOT NULL`.**
  Verificado 2026-08-25: un producto tiene 726 casos con `pd` nula y `grupo`
  poblado; en el resto de los casos ambas coinciden. `grupo` es lo que manda.
- **Los nulos NO vienen como cadena — con una excepción abierta en
  `modelo_*`.** Verificado 2026-08-25: `'NA'`, `''` y `'SIN CALIFICACION'`
  dieron 0 casos en todos los productos (`g_*` y `modelo_*`), así que para
  `g_*` `IS NULL` alcanza y el filtro `grupo IS NOT NULL` no necesita un
  `CASE` extra. Pero el 2026-09-01 se reportó un valor vacío o nulo en
  `modelo_*`, que contradice esa medición. Hasta resolverlo, el SQL normaliza
  `modelo` con `nullif(trim(modelo), '')`. Ver "El modelo vacío".
- **La deduplicación por `ingestion_day` NO se hace en SQL.** Verificado
  2026-08-25: un mes puntual llegó con dos ingestiones totales (reproceso
  controlado, una de ellas un ensayo). Fue un **caso único, ya corregido a
  mano** borrando la ingestión del ensayo de ese mes, y no se va a repetir.
  La verificación posterior sobre los 16 meses de la ventana confirma un solo
  `ingestion_day` por mes, sin duplicados. El código asume una fila por
  cliente + mes y no lleva `row_number()`.
- **`pd` no es comparable entre modelos.** Verificado 2026-08-25:
  `ADVANCE_1_1` y `ADVANCE_INCLUSION` devuelven el puntaje crudo en `pd`
  (escala 0 a 999), mientras el resto usa 0 a 1. La traducción a
  `grupo`/`grupo_base` sí llega normalizada a G1-G8 vía tablas traductoras
  externas. Cualquier histograma o cálculo de PSI sobre `pd` debe segmentar
  por `modelo`, no asumir una escala [0,1] uniforme. Ver "Modelos en escala de
  puntaje".

## Modelos y su escala

### Los ocho modelos vigentes

Verificado 2026-09-01. Son los modelos vigentes en todo el proceso de
calificación, y **aplican a los 16 productos**, no a un subconjunto: el mismo
modelo puede aparecer en cualquiera de las columnas `modelo_*`.

| modelo              | escala de `pd`   |
|---------------------|------------------|
| `ADVANCE_1_1`       | puntaje 0–999    |
| `ADVANCE_INCLUSION` | puntaje 0–999    |
| `T1_COMPORT`        | probabilidad 0–1 |
| `T1_COMPORT_NEI`    | probabilidad 0–1 |
| `T1_COMPORT_SOCIAL` | probabilidad 0–1 |
| `T2`                | probabilidad 0–1 |
| `T3_MARCAS`         | probabilidad 0–1 |
| `T_2_3`             | probabilidad 0–1 |

Además existe un **valor vacío o nulo** en `modelo_*`. No es un noveno modelo:
es la ausencia de modelo. Ver "El modelo vacío" más abajo.

Que los ocho apliquen a todos los productos es consistente con que solo haya
dos PD (ver "La PD no es por producto"): el modelo es un atributo del cliente,
igual que la PD, y las 16 columnas `modelo_*` son la misma información
replicada por familia.

### La escala es un mapeo manual

Solo los dos `ADVANCE_*` devuelven puntaje; los otros seis devuelven
probabilidad. Esa clasificación vive en el `CASE` de `escala` en
`sql/10_agregados/pd_por_modelo.sql` y **es un mapeo manual**: no hay nada en
la tabla que marque la escala de un modelo, hay que saberlo y escribirlo.

**Hay que actualizarla cuando entre un modelo nuevo en escala de puntaje.**

### El síntoma de olvidarlo no es un error

Un modelo de puntaje que no esté en la lista queda etiquetado
`probabilidad_0_1` y sus valores de 0 a 999 se binean con la escala
logarítmica pensada para probabilidades. La query corre, devuelve filas, y no
avisa nada. Lo que se ve es **un histograma con bins absurdos**: el modelo
nuevo aterriza en índices de bin positivos, junto a los negativos de las PD
reales, en el mismo eje y bajo la misma etiqueta de escala. Si aparece eso,
revisar esta lista antes que cualquier otra cosa.

`sql/00_perfilado/dominio_grupos_y_escala_pd.sql` es la query que lo detecta a
tiempo: si el `pd_max` de algún modelo pasa de 1 y no está acá, falta
agregarlo. Vale correrla cuando cambie la vigencia de modelos.

### Por qué una lista y no un patrón

La versión anterior usaba `lower(modelo) like '%advanced%'`, con "d" final,
cuando los modelos reales se llaman `ADVANCE`, sin "d". **No matcheaba
ninguno**: los dos modelos de puntaje se estaban clasificando como
probabilidad. Un patrón con comodín falla de las dos formas — no atrapa lo que
debería, y atraparía un modelo futuro con "advance" en el nombre que sí venga
en escala 0-1. La lista explícita hace imposibles ambos casos, a cambio de
tener que mantenerla.

### El modelo vacío

En `modelo_*` aparece un valor **vacío o nulo**. Semánticamente es lo mismo —
ausencia de modelo — así que el SQL lo normaliza a NULL con
`nullif(trim(modelo), '')` antes de usarlo como llave. Sin eso, `''` y `NULL`
serían dos categorías distintas en el tablero significando lo mismo, y la
cadena vacía además pasaría desapercibida en un eje.

Con la normalización, una fila sin modelo cae en la rama `else` del `CASE` de
escala y queda etiquetada `probabilidad_0_1`. **Es un supuesto, no un dato**:
seis de los ocho modelos son de probabilidad, así que es el default razonable,
pero si esas filas resultaran ser de puntaje sus bins saldrían mal igual que
con un modelo nuevo sin declarar. Vale mirar cuántas son antes de darle peso a
esa categoría en un visual.

**Esto contradice un hallazgo previo del perfilado**, que decía que `''` daba
0 casos en `modelo_*` (ver pendiente 3). Alguna de las dos observaciones es
incompleta: puede que el vacío sea NULL y no cadena, o que aparezca en meses
que la consulta de perfilado no cubrió. Correr
`sql/00_perfilado/nulos_pd_vs_grupo.sql` sobre la ventana completa lo resuelve;
mientras tanto la normalización cubre los dos casos.

## Pendientes por resolver — en este orden

El perfilado va primero porque su resultado cambia el resto del código.

1. **¿Hay más de un `ingestion_day` por mes?**
   **Resuelto 2026-08-25: no, un solo `ingestion_day` por mes en los 16
   meses de la ventana.** El reproceso controlado que había aparecido antes
   (dos ingestiones totales, una de ellas un ensayo) fue un caso único, ya
   corregido a mano borrando la ingestión del ensayo, y la verificación
   posterior sobre los 16 meses no encontró duplicados. **Sin cambio de
   código**: el fragmento canónico no lleva `row_number()`. Ver "Decisiones
   ya tomadas".
2. **¿`pd` nulo y `g` nulo coinciden siempre?**
   **Resuelto 2026-08-25: no del todo.** Un producto tiene 726 casos con `pd`
   nula y `grupo` poblado; el resto coincide. El filtro base pasa a ser
   `grupo IS NOT NULL`. Ver "Decisiones ya tomadas".
3. **¿Los nulos vienen como cadena?**
   **Resuelto para `g_*` el 2026-08-25** (0 casos de `'NA'`, `''` y
   `'SIN CALIFICACION'`), que es lo que decide el filtro `grupo IS NOT NULL`.
   **REABIERTO para `modelo_*` el 2026-09-01**: se reportó un valor vacío o
   nulo en esas columnas, que contradice la medición anterior. Falta correr
   `sql/00_perfilado/nulos_pd_vs_grupo.sql` sobre la ventana completa para
   saber si es NULL o cadena vacía, y cuántas filas son. El SQL ya normaliza
   con `nullif(trim(modelo), '')`, que cubre los dos casos, así que no
   bloquea; pero la clasificación de escala de esas filas es un supuesto.
   Ver "El modelo vacío".
4. **¿El dominio de los grupos es exactamente G1–G8?**
   **Resuelto 2026-08-25: no exactamente.** `sufi_moto`, `sufi_cpe` y
   `sufi_con` abren G7 y G8 en `G7_B/G7_M/G7_A` y `G8_B/G8_M/G8_A` (severidad
   ascendente B < M < A); los demás productos sí son G1-G8 planos. Resuelto
   con las columnas `grupo_base` y `grupo_orden` en el fragmento canónico.
   Ver "Apertura de G7 y G8 en los productos sufi".
5. **¿Las PD están en la misma escala entre productos?**
   **Resuelto 2026-08-25: no, y el eje no es el producto sino el modelo.**
   `ADVANCE_1_1` y `ADVANCE_INCLUSION` devuelven `pd` en escala 0-999; el
   resto en 0-1. Cualquier histograma o PSI sobre `pd` debe segmentar por
   `modelo`. Ver "Modelos en escala de puntaje".
6. **Confirmar los valores de `familia_producto`** con la clasificación oficial
   de productos del banco. Sigue abierto — se confirma más adelante. Por
   ahora se sigue usando la propuesta de la tabla "Mapeo idx → producto" tal
   cual, sin bloquear el resto del trabajo.

## Distinción pendiente en la matriz de migración

Un cliente puede tener grupo en un producto en un mes y nulo al siguiente sin
haberse ido del banco: dejó de calificar para ese producto. Son dos fenómenos
distintos que hay que separar en la matriz:

- **Pérdida de elegibilidad**: el cliente está en la tabla ese mes, pero sin
  grupo en ese producto. Es una decisión del modelo.
- **Salida**: el cliente no está en la tabla ese mes. Es un cambio de
  población.

Requiere cruzar contra la base de clientes del mes, no solo contra la larga.

## Visuales que alimenta el tablero

**El tablero tiene dos audiencias y se separan POR PÁGINA, no se mezclan.**
Un visual de PD no va en una página funcional y uno de composición de grupos
no va en una de modelos. El detalle de qué consulta alimenta cada bloque está
en `powerbi/notas_modelo.md`, "Dos audiencias, dos bloques de páginas".

### Páginas funcionales — equipo comercial y de negocio

La pregunta es cómo se reparte la cartera, no cómo se comporta el modelo.

Composición: distribución de `grupo` por producto (barra apilada 100%, con
drill desde `familia_producto`; en `sufi_moto`/`sufi_cpe`/`sufi_con` esto
muestra la apertura G7_B/M/A y G8_B/M/A, no solo G1-G8, y el apilado se ordena
por `grupo_orden`), heatmap segmento × grupo, distribución de cuántos
productos son ofertables por cliente.

Cobertura: % de clientes con grupo por producto, con la salvedad de
`comercial`, `micro` y `sobregiro`.

Evolución: mezcla de riesgo en el tiempo (área apilada, **en porcentaje**),
evolución de la base de clientes en su propio visual, vigencia de modelos
(% de población por versión de `modelo_*`).

Migración de grupo: matriz 8×8 sobre `grupo_base` (más entradas, salidas y
pérdida de elegibilidad), estabilidad como traza de la matriz, deterioro neto
como masa bajo la diagonal menos masa sobre ella. El agregado trae
`segmento_anterior` y `segmento_actual` por separado: un cliente que cambia de
segmento no cambió de riesgo, y sin las dos columnas aparece como pérdida y
ganancia de elegibilidad simultáneas.

Consistencia: heatmap de `grupo_base` en un producto contra `grupo_base` en
otro (para que las celdas sean comparables 8×8 incluso entre productos sufi y
no-sufi), perfil consolidado por cliente (mejor grupo, peor grupo,
dispersión).

### Páginas de modelos — seguimiento técnico

La pregunta es cómo se comporta el modelo. **Aquí `producto` no es una
dimensión válida** salvo en sensibilidad de cortes, porque solo hay dos PD.

PSI sobre las dos PD, por modelo, con umbrales en 0,1 y 0,25 (bins fijos).

Histograma de PD por serie y modelo, nunca mezclando modelos de escala
distinta.

Vigencia de modelos: % de población por versión, y fecha en que cambió.

Migración de PD por deciles: matriz 10×10 de ranking, con el mismo `{REZAGO}`
que la de grupo. **No se lee como la de grupo**: una diagonal fuerte aquí dice
que el orden se mantuvo, no que la distribución no se movió — eso lo dice el
PSI.

Sensibilidad de cortes: frontera de PD entre grupos consecutivos por producto,
y detección de rangos solapados. Es el único visual técnico donde `producto`
sí es dimensión, porque los cortes sí son por producto.

## Estructura del repo

```
sql/
  00_perfilado/      chequeos de salud del dato; van contra la tabla fuente
    duplicados_ingestion_day.sql    una ingestión por mes (pendiente 1)
    nulos_pd_vs_grupo.sql           pd vs grupo, nulos-cadena (2 y 3)
    dominio_grupos_y_escala_pd.sql  dominio de grupo, escala de pd (4 y 5)
    validacion_mapeo.sql            cuadra los 16 count(g_*) contra `largo`
  20_construccion/   CREAN las tablas de proceso. Una vez al mes, sin parámetros
    00_orden.md             secuencia y dependencias. LEER ANTES DE CORRER
    01_largo_calificaciones  el unpivot materializado. VA PRIMERO
    02..10                   un archivo por tabla
  30_lectura/        SELECT sin filtros sobre esas tablas. Es lo único que
                     llama Streamlit
  10_agregados/      HISTÓRICO: la versión parametrizada, de cuando no había
                     escritura. Ya no la usa la app
    -- páginas funcionales (negocio)
    base_clientes.sql       clientes por mes y segmento (tabla ancha)
    cobertura_producto.sql  16 count(g_*), salida ancha, despivota en M
    distribucion_grupo.sql  composición por grupo; sin PD
    migracion.sql           matriz de grupo sobre grupo_base, con {REZAGO}
    -- páginas de modelos (técnico)
    pd_por_modelo.sql       histograma y PSI de las 2 PD, bins fijos
    migracion_pd.sql        matriz de deciles de PD, con {REZAGO}
    cortes_por_producto.sql fronteras de corte y detección de solapamiento
  _fragmentos/       cte_productos.sql — copia canónica del mapeo
powerbi/
  notas_modelo.md    esquema estrella, parámetros M, relaciones
```

`validacion_mapeo.sql` es la única defensa contra un `CASE` desalineado, que
no produce error visible. Correrla después de tocar el mapeo, y sobre un mes
cualquiera antes de dar por buena una carga.

## Notas de modelado en Power BI

- Esquema estrella: dimensión producto (con `producto` y `familia_producto`),
  dimensión modelo, dimensión fecha, más las tablas de agregados como hechos.
- Jerarquía `familia_producto` → `producto` en la dimensión de producto, para
  que los visuales soporten drill down.
- **`grupo` se configura con "Ordenar por columna" contra `grupo_orden`.**
  (Herramientas de columna → Ordenar por columna → `grupo_orden`.) Sin eso
  Power BI ordena `grupo` alfabéticamente y los grupos abiertos de sufi
  quedan `G7_A, G7_B, G7_M`, con el peor grupo primero — ver "Apertura de G7 y
  G8 en los productos sufi". `grupo_orden` debe quedar oculto en el modelo:
  es una columna de servicio, no una medida que el usuario deba ver. Cada
  valor de `grupo` tiene un solo `grupo_orden`, así que la relación 1:1 que
  exige "Ordenar por columna" se cumple.
- La consulta nativa (`Value.NativeQuery`) pide aprobación cada vez que cambia
  el texto por parámetros. Se resuelve en Opciones → Seguridad, o desde la
  configuración del origen de datos.
- El refresco incremental con `RangeStart`/`RangeEnd` es frágil sobre consulta
  nativa. Si no pliega, refrescar la ventana completa: son megabytes.
- Los parámetros M dinámicos (que el usuario cambie el rango desde el reporte)
  solo funcionan en DirectQuery. En Import el rango se fija al publicar.
- La migración va como consulta aparte, con su propio parámetro de rango, para
  que no arrastre al resto del refresco.