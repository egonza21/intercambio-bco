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

**Se corre una vez al mes**, cuando llega la partición nueva, desde la página
**Construcción** de la app. Tiene el último mes de la tabla fuente al lado del
último mes construido (si la fuente va adelante, dice que hay que
reconstruir), el estado de cada tabla, un botón por script y uno para todo,
con log y barra de progreso. Si un script falla se detiene ahí, porque los que
siguen pueden depender de él.

> **Los scripts no se pueden correr a mano con `impala-shell -f`.** Llevan
> marcadores que resuelve la app: `{IDUNICO}` en todos (impala-shell no lo
> sustituye; su sintaxis de variables es otra) y `{MODELOS_DECLARADOS}` en
> `05_pd_por_modelo`, que se genera desde `config/modelos.csv`. Además `05`
> tiene una verificación que corre en la app a mitad del script y que puede
> abortar la construcción. Corrido a mano, se la saltearía.

**Ningún script usa CTEs**: cada paso intermedio es una tabla física con
prefijo `tmp_`, que se borra al final. Eso multiplica las sentencias — la
construcción completa son **173** repartidas en once scripts, de 3 en los más
simples a 31 en los de migración de PD. La app las ejecuta de a una: si una
falla, el log dice cuál. El detalle por script está en `00_orden.md`.

`01_largo_calificaciones` tiene que existir antes que los cuatro scripts que
leen de ella. El detalle de dependencias está en
`sql/20_construccion/00_orden.md`.

### Los modelos: `config/modelos.csv`

Es la única lista de modelos del repo, con su escala (`probabilidad` o
`puntaje`). **Cuando entra un modelo nuevo se agrega una línea ahí** y nada
más. Si alguien se olvida, la construcción de `pd_por_modelo` lo atrapa: un
modelo con PD mayor a 1 que no esté declarado como puntaje hace fallar la
construcción, y la tabla se borra en vez de quedar con los bins mal. Un modelo
nuevo de probabilidad solo da un aviso. Detalle en `CLAUDE.md`, "Modelos y su
escala".

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

## Pruebas

```bash
cd tablero-calif
python -m unittest discover -s tests -v
```

Sin dependencias nuevas: `unittest` es de la biblioteca estándar. Usa datos
**sintéticos** (`tests/fixtures.py`, inventados con semilla fija), así que corre
sin Impala y sin helper. **Correrlas antes de cada commit que toque `app/`.**

Llaman a todas las funciones públicas de gráfico con datos que abren sus
ramas, y buscan nombres usados sin definir en todo `app/`. Existen porque
`py_compile` e importar un módulo no ejecutan el cuerpo de las funciones, y así
se escaparon un `@dataclass` perdido y un diccionario borrado.

La app se conecta a Impala a través de la librería interna `helper`. Esa
llamada está aislada en **una sola función** de `app/data.py`, en el bloque
marcado con un recuadro de comentarios. Si la firma real difiere, se ajusta ahí
y en ningún otro lado:

```python
DSN = "impala-virtual-prd"
USUARIO = "efgon"
FORMATO_PARAMETRO = "{{{nombre}}}"   # cambiar si el helper usa otro estilo
```

**Hay una sola instancia del helper por proceso** (`@st.cache_resource`),
compartida por todas las páginas, y **no se cierra nunca**. Instanciar por
llamada costaba una conexión nueva por sentencia, y reconstruir todo son unas
170.

El proceso de Streamlit vive horas, así que una instancia cacheada puede
quedarse con el socket muerto por inactividad. Por eso todo lo que ejecuta
algo pasa por `_con_reintento()`: si el error es **de conexión**, limpia el
caché, reinstancia y reintenta **una vez**. Si es de SQL, propaga sin
reintentar — reejecutar un DDL que falló es caro y esconde el error real. La
distinción está en `_es_error_de_conexion()`, que recorre la cadena de causas
y, ante la duda, dice que no.

Las sentencias sin retorno (drop, create table as, compute stats) van por
`data.METODO_DDL`, **un nombre y no una lista de candidatos**. Si el helper no
lo expone, la página de Construcción lo muestra arriba y en rojo, deshabilita
los botones de reconstruir y dice qué métodos sí encontró. No hay respaldo a
`obtener_dataframe`: un respaldo silencioso es lo que esconde un nombre mal
escrito hasta que alguien mira los datos.

> El nombre es **singular**: `ejecutar_consulta`. No se puede inspeccionar la
> clase fuera del banco —el paquete no está instalado—, así que la verificación
> de la página es lo que cubre ese hueco. Primero se escribió en plural y
> estaba mal.

Se ejecutan **de a una** aunque el método acepte varias: si un script de 31
sentencias falla, hay que poder decir en cuál.

Los agregados se cachean una hora (`@st.cache_data`). Para forzar una
relectura: tecla `C` en la app, o «Clear cache» en el menú.

## Exportar el HTML para las revisiones

```bash
python app/export.py                     # la ventana completa de lo construido
python app/export.py --desde 202601 --hasta 202609 --mes 202609 --rezago 6
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
consultas. **Son opcionales**: por defecto salen de las tablas construidas,
con el mismo cálculo que la ventana de la app, así un export sin argumentos
siempre incluye el último mes construido. La app tampoco tiene fechas fijas:
cada mes nuevo aparece solo al reconstruir.

## Cómo está armado

```
app/
  main.py            configura la página, inyecta el CSS y arma la navegación
  data.py            lee los .sql, llama al helper y cachea
  theme.py           paleta, dimensión de grupo, template de Plotly y CSS
  charts.py          fachada: reexporta las figuras de los módulos de abajo
  charts_base.py     helpers compartidos (_sin_datos, _t, contra qué mes)
  charts_panorama.py Panorama del mes y Evolución
  charts_anomalias.py ranking, matriz segmento × producto y puente de la base
  charts_migracion.py migración de grupo, de PD y de modelo
  charts_modelos.py  histograma de PD, PSI y cortes
  charts_salud.py    los cuatro chequeos de salud del dato
  export.py          arma el HTML estático con esas mismas figuras
  pages/             una por página del tablero
config/
  modelos.csv        los modelos y su escala; la única lista del repo
  productos.csv      idx, producto, familia, serie; la única lista de productos
tests/               pruebas con datos sintéticos
```

Las figuras están partidas **por página**, que es como se piensa el tablero.
`charts.py` quedó como fachada para que `import charts` siga funcionando: la
división es del código, no de la interfaz.

La regla que sostiene el diseño: **los módulos de figuras devuelven figuras y
no las pintan.** `main.py` las pasa a `st.plotly_chart`; `export.py` las pasa a
`write_html`. Una sola definición por figura, dos salidas. Si el HTML se ve
distinto de la app, es un bug de la función, no de dos implementaciones que se
separaron.

### Dos invariantes que no son opcionales

**El código de segmento es la identidad; el nombre es presentación.** Los ejes
y los índices se construyen siempre sobre `segmento` (el código), y el nombre
legible entra solo por `tickvals`/`ticktext` o como `name` de una serie. Los
nombres pueden repetirse — un código sin mapear cae a su valor crudo — y
Plotly colapsa dos categorías con la misma etiqueta en una sola, mostrando el
valor de un segmento bajo el nombre de otro sin dar error. `data._con_segmento`
normaliza la columna a string una sola vez, al leer; `theme.etiquetas_segmento`
revienta si dos códigos producen la misma etiqueta.

**Ningún visual que compare contra otro mes deja implícito contra cuál.**
`charts_base.mes_comparacion` resuelve el mes de comparación a partir de los
meses que existen, no de `idx_mes - 1`, y devuelve también la distancia. Si
falta la partición del mes anterior, el visual lo dice y aclara contra qué mes
terminó comparando y a cuántos meses. En las tablas, las columnas se llaman
con el mes ("jul 2026", "ago 2026"), nunca "anterior"/"actual".

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
