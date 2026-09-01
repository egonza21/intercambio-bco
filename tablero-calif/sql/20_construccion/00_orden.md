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

## Esto NO es concurrente

El `drop` + `create` deja la tabla **inexistente** durante toda la
construcción. Mientras corre:

- Si otra persona construye a la vez, las dos escrituras se pisan y el
  resultado queda indefinido.
- Si alguien tiene la app abierta y toca un filtro que fuerza relectura, le va
  a fallar la consulta con "table does not exist".

La construcción es un proceso **manual y controlado**: una persona, avisando, y
sin nadie leyendo. No hay bloqueo ni transacción que lo impida — la disciplina
es lo único que hay.

Si esto se vuelve un problema, el patrón habitual es construir en una tabla
`_nueva` y hacer el swap con dos `alter table ... rename`, que reduce la
ventana de inexistencia a milisegundos. No está implementado porque hoy la
construcción es mensual y coordinada.

## Después de construir

Correr la página **Salud del dato** de la app antes de mirar cualquier otra
cosa. Los cuatro chequeos verifican los supuestos sobre los que se apoya todo
lo demás, y el 2 (mapeo `idx` → columna) conviene activarlo explícitamente
después de una construcción: es la única defensa contra un `CASE` desalineado,
que no da error y solo etiqueta mal.
