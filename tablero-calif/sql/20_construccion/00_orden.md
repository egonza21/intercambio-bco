# Orden de ejecución

Se corre **una vez al mes**, cuando llega la partición nueva. Los scripts no
llevan parámetros: cada uno reconstruye toda la ventana disponible.

## La dependencia que importa

`01_largo_calificaciones` tiene que existir **antes** que los cuatro scripts
que leen de ella. El resto es independiente y puede correrse en cualquier
orden, o en paralelo si el clúster lo aguanta.

```
01_largo_calificaciones          ← materializa el unpivot. VA PRIMERO.
   │
   ├── 04_distribucion_grupo
   ├── 06_cortes_por_producto
   ├── 07_migracion_r1
   └── 08_migracion_r6

11_puente_base                   ← usa una tmp propia, tmp_puente_mes
02_base_clientes                 ┐
03_cobertura_producto            │  independientes: leen la tabla ancha
05_pd_por_modelo                 │  directo, no pasan por largo_calificaciones
09_migracion_pd_r1               │
10_migracion_pd_r6               ┘
```

Por qué esos cinco no dependen de `largo_calificaciones`:

- `02` y `03` necesitan las filas **sin** grupo. `largo_calificaciones` ya trae
  aplicado `grupo IS NOT NULL`, que borra justamente lo que hay que contar como
  no cubierto.
- `05`, `09` y `10` trabajan sobre las dos PD, que son del cliente y no del
  producto: su cross join es contra 2 series, no contra 16 productos. Pasar por
  la tabla larga los haría más lentos, no más rápidos.

## Secuencia completa

```
01_largo_calificaciones.sql
02_base_clientes.sql
03_cobertura_producto.sql
04_distribucion_grupo.sql
05_pd_por_modelo.sql
06_cortes_por_producto.sql
07_migracion_r1.sql
08_migracion_r6.sql
09_migracion_pd_r1.sql
10_migracion_pd_r6.sql
11_puente_base.sql
```

El prefijo numérico es el orden. Correrlos en ese orden siempre funciona.

## Forma de cada script

```sql
drop table if exists proceso.<nombre> purge;

create table proceso.<nombre>
stored as parquet
as
select ...;

compute stats proceso.<nombre>;
```

Son **tres sentencias**, no una. Si el cliente SQL o el helper no acepta varias
por llamada, hay que separarlas por `;` y ejecutarlas en secuencia.

**El `compute stats` no es opcional.** Sin estadísticas Impala elige planes de
join malos, y se nota sobre todo en las tablas que se cruzan: la migración une
`largo_calificaciones` contra sí misma y contra la base de clientes.

**El `purge` tampoco.** Sin él la tabla vieja va al trash de HDFS y el espacio
no se libera hasta que pase la retención.

## El identificador de versión

Los nombres llevan un sufijo que sale del marcador `{IDUNICO}`:

```
proceso.largo_calificaciones_vfinal
proceso.distribucion_grupo_vfinal
```

El valor sale de `IDUNICO_POR_DEFECTO` en `app/data.py`, y la página de
**Construcción** de la app lo puede cambiar por sesión.

**Construcción y lectura tienen que usar el mismo valor.** Si difieren, la app
consulta tablas que no existen. Por eso el valor vive en un solo lugar y las
dos capas lo toman de ahí.

Solo se aceptan letras, números y guion bajo: el identificador va **directo al
nombre de una tabla en un DDL**, y ahí no hay parámetro ligado que valga — no
existe forma de parametrizar un nombre de objeto. La validación es la única
defensa, y está en `data.validar_idunico()`.

## Concurrencia

El `drop` + `create` deja la tabla **inexistente** mientras dura. Pero el
identificador acota el problema: **dos personas con identificadores distintos
escriben en tablas distintas y no se pisan.**

El conflicto queda solo cuando **comparten identificador**:

- Dos construcciones simultáneas sobre el mismo identificador se pisan y el
  resultado queda indefinido.
- Alguien con la app abierta en ese identificador, que fuerce una relectura
  mientras corre, recibe "table does not exist".

Así que la regla práctica es: para probar algo, usar un identificador propio
(`v2_prueba`, `vjuan`) y no tocar el que está en uso. Reconstruir el
identificador compartido sigue siendo un acto coordinado — avisar antes.

Si algún día hace falta que ni siquiera eso interrumpa, el patrón es construir
en `_nueva` y hacer swap con dos `alter table ... rename`, que reduce la
ventana de inexistencia a milisegundos. No está implementado porque con
identificadores separados el caso ya casi no aparece.

## Los cuatro scripts de migración crean tablas temporales

`07`, `08`, `09` y `10` no son un solo `CREATE TABLE AS`: parten el trabajo en
tablas intermedias materializadas, con el prefijo `tmp_`.

```
proceso.tmp_migracion_r1_origen_<id>       proceso.tmp_migracion_pd_r1_deciles_<id>
proceso.tmp_migracion_r1_destino_<id>      proceso.tmp_migracion_pd_r1_base_<id>
proceso.tmp_migracion_r1_base_<id>         proceso.tmp_migracion_pd_r1_par_<id>
proceso.tmp_migracion_r1_par_<id>
```

**Por qué.** Encadenado en CTEs, el ETL de migración se cancelaba por memoria:
Impala no materializa los CTEs, así que el full outer join, el left join
contra la base y la agregación final quedaban todos en el mismo plan con los
intermedios en memoria. En la de PD había además un `ntile` que, por estar el
CTE referenciado dos veces, corría el sort completo **dos veces**.

**El `compute stats` de cada intermedia va antes del join que la usa.** No es
higiene: es buena parte de la ganancia. Con estadísticas Impala conoce los
tamaños y elige entre broadcast y particionado; sin ellas adivina, y un
broadcast de la tabla equivocada es justamente lo que revienta la memoria.

### Se borran solas, salvo que el script se interrumpa

Cada script borra sus intermedias al final, cuando la tabla definitiva ya
existe. **Si se interrumpe a la mitad quedan huérfanas ocupando espacio.**

Los `drop table if exists ... purge` del arranque de cada script las limpian en
la corrida siguiente, así que volver a correrlo alcanza. Para revisarlas a
mano:

```sql
show tables in proceso like 'tmp_migracion*';
```

Como llevan el sufijo del identificador, una huérfana de `v2_prueba` no
interfiere con `vfinal`: se pueden borrar sin coordinar con nadie más.

## Después de construir

Correr la página **Salud del dato** de la app antes de mirar cualquier otra
cosa. Los cuatro chequeos verifican los supuestos sobre los que se apoya todo
lo demás, y el 2 (mapeo `idx` → columna) conviene activarlo explícitamente
después de una construcción: es la única defensa contra un `CASE` desalineado,
que no da error y solo etiqueta mal.
