# Notas de modelado en Power BI

Complementa la sección "Notas de modelado en Power BI" de `CLAUDE.md`. Aquí va
el detalle de cómo se arman las dimensiones, cómo se declaran los parámetros y
qué queda del lado de Power Query en vez del SQL.

## Dos audiencias, dos bloques de páginas

**El tablero atiende a dos públicos y se separan por página. No se mezclan en
un mismo lienzo.** No es una preferencia estética: las dos audiencias leen los
mismos datos con preguntas distintas, y un visual puesto en la página
equivocada se malinterpreta de forma predecible.

| | **Páginas funcionales** | **Páginas de modelos** |
|---|---|---|
| Audiencia | equipo comercial / negocio | seguimiento técnico |
| Pregunta | cómo se reparte la cartera | cómo se comporta el modelo |
| Unidad | el **grupo** (G1–G8) | la **PD** |
| Dimensiones | producto, segmento, familia | serie_pd, modelo |
| Contenido | composición por producto y segmento, cobertura, migración de grupo, evolución mensual | PSI de las dos PD, vigencia de modelos, migración de PD por deciles, sensibilidad de cortes |

### Qué consulta alimenta qué

| consulta | bloque | notas |
|---|---|---|
| `base_clientes` | funcional | denominador y evolución de la base |
| `cobertura_producto` | funcional | despivotar en Power Query |
| `distribucion_grupo` | funcional | ya no trae PD |
| `migracion_mensual` / `migracion_semestral` | funcional | matriz de grupo |
| `pd_por_modelo` | modelos | PSI e histograma |
| `migracion_pd_mensual` / `migracion_pd_semestral` | modelos | matriz de deciles |
| `cortes_por_producto` | modelos | sensibilidad de cortes |

### Por qué no se mezclan

- **`producto` no es una dimensión válida para la PD.** Solo hay dos PD (ver
  `CLAUDE.md`, "La PD no es por producto"), así que un visual de PD con
  producto en el eje muestra 12 copias del mismo histograma. En las páginas
  funcionales producto está en todos los ejes; llevar un visual de PD ahí es
  la forma más fácil de construir ese error.
- **La PD y el grupo se mueven por razones distintas.** Un cliente puede
  cambiar de grupo sin que su PD se mueva, si cambian los cortes del producto.
  Poner las dos migraciones juntas invita a leer una como explicación de la
  otra.
- **Las dos matrices se leen distinto.** La de grupo usa bandas fijas
  (`grupo_base`); la de PD usa deciles por período, que son ranking. Una
  diagonal fuerte significa cosas distintas en cada una.
- **El negocio no necesita el PSI y el equipo técnico no necesita la
  cobertura por segmento.** Mezclarlos hace que cada audiencia filtre visuales
  que no le sirven.

Lo único que comparten es el slicer de fecha y `dim_fecha`.

## Reparto de responsabilidades: SQL vs. Power Query

Los agregados de `sql/10_agregados/` son **hechos**: traen las llaves del
grano y las métricas, nada más. Todo lo que sea atributo derivado de una
llave (etiquetas, agrupaciones, órdenes) se resuelve en dimensiones armadas
en Power Query.

La razón es de tamaño y de repetición: un atributo que solo depende de
`grupo` no tiene por qué viajar repetido en cada fila del hecho, y tenerlo en
una dimensión permite cambiarlo sin volver a correr la consulta en Impala.

## Parámetros

**`{DESDE}` y `{HASTA}` se declaran como parámetros formales de Power Query**
(Administrar parámetros → Nuevo, tipo Número entero). Los valores son
`ingestion_year * 12 + ingestion_month`. La consulta nativa los sustituye como
texto dentro de `Value.NativeQuery`.

Referencia de la ventana disponible (16 meses):

| mes     | idx   |
|---------|-------|
| 2025-05 | 24305 |
| 2025-11 | 24311 |
| 2026-08 | 24320 |

**`{REZAGO}` NO es un parámetro compartido: es fijo por consulta.** Cada
consulta de migración lo lleva escrito en su propio paso, porque el rezago
define *qué análisis es* esa consulta, no un filtro que el usuario mueva.

**En Import el usuario no puede mover el rango desde el reporte.** Los
parámetros M dinámicos solo funcionan en DirectQuery. Así que:

- Se trae la **ventana completa de 16 meses** (`{DESDE}` = 24305,
  `{HASTA}` = 24320) en el refresco.
- El **slicer de fecha del reporte filtra sobre lo ya cargado**, no vuelve a
  consultar Impala.
- Cambiar el rango implica editar el parámetro y volver a publicar. No es un
  problema de volumen: son megabytes.

## dim_grupo

**Es una tabla propia, no cuelga de los agregados.** `distribucion_grupo.sql`
lleva `grupo` como llave y nada más; `grupo_base` y `grupo_orden` viven aquí.

Se crea con **Especificar datos** (Inicio → Especificar datos), no con una
consulta a Impala: el dominio es cerrado y de 14 filas, y traerlo del servidor
sería una consulta más en el refresco para un contenido que no cambia.

| grupo | grupo_base | grupo_orden |
|-------|------------|-------------|
| G1    | G1         | 10          |
| G2    | G2         | 20          |
| G3    | G3         | 30          |
| G4    | G4         | 40          |
| G5    | G5         | 50          |
| G6    | G6         | 60          |
| G7    | G7         | 70          |
| G7_B  | G7         | 71          |
| G7_M  | G7         | 72          |
| G7_A  | G7         | 73          |
| G8    | G8         | 80          |
| G8_B  | G8         | 81          |
| G8_M  | G8         | 82          |
| G8_A  | G8         | 83          |

Son **14 filas**: G1–G6 planos (6), G7 y G8 planos (2) y las seis aperturas de
los productos sufi (6). Los grupos planos G7 y G8 y sus aperturas conviven en
la misma tabla porque conviven en el dominio: un producto sufi entrega
`G7_B`, uno no-sufi entrega `G7`, y ambos tienen que resolver contra esta
dimensión.

Equivalente en M, por si conviene versionarlo en vez de dejarlo en el binario
que genera "Especificar datos":

```m
let
    dim_grupo = #table(
        type table [grupo = text, grupo_base = text, grupo_orden = Int64.Type],
        {
            {"G1",   "G1", 10}, {"G2",   "G2", 20}, {"G3",   "G3", 30},
            {"G4",   "G4", 40}, {"G5",   "G5", 50}, {"G6",   "G6", 60},
            {"G7",   "G7", 70}, {"G7_B", "G7", 71}, {"G7_M", "G7", 72},
            {"G7_A", "G7", 73}, {"G8",   "G8", 80}, {"G8_B", "G8", 81},
            {"G8_M", "G8", 82}, {"G8_A", "G8", 83}
        }
    )
in
    dim_grupo
```

Configuración en el modelo:

- Relación 1:* desde `dim_grupo[grupo]` hacia la columna `grupo` de los
  hechos cuyo grano es `grupo` (hoy, `distribucion_grupo`).
- **Aquí se configura "Ordenar por columna"**: `dim_grupo[grupo]` →
  `grupo_orden` (Herramientas de columna → Ordenar por columna). Es el único
  lugar donde se configura; los hechos no llevan orden. Sin esto Power BI
  ordena alfabéticamente y deja `G7_A, G7_B, G7_M`, con el peor grupo
  primero.
- `grupo_orden` **oculto**: es columna de servicio.
- `grupo_base` visible, para los visuales que quieran colapsar la apertura
  sin cambiar de tabla de hechos.

### dim_grupo_base, para la matriz de migración

`migracion.sql` no tiene grano `grupo` sino el par
`grupo_base_origen` / `grupo_base_destino`, así que **no resuelve contra
dim_grupo**: `grupo_base` no es único en esa tabla (tres filas comparten G7).

Necesita su propia dimensión de 8 filas, y **dos veces**, como dimensión de
rol — una para el eje origen y otra para el destino. En Power BI eso es o bien
dos consultas de Enter Data (`dim_grupo_origen`, `dim_grupo_destino`), o una
sola con dos relaciones y `USERELATIONSHIP` en las medidas. Recomendado lo
primero, que es más simple de leer en el panel de relaciones:

| grupo_base | grupo_base_orden |
|------------|------------------|
| G1         | 1                |
| G2         | 2                |
| G3         | 3                |
| G4         | 4                |
| G5         | 5                |
| G6         | 6                |
| G7         | 7                |
| G8         | 8                |

Las filas de `migracion` con `grupo_base_origen` o `grupo_base_destino` en
NULL son las entradas y salidas: no resuelven contra la dimensión y se
identifican por la columna `categoria`. Si se las quiere ver como fila o
columna extra del visual, agregar un miembro `(sin calificación)` a la
dimensión y mapearlo en Power Query; no viene del SQL a propósito, para no
ensuciar el dominio de `grupo_base`.

### Cuidado: `grupo_orden` queda definido en dos lados

La escala está tanto en esta dim_grupo como en el cálculo aritmético de
`sql/_fragmentos/cte_productos.sql`. Son dos copias de la misma decisión: si
aparece un valor de grupo nuevo, o cambia la convención B/M/A, hay que tocar
las dos.

El reparto que quedó:

- **`grupo_orden` es presentacional** → manda esta dim_grupo. En el SQL queda
  calculado pero sin consumidor, porque ningún agregado lo selecciona.
- **`grupo_base` sí se necesita del lado servidor**, y ahí manda el SQL:
  `migracion.sql` tiene que unir mes N contra mes N−{REZAGO} sobre la escala
  colapsada *antes* de agregar. Resolverlo en el modelo llegaría tarde.

## Otras dimensiones

- **dim_producto**: `producto` (16 valores) y `familia_producto` (4), con
  jerarquía `familia_producto` → `producto` para el drill down. No viaja en
  los hechos: `familia_producto` está determinada por `producto`. Los valores
  siguen pendientes de confirmar contra la clasificación oficial del banco
  (pendiente 6 de `CLAUDE.md`).
- **dim_modelo**: versiones de `modelo_*`. `pd_por_modelo` ya trae la columna
  `escala` (`probabilidad_0_1` / `puntaje_0_999`); conviene subirla a esta
  dimensión para poder filtrar por unidad sin depender del hecho.
- **dim_fecha**: sobre `ingestion_year` + `ingestion_month`. Marcarla como
  tabla de fechas. Ojo: `migracion` se relaciona por su **mes destino**.

## Consultas y su forma en Power Query

| consulta                  | origen                      | forma                                  |
|---------------------------|-----------------------------|----------------------------------------|
| `base_clientes`           | base_clientes.sql           | directa                                |
| `cobertura_producto`      | cobertura_producto.sql      | **despivotar** las 16 columnas `cob_*` |
| `distribucion_grupo`      | distribucion_grupo.sql      | directa                                |
| `migracion_mensual`       | migracion.sql, rezago 1     | directa                                |
| `migracion_semestral`     | migracion.sql, rezago 6     | directa                                |
| `pd_por_modelo`           | pd_por_modelo.sql           | directa                                |
| `migracion_pd_mensual`    | migracion_pd.sql, rezago 1  | directa                                |
| `migracion_pd_semestral`  | migracion_pd.sql, rezago 6  | directa                                |
| `cortes_por_producto`     | cortes_por_producto.sql     | directa                                |

Son **cuatro** consultas con `{REZAGO}` fijo: dos de migración de grupo y dos
de migración de PD. Las cuatro son tablas de hechos separadas.

### cobertura_producto: despivotar

Llega ancha (16 columnas `cob_*` más `clientes`). En Power Query: seleccionar
las 16 `cob_*` → Transformar → **Anular dinamización de columnas**, renombrar
a `producto` / `cubiertos`, y quitar el prefijo `cob_` para que el valor
resuelva contra `dim_producto[producto]`.

Sale ancha del SQL a propósito: así el agregado no necesita el cross join
contra productos y se resuelve con 16 `count()` sobre una sola pasada.

### migración: dos consultas, no una

`migracion_mensual` (rezago 1) y `migracion_semestral` (rezago 6) apuntan al
**mismo archivo .sql** con distinto valor sustituido. Son tablas de hechos
separadas en el modelo.

**No se combinan ni se acumulan.** Sumar seis matrices mensuales no da la
semestral: un cliente que va G3 → G4 → G3 aporta dos movimientos en las
mensuales y cero en la semestral. Ver `CLAUDE.md`, "Decisiones ya tomadas".

Cada una lleva su rango con la regla `{DESDE} >= 24305 + {REZAGO}`, para no
arrastrar los meses del borde donde no hay contra qué comparar y todo saldría
clasificado como `entrada`. Con rezago 6, `{DESDE}` = 24311 (2025-11).

La migración va con su propio parámetro de rango para que no arrastre al
resto del refresco: es la consulta más cara del repo.

## Medidas

### Sobre `distribucion_grupo`

Trae una sola métrica: `clientes`. **Ya no trae PD** — ver `CLAUDE.md`, "La PD
no es por producto": llevar `pd_suma` con `producto` en el grano hacía que
sumar sobre productos contara la misma PD hasta 12 veces.

La trampa que queda: **sumar `clientes` entre productos da pares
cliente-producto, no clientes.** Un cliente con grupo en 5 productos aporta 5.
Para contar clientes hay que fijar un producto, o usar `base_clientes`.

### Composición: siempre en porcentaje

La base cae 9% en la ventana (16,6 MM → 15,2 MM). Los visuales de composición
van en porcentaje sobre el total del mes; el conteo absoluto va en su propio
visual junto a `base_clientes`. Apilar conteos hace que la contracción de la
base se lea como mejora del riesgo. Ver `CLAUDE.md`, "Ventana de datos y
contracción de la base".

### PSI sobre `pd_por_modelo`

El agregado trae los conteos por bin; el PSI se calcula en DAX contra un
período base:

```
PSI = SUMX(bins, (p_actual - p_base) * LN(DIVIDE(p_actual, p_base)))
```

donde `p_actual` y `p_base` son la proporción del bin dentro de su período
(`clientes` del bin sobre `clientes` del período, para el mismo
`producto` + `modelo`). Umbrales en 0,1 y 0,25.

Los bins son de ancho fijo por escala (20 bins: 0,05 para probabilidad, 50
para puntaje) y los bordes no dependen del período — condición necesaria para
que el PSI signifique algo. Cuidar `DIVIDE` para los bins vacíos: un bin con
`p_base` = 0 da división por cero, y lo habitual es excluirlo o sustituirlo
por un épsilon.

El grano es `serie_pd` + `modelo`, **sin producto**: solo hay dos PD, así que
un PSI "por producto" serían 12 copias del mismo número.

### Migración de PD: no confundirla con el PSI

`migracion_pd` usa **deciles por período** (`ntile(10)` dentro de cada
serie × modelo × mes), no bandas fijas. Cada decil tiene el 10% de su mes por
construcción.

Es lo correcto para esa matriz y sería un error en el PSI:

- La matriz de deciles pregunta por **reordenamiento**: quién estaba en el
  decil más riesgoso y dónde está ahora. La diagonal es estabilidad del
  ranking.
- El PSI pregunta por **desplazamiento de la distribución**, y con bins por
  período daría siempre ~0.

**Una diagonal fuerte en la matriz de deciles NO dice que la distribución no
se movió.** Puede desplazarse entera y mantener el orden intacto. Para eso
está el PSI, que es un visual distinto en la misma página.

### Sensibilidad de cortes: `cortes_por_producto`

Trae `pd_min`, `pd_max`, `clientes` por producto × modelo × grupo, más
`pd_max_grupo_previo` y `solapa`.

La frontera de corte entre dos grupos consecutivos está entre el `pd_max` de
uno y el `pd_min` del siguiente. Ordenar los grupos por `pd_min` ascendente
reconstruye la tabla de cortes vigente ese mes.

**`solapa = true` es la señal a vigilar**: significa que dos clientes con la
misma PD quedaron en grupos distintos, y por lo tanto el corte de ese producto
**no depende solo de la PD**. Puede ser una regla de negocio legítima, pero
tiene que ser una decisión conocida. Un indicador de "productos con
solapamiento este mes" en la página de modelos alcanza para que no pase
inadvertido.

Es el único visual técnico donde `producto` sí es dimensión válida: los cortes
sí son por producto, aunque la PD no lo sea.
