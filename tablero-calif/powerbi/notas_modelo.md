# Notas de modelado en Power BI

Complementa la sección "Notas de modelado en Power BI" de `CLAUDE.md`. Aquí va
el detalle de cómo se arman las dimensiones y qué queda del lado de Power
Query en vez del SQL.

## Reparto de responsabilidades: SQL vs. Power Query

Los agregados de `sql/10_agregados/` son **hechos**: traen las llaves del
grano y las métricas, nada más. Todo lo que sea atributo derivado de una
llave (etiquetas, agrupaciones, órdenes) se resuelve en dimensiones armadas
en Power Query.

La razón es de tamaño y de repetición: un atributo que solo depende de
`grupo` no tiene por qué viajar repetido en cada fila del hecho, y tenerlo en
una dimensión permite cambiarlo sin volver a correr la consulta en Impala.

## dim_grupo

**`grupo_base` y `grupo_orden` NO van en los agregados.** El agregado
`distribucion_grupo.sql` lleva `grupo` como llave y nada más; las dos
derivadas viven en esta dimensión.

`grupo` tiene un dominio cerrado de 14 valores (G1–G8 planos, más las seis
aperturas de G7 y G8 de los productos sufi — ver "Apertura de G7 y G8 en los
productos sufi" en `CLAUDE.md`), así que la dimensión se declara como tabla
literal en M, sin consultar Impala:

```m
let
    dim_grupo = #table(
        type table [grupo = text, grupo_base = text, grupo_orden = Int64.Type],
        {
            {"G1",   "G1", 10},
            {"G2",   "G2", 20},
            {"G3",   "G3", 30},
            {"G4",   "G4", 40},
            {"G5",   "G5", 50},
            {"G6",   "G6", 60},
            {"G7",   "G7", 70},
            {"G7_B", "G7", 71},
            {"G7_M", "G7", 72},
            {"G7_A", "G7", 73},
            {"G8",   "G8", 80},
            {"G8_B", "G8", 81},
            {"G8_M", "G8", 82},
            {"G8_A", "G8", 83}
        }
    )
in
    dim_grupo
```

Configuración en el modelo:

- Relación 1:* desde `dim_grupo[grupo]` hacia la columna `grupo` de cada
  tabla de hechos.
- `dim_grupo[grupo]` con **Ordenar por columna** → `grupo_orden`
  (Herramientas de columna → Ordenar por columna). Sin esto Power BI ordena
  alfabéticamente y deja `G7_A, G7_B, G7_M`, con el peor grupo primero.
- `grupo_orden` **oculto**: es columna de servicio, no una medida que el
  usuario deba ver.
- `grupo_base` visible, para los visuales que necesitan la escala de 8
  categorías (migración, consistencia cross-producto).

### Cuidado: `grupo_orden` queda definido en dos lados

La escala de `grupo_orden` está tanto en esta tabla literal como en el
cálculo aritmético de `sql/_fragmentos/cte_productos.sql`. Son dos copias de
la misma decisión y hay que mantenerlas alineadas: si aparece un valor de
grupo nuevo (o cambia la convención B/M/A), hay que tocar los dos.

El reparto natural, si se mantiene el patrón de este agregado:

- **`grupo_orden` es presentacional** → su lugar es esta dim_grupo. En el SQL
  queda sin consumidor mientras ningún agregado lo seleccione.
- **`grupo_base` sí se necesita del lado servidor** para la matriz de
  migración, que tiene que unir mes N contra mes N−1 sobre una escala común
  de 8 categorías antes de agregar. Ahí no alcanza con resolverlo en el
  modelo.

Cuando se escriba el agregado de migración conviene revisar esta división y
dejar anotado cuál de las dos copias manda.

## Otras dimensiones

- **dim_producto**: `producto` (16 valores) y `familia_producto` (4), con
  jerarquía `familia_producto` → `producto` para el drill down. Tampoco viaja
  en los hechos: `familia_producto` está determinada por `producto`.
  Los valores de `familia_producto` siguen pendientes de confirmar contra la
  clasificación oficial del banco (pendiente 6 de `CLAUDE.md`).
- **dim_modelo**: versiones de `modelo_*`. Ojo con la escala de PD: el modelo
  "advanced" trae el puntaje crudo (0–999) y el resto probabilidades [0,1].
  Conviene un atributo de escala en esta dimensión para poder excluir o
  separar explícitamente los modelos que no comparten unidad.
- **dim_fecha**: construida sobre `ingestion_year` + `ingestion_month`.

## Medidas sobre `distribucion_grupo`

El agregado trae `clientes`, `clientes_con_pd`, `pd_suma`, `pd_min` y
`pd_max`. Dos trampas al escribir las medidas:

- **PD promedio ponderada = `SUM(pd_suma) / SUM(clientes_con_pd)`**, no
  `/ SUM(clientes)`. Hay un producto con 726 filas de PD nula y grupo
  poblado: esas filas cuentan en `clientes` pero no aportan a `pd_suma`.
- **Nunca sumar `pd_suma` entre modelos de escala distinta.** Como `modelo`
  está en el grano, cada fila es consistente, pero un visual que agregue
  sobre varios modelos mezcla 0–999 con 0–1 y da un número sin significado.
  Filtrar por modelo, o por el atributo de escala de dim_modelo.
