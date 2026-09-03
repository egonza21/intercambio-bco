# Tablero de calificaciones de riesgo

Repo de queries SQL (Impala) más una app de Streamlit para el seguimiento de
los modelos de calificación de clientes.

- `CLAUDE.md` — contexto, restricciones y hallazgos del perfilado. **Leerlo
  antes de tocar SQL.**
- `sql/` — las consultas. Es la fuente de verdad de los datos.
- `app/` — el Streamlit y el exportador a HTML.
- `powerbi/notas_modelo.md` — notas del modelo de Power BI, que consume los
  mismos agregados.

## Construir las tablas

**Se corre una vez al mes**, cuando llega la partición nueva. Antes de la app:
si las tablas no existen, la app no arranca.

```bash
# en orden; el prefijo numérico ES el orden
for f in sql/20_construccion/*.sql; do
    echo "== $f"
    impala-shell -f "$f"      # o el cliente que uses
done
```

**Ningún script usa CTEs**: cada paso intermedio es una tabla física con
prefijo `tmp_`, que se borra al final. Eso multiplica las sentencias — la
construcción completa son **169** repartidas en once scripts, de 3 en los más
simples a 31 en los de migración de PD. Si el cliente no acepta varias por
llamada hay que separarlas por `;` y ejecutarlas en secuencia; `impala-shell -f`
lo hace solo. El detalle por script está en `00_orden.md`.

`01_largo_calificaciones` tiene que existir antes que los cuatro scripts que
leen de ella. El detalle de dependencias está en
`sql/20_construccion/00_orden.md`.

También se puede correr **desde la app**, en la página **Construcción**: tiene
el estado de cada tabla (si existe, cuántas filas, hasta qué mes llega), un
botón por script y uno para todo, con log y barra de progreso. Si un script
falla se detiene ahí, porque los que siguen pueden depender de él.

### El identificador de versión

Las tablas llevan un sufijo: `proceso.distribucion_grupo_vfinal`. Sale de
`IDUNICO_POR_DEFECTO` en `app/data.py` y se puede cambiar desde la página de
Construcción, para armar una versión de prueba sin tocar la que está en uso.

> **Construcción y lectura tienen que usar el mismo identificador**, o la app
> lee tablas que no existen.

> El `drop`+`create` deja cada tabla inexistente mientras dura, pero dos
> personas con identificadores **distintos** no se pisan. El conflicto solo
> aparece si comparten identificador: ahí conviene avisar antes.

Después de construir, abrir la página **Salud del dato** y activar el chequeo
de mapeo: es la única defensa contra un `CASE` desalineado, que no da error.

## Correr la app

```bash
python -m venv .venv && source .venv/bin/activate
pip install streamlit plotly pandas numpy    # más la librería `helper` del banco
streamlit run app/main.py
```

Requiere Streamlit 1.36 o superior (usa `st.navigation`).

La app se conecta a Impala a través de la librería interna `helper`. Esa
llamada está aislada en **una sola función** de `app/data.py`, en el bloque
marcado con un recuadro de comentarios. Si la firma real difiere, se ajusta ahí
y en ningún otro lado:

```python
DSN = "impala-virtual-prd"
USUARIO = "efgon"
FORMATO_PARAMETRO = "{{{nombre}}}"   # cambiar si el helper usa otro estilo
```

Los agregados se cachean una hora (`@st.cache_data`). Para forzar una
relectura: tecla `C` en la app, o «Clear cache» en el menú.

## Exportar el HTML para las revisiones

```bash
python app/export.py --desde 202505 --hasta 202608 --mes 202608 --rezago 1
```

Deja un archivo en `exportes/`, con la fecha de generación en el nombre. Se
abre con doble clic: no necesita servidor, ni Python, ni red. `plotly.js` va
embebido en el propio archivo porque la red del banco puede no alcanzar el CDN.

El HTML arranca con la sección de **salud del dato**, con el estado de los
cuatro chequeos al momento de generarlo: quien abra el reporte sabe si los
números que va a mirar son confiables antes de mirarlos.

El export **siempre ejecuta los cuatro chequeos**, incluido el de mapeo, sin
importar lo que esté tildado en la app. Un archivo que afirma que todo está
bien sin haber corrido un chequeo está diciendo algo que no verificó, y el
export se genera una vez al mes: la lentitud ahí no importa.

> **Los HTML contienen datos.** Son agregados, pero son datos igual. `exportes/`
> está en `.gitignore` y así tiene que quedar: el repo es solo código (ver
> `CLAUDE.md`, "Restricciones del entorno").

Los parámetros `--desde`, `--hasta` y `--mes` se escriben en `YYYYMM`, que es
lo legible; internamente se convierten al índice `year*12+month` que usan las
consultas.

## Cómo está armado

```
app/
  main.py     configura la página, inyecta el CSS y arma la navegación
  data.py     lee los .sql, sustituye parámetros, llama al helper y cachea
  theme.py    paleta, dimensión de grupo, template de Plotly y CSS
  charts.py   construye las figuras. NO renderiza ninguna
  export.py   arma el HTML estático con esas mismas figuras
  pages/      una por página del tablero
```

La regla que sostiene el diseño: **`charts.py` devuelve figuras y no las
pinta.** `main.py` las pasa a `st.plotly_chart`; `export.py` las pasa a
`write_html`. Una sola definición por figura, dos salidas. Si el HTML se ve
distinto de la app, es un bug de `charts.py`, no de dos implementaciones que se
separaron.

### Dos capas de SQL

`sql/20_construccion/` crea las tablas, una vez al mes y **sin parámetros**.
`sql/30_lectura/` son SELECT sin filtros sobre esas tablas, y es lo único que
llama la app.

`data.py` lee los `.sql` de `30_lectura/` tal como están, sin sustituir nada:
trae cada tabla entera y **filtra en pandas**. Son decenas de miles de filas,
así que `st.cache_data` cachea una vez y mover un selector del sidebar es
instantáneo porque no vuelve a Impala.

La excepción son las consultas de `00_perfilado/`, que sí van directo contra la
tabla fuente y con parámetros: son diagnósticas, se corren cuando hacen falta,
y la de mapeo se ejecuta deliberadamente sobre un solo mes. Ahí los valores de
mes se calculan como `year * 12 + month` y se fuerzan a `int` antes de
formatearlos, así un selector no puede meter texto arbitrario en la consulta.
El porqué del `12` y no `100` está en `CLAUDE.md`.

La fuente de verdad del mapeo `idx → producto` es
`sql/20_construccion/01_largo_calificaciones.sql`: es el único que corre y
produce la tabla larga que lee todo lo demás. Las copias de
`sql/00_perfilado/` tienen que mantenerse alineadas con él, y
`validacion_mapeo.sql` es lo que lo verifica.

### Decisiones de color

La paleta no se eligió a ojo: se validó con los checks computables de la guía
de visualización (banda de luminosidad OKLCH, piso de croma, separación bajo
simulación de daltonismo, piso de visión normal y contraste contra la
superficie). Las cifras de cada check están anotadas en `theme.py`.

- **G1–G8 es una escala ordinal**, así que va en una rampa secuencial y nunca
  en colores categóricos sueltos. La rampa recorre **verde → ámbar → rojo** con
  croma moderado, y la luminosidad baja de forma monótona a lo largo de los
  ocho pasos. Que el gradiente lo lleven tono y luminosidad a la vez es lo que
  hace que la escala sobreviva cuando el tono se pierde: en blanco y negro
  queda el span de L, y bajo daltonismo la separación entre pasos contiguos
  queda mejor que con una rampa de un solo tono. Las aperturas de sufi
  (`G7_B/M/A`) se interpolan dentro del tramo de su grupo base, así que leen
  como subdivisiones y no como grupos nuevos.
- **La matriz de migración usa una paleta divergente centrada en la diagonal.**
  El tono dice la dirección (azul mejora, rojo deterioro) y la intensidad el
  volumen. La diagonal queda neutra sin importar su masa: es estabilidad, no
  señal. Entradas, salidas y elegibilidad van en gris, fuera de la escala.
- **Las series de tiempo son cuatro como máximo**, con color *y* estilo de
  línea distinto, para que se lean impresas o en blanco y negro. Cuando hay
  más, las menores se agrupan en «otros» en vez de generar colores nuevos.
- Los umbrales de PSI van como líneas tenues anotadas al margen derecho, no
  como series de la leyenda.

### Dónde vive `grupo_orden`

En `theme.DIM_GRUPO`. No viaja en los agregados a propósito: es presentacional
(ver `powerbi/notas_modelo.md`). La app lo reconstruye con **la misma
aritmética** que `sql/20_construccion/01_largo_calificaciones.sql`. Si cambia la convención
de nombres de grupo, hay que tocar los dos lados.

## Qué mira cada página

| Página | Audiencia | Consultas |
|---|---|---|
| Salud del dato | todas | las cuatro de `sql/00_perfilado/` |
| Panorama del mes | negocio | `distribucion_grupo`, `cobertura_producto`, `base_clientes` |
| Evolución | negocio | `distribucion_grupo`, `base_clientes` |
| Migración | negocio + modelos | `migracion`, `migracion_pd` |
| Modelos | seguimiento técnico | `pd_por_modelo`, `cortes_por_producto` |

**Salud del dato va primera** y no es una página de gráficos: es el estado de
los cuatro chequeos de perfilado, cada uno verde o rojo con una línea de
explicación. El detalle solo se despliega si el chequeo falla. Si algo ahí
está en rojo, los números de las otras páginas no significan lo que parecen.

1. **Un solo `ingestion_day` por mes** — todo el repo asume una fila por
   cliente y mes; sin eso cada `count(*)` duplica en silencio.
2. **Mapeo `idx` → columna alineado** — un `CASE` desalineado no da error,
   solo etiqueta mal. Es la consulta más lenta (16 agregados sobre la misma
   partición), así que en la app viene desactivada y se corre sobre un mes.
   Mientras esté apagada la tarjeta dice **SIN EJECUTAR**, no verde, y el
   estado global no puede ser verde: un chequeo que no corrió no afirma nada.
3. **Dominio de grupos y modelos sin novedades** — un grupo fuera de G1–G8 y
   las aperturas de sufi, o un modelo fuera de los ocho conocidos. Un modelo
   nuevo no es un error: es una novedad. Si viene en escala de puntaje hay que
   agregarlo a la lista de `pd_por_modelo.sql` o sus bins salen mal sin dar
   síntoma, y el chequeo lo señala aparte.
4. **PD y grupo concuerdan** — las filas con PD nula y grupo poblado existen y
   no son un problema; el chequeo falla si **crecen** respecto al mes anterior.
   Es el único de los cuatro con gráfico, porque es el único donde la
   tendencia dice algo.

La separación entre las dos audiencias está explicada en
`powerbi/notas_modelo.md`, "Dos audiencias, dos bloques de páginas". Vale acá
igual: **`producto` no es una dimensión válida para nada que sea PD**, porque
solo hay dos PD. La excepción es la sensibilidad de cortes, donde sí lo es,
porque los cortes sí son por producto.

## Lo que la app hace y Power BI no

- **Tabla de solapamientos de cortes**: rangos de PD que se cruzan entre grupos
  consecutivos del mismo producto. Es una alerta de calidad, no un gráfico: si
  aparece, el corte de ese producto no depende solo de la PD.
- **Tabla de peores saltos**: origen → destino con caída de tres grupos o más,
  por volumen.
- **Comparador de dos meses** lado a lado en composición.
- **Descarga a CSV** de cualquier tabla en pantalla.

## Estado

Las consultas de `sql/20_construccion/` **todavía no se corrieron en Impala**. Lo
verificado hasta acá es consistencia estructural (mapeo alineado, aritmética de
meses, cobertura de columnas) y que las figuras se construyen y serializan con
datos sintéticos. Falta la primera corrida real.
