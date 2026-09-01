# Tablero de calificaciones de riesgo

Repo de queries SQL (Impala) más una app de Streamlit para el seguimiento de
los modelos de calificación de clientes.

- `CLAUDE.md` — contexto, restricciones y hallazgos del perfilado. **Leerlo
  antes de tocar SQL.**
- `sql/` — las consultas. Es la fuente de verdad de los datos.
- `app/` — el Streamlit y el exportador a HTML.
- `powerbi/notas_modelo.md` — notas del modelo de Power BI, que consume los
  mismos agregados.

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
FORMATO_PARAMETRO = "%({nombre})s"   # cambiar si el helper usa otro estilo
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

### El SQL no se reescribe

`data.py` lee los `.sql` de `sql/10_agregados/` tal como están y solo
reemplaza los marcadores `{DESDE}`, `{HASTA}` y `{REZAGO}` por el formato de
parámetros del helper. Esas consultas llevan documentado el porqué de cada
decisión; duplicarlas en Python sería crear una segunda fuente de verdad.

Los valores de mes se calculan como `year * 12 + month` y se fuerzan a `int`
antes de formatearlos, así un selector de fecha no puede meter texto arbitrario
en la consulta. El porqué del `12` y no `100` está en `CLAUDE.md`.

### Decisiones de color

La paleta no se eligió a ojo: se validó con los checks computables de la guía
de visualización (banda de luminosidad OKLCH, piso de croma, separación bajo
simulación de daltonismo, piso de visión normal y contraste contra la
superficie). Las cifras de cada check están anotadas en `theme.py`.

- **G1–G8 es una escala ordinal**, así que va en una rampa secuencial de un
  solo tono, clara a oscura, nunca en colores categóricos: con colores no
  relacionados se pierde la lectura de gradiente. Las aperturas de sufi
  (`G7_B/M/A`) caen en tonos contiguos dentro del tramo de su grupo base, por
  construcción — el color sale de `grupo_orden`.
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
aritmética** que `sql/_fragmentos/cte_productos.sql`. Si cambia la convención
de nombres de grupo, hay que tocar los dos lados.

## Qué mira cada página

| Página | Audiencia | Consultas |
|---|---|---|
| Panorama del mes | negocio | `distribucion_grupo`, `cobertura_producto`, `base_clientes` |
| Evolución | negocio | `distribucion_grupo`, `base_clientes` |
| Migración | negocio + modelos | `migracion`, `migracion_pd` |
| Modelos | seguimiento técnico | `pd_por_modelo`, `cortes_por_producto` |

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

Las consultas de `sql/10_agregados/` **todavía no se corrieron en Impala**. Lo
verificado hasta acá es consistencia estructural (mapeo alineado, aritmética de
meses, cobertura de columnas) y que las figuras se construyen y serializan con
datos sintéticos. Falta la primera corrida real.
