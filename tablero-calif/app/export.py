"""Genera el HTML estático para las revisiones con el equipo.

    python app/export.py --desde 202505 --hasta 202608

Usa EXACTAMENTE las mismas funciones de charts.py que pinta la app. No hay una
segunda definición de ninguna figura: si el HTML se ve distinto al Streamlit,
es un bug de charts.py, no de dos implementaciones que se separaron.

El archivo se autocontiene: plotly.js va embebido, no por CDN, porque la red
del banco puede no alcanzarlo. Se abre con doble clic, sin servidor ni Python.

SALIDA: va a tablero-calif/exportes/, que está en .gitignore. Los HTML
CONTIENEN DATOS aunque sean agregados, y el repo es solo código.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts  # noqa: E402
import data  # noqa: E402
import theme  # noqa: E402

DIR_SALIDA = Path(__file__).resolve().parent.parent / "exportes"

CONFIG_PLOTLY = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
}


def _css() -> str:
    """Replica la paleta y la tipografía de la app, para que el archivo se vea
    igual de cuidado que el Streamlit."""
    return f"""
    :root {{
      --surface: {theme.SURFACE}; --plane: {theme.PLANE};
      --ink: {theme.INK}; --ink-soft: {theme.INK_SOFT}; --ink-muted: {theme.INK_MUTED};
      --border: {theme.BORDER};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; background: var(--plane); color: var(--ink-soft);
      font-family: {theme.FONT}; font-size: 14px; line-height: 1.55;
      -webkit-font-smoothing: antialiased;
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 3rem 1.6rem 5rem; }}
    header.top {{ border-bottom: 1px solid var(--border); padding-bottom: 1.4rem;
                  margin-bottom: 2rem; }}
    h1 {{ font-size: 1.7rem; font-weight: 650; color: var(--ink);
         letter-spacing: -0.015em; margin: 0 0 .3rem; }}
    h2 {{ font-size: 1.15rem; font-weight: 620; color: var(--ink);
         letter-spacing: -0.008em; margin: 0 0 .35rem;
         scroll-margin-top: 1.5rem; }}
    h3 {{ font-size: .95rem; font-weight: 600; color: var(--ink); margin: 0 0 .3rem; }}
    p.sub {{ color: var(--ink-soft); font-size: .87rem; margin: 0 0 1rem;
            max-width: 76ch; }}
    p.nota {{ color: var(--ink-muted); font-size: .79rem; margin: .5rem 0 0;
             max-width: 88ch; }}
    section {{ margin: 0 0 3.2rem; }}
    .fig {{ background: var(--surface); border: 1px solid var(--border);
           border-radius: 10px; padding: .5rem .4rem .2rem; margin: 0 0 .6rem;
           box-shadow: 0 1px 2px rgba(11,11,11,.04); }}
    nav.indice {{ background: var(--surface); border: 1px solid var(--border);
                 border-radius: 10px; padding: 1rem 1.2rem; margin: 0 0 2.6rem; }}
    nav.indice p {{ margin: 0 0 .5rem; font-size: .74rem; font-weight: 600;
                   text-transform: uppercase; letter-spacing: .06em;
                   color: var(--ink-muted); }}
    nav.indice ol {{ margin: 0; padding-left: 1.1rem; }}
    nav.indice li {{ margin: .2rem 0; }}
    nav.indice a, .volver {{ color: {theme.SERIES[0]}; text-decoration: none; }}
    nav.indice a:hover, .volver:hover {{ text-decoration: underline; }}
    .volver {{ font-size: .78rem; display: inline-block; margin-top: .4rem; }}
    .chks {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: .8rem; margin: 0 0 1.6rem; }}
    .chk {{ background: var(--surface); border: 1px solid var(--border);
           border-left: 3px solid var(--ink-muted); border-radius: 10px;
           padding: .8rem 1rem; }}
    .chk-est {{ font-size: .68rem; font-weight: 700; letter-spacing: .05em; }}
    .chk-nom {{ font-size: .9rem; font-weight: 600; color: var(--ink);
               margin: .2rem 0 .35rem; line-height: 1.3; }}
    .chk-res {{ font-size: .78rem; color: var(--ink-soft); line-height: 1.45; }}
    .banda {{ border-radius: 10px; padding: .85rem 1.1rem; margin: 0 0 1.4rem;
             font-size: .87rem; }}
    .kpis {{ display: flex; flex-wrap: wrap; gap: .8rem; margin: 0 0 1.4rem; }}
    .kpi {{ flex: 1 1 170px; background: var(--surface); border: 1px solid var(--border);
           border-radius: 10px; padding: .8rem 1rem; }}
    .kpi .lbl {{ font-size: .7rem; text-transform: uppercase; letter-spacing: .045em;
                color: var(--ink-muted); font-weight: 600; }}
    .kpi .val {{ font-size: 1.5rem; font-weight: 600; color: var(--ink);
                letter-spacing: -0.02em; margin-top: .15rem; }}
    table {{ border-collapse: collapse; width: 100%; font-size: .82rem;
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 10px; overflow: hidden; }}
    th {{ text-align: left; font-weight: 600; color: var(--ink-muted);
         font-size: .72rem; text-transform: uppercase; letter-spacing: .04em;
         padding: .55rem .7rem; border-bottom: 1px solid var(--border); }}
    td {{ padding: .45rem .7rem; border-bottom: 1px solid rgba(11,11,11,.05);
         font-variant-numeric: tabular-nums; }}
    tr:last-child td {{ border-bottom: none; }}
    footer {{ border-top: 1px solid var(--border); padding-top: 1.2rem;
             margin-top: 2rem; font-size: .78rem; color: var(--ink-muted); }}
    @media print {{
      body {{ background: #fff; }}
      .fig, .kpi, table {{ break-inside: avoid; box-shadow: none; }}
      nav.indice, .volver {{ display: none; }}
    }}
    """


class Doc:
    """Acumula secciones. Embebe plotly.js UNA sola vez.

    El pedido era include_plotlyjs=True para no depender del CDN. Se cumple:
    la librería queda dentro del archivo. Lo que no se hace es repetirla por
    figura -- son ~3 MB cada vez. Va completa en la primera y por referencia en
    el resto, con lo cual el HTML sigue abriendo sin red.
    """

    def __init__(self) -> None:
        self.partes: list[str] = []
        self.indice: list[tuple[str, str]] = []
        self._primera = True

    def seccion(self, ancla: str, titulo: str, sub: str = "") -> None:
        self.indice.append((ancla, titulo))
        self.partes.append(f'<section id="{ancla}"><h2>{titulo}</h2>')
        if sub:
            self.partes.append(f'<p class="sub">{sub}</p>')

    def cierra(self) -> None:
        self.partes.append('<a class="volver" href="#indice">Volver al índice</a>'
                           '</section>')

    def figura(self, fig, alto: int | None = None) -> None:
        html = fig.to_html(
            include_plotlyjs=True if self._primera else False,
            full_html=False, config=CONFIG_PLOTLY,
            default_height=alto or fig.layout.height or 420,
        )
        self._primera = False
        self.partes.append(f'<div class="fig">{html}</div>')

    def semaforo(self, chequeos) -> None:
        """Estado de los chequeos de salud, en tarjetas con borde de color."""
        celdas = []
        for c in chequeos:
            celdas.append(
                f'<div class="chk" style="border-left-color:{c.color}">'
                f'<div class="chk-est" style="color:{c.color}">{c.icono} {c.estado}</div>'
                f'<div class="chk-nom">{c.nombre}</div>'
                f'<div class="chk-res">{c.resumen}</div></div>')
        self.partes.append(f'<div class="chks">{"".join(celdas)}</div>')

    def kpis(self, pares: list[tuple[str, str]]) -> None:
        celdas = "".join(
            f'<div class="kpi"><div class="lbl">{l}</div><div class="val">{v}</div></div>'
            for l, v in pares)
        self.partes.append(f'<div class="kpis">{celdas}</div>')

    def nota(self, texto: str) -> None:
        self.partes.append(f'<p class="nota">{texto}</p>')

    def sub(self, texto: str) -> None:
        self.partes.append(f'<h3>{texto}</h3>')

    def tabla(self, df, maximo: int = 25) -> None:
        if df is None or df.empty:
            self.partes.append('<p class="nota">Sin filas.</p>')
            return
        self.partes.append(df.head(maximo).to_html(index=False, border=0,
                                                   float_format=lambda v: f"{v:.5f}"))
        if len(df) > maximo:
            self.nota(f"Se muestran {maximo} de {len(df)} filas. "
                      f"El listado completo se descarga desde la app.")

    def render(self, titulo: str, subtitulo: str) -> str:
        idx = "".join(f'<li><a href="#{a}">{t}</a></li>' for a, t in self.indice)
        return (
            "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{titulo}</title><style>{_css()}</style></head><body>"
            f'<div class="wrap"><header class="top"><h1>{titulo}</h1>'
            f'<p class="sub">{subtitulo}</p></header>'
            f'<nav class="indice" id="indice"><p>Contenido</p><ol>{idx}</ol></nav>'
            + "".join(self.partes) +
            '<footer>Generado desde el repo de calificaciones. Los agregados '
            'salen de las tablas construidas por <code>sql/20_construccion/</code>; '
            'las figuras, de '
            '<code>app/charts.py</code>, las mismas que muestra la app.<br>'
            'Este archivo contiene datos: no subirlo al repositorio.</footer>'
            "</div></body></html>")


def construir(desde: int, hasta: int, mes: int, rezago: int) -> str:
    doc = Doc()

    # --- 0. Salud del dato -------------------------------------------------
    # Va PRIMERO: el que abre el reporte tiene que saber si los números que va
    # a mirar son confiables antes de mirarlos.
    # El export SIEMPRE corre los cuatro, incluido el de mapeo, sin importar
    # lo que tenga tildado la UI: un archivo que afirma que todo está bien sin
    # haber corrido un chequeo está diciendo algo que no verificó. Se genera
    # una vez al mes, así que la lentitud acá no importa.
    nulos = data.nulos_pd_vs_grupo(desde, hasta)
    chequeos = [
        charts.chequeo_ingestion_day(data.duplicados_ingestion_day(desde, hasta)),
        # Sobre un solo mes: el costo se multiplica por la cantidad de meses.
        charts.chequeo_mapeo(data.validacion_mapeo(mes, mes)),
    ]
    chequeos.append(charts.chequeo_dominio(
        data.dominio_grupos(desde, hasta), data.escala_modelos(desde, hasta),
        data.MODELOS_CONOCIDOS))
    chequeos.append(charts.chequeo_pd_grupo(nulos))

    fallan = [c for c in chequeos if c.ejecutado and not c.ok]
    nivel, mensaje, _ = charts.resumen_global(chequeos)
    doc.seccion("salud", "Salud del dato",
                "Estado de los chequeos de sql/00_perfilado/ al momento de "
                "generar este archivo. Son los supuestos sobre los que se "
                "apoya todo lo que sigue.")
    fondo, borde, tinta = {
        "ok":     ("#e9f7e9", theme.ESTADO_OK, "#0b5c0b"),
        "aviso":  ("#fdf5e3", theme.ESTADO_ALERTA, "#7a5800"),
        "alerta": ("#fdeceb", theme.ESTADO_CRITICO, "#7d1f1f"),
    }[nivel]
    doc.partes.append(
        f'<div class="banda" style="background:{fondo};border:1px solid {borde};'
        f'color:{tinta}"><b>{mensaje}</b></div>')
    doc.semaforo(chequeos)
    for c in fallan:
        if c.detalle is not None and not c.detalle.empty:
            doc.sub(f"Detalle · {c.nombre}")
            doc.tabla(c.detalle, maximo=15)
    doc.sub("Discordancia entre PD y grupo, mes a mes")
    doc.figura(charts.discordancia_pd_grupo(nulos))
    doc.nota("Es el único de los cuatro chequeos donde la tendencia dice algo. "
             "Que existan filas con PD nula y grupo poblado no es un problema; "
             "que crezcan sugiere que la replicación de PD se degrada.")
    doc.cierra()

    def _v(df):
        return df if df.empty or "idx_mes" not in df.columns \
            else df[df["idx_mes"].between(desde, hasta)]

    # --- 0. Qué se movió --------------------------------------------------
    # Va antes que todo: quien abre el reporte tiene que saber dónde mirar
    # antes de mirar. Sin ventana: el baseline necesita toda la historia.
    cob_full = data.cobertura_producto()
    doc.seccion("anomalias", "Qué se movió este mes",
                f"Celdas segmento × producto ordenadas por cuánto se salieron "
                f"de su propia historia, en {theme.etiqueta_mes_idx(mes)} "
                f"contra {theme.etiqueta_mes_idx(mes - 1)}. Es un ranking, no "
                f"una alarma: siempre muestra sus primeras filas. El baseline "
                f"usa mediana y MAD, no promedio y desvío, porque los "
                f"incidentes pasados están dentro de la historia y con "
                f"promedio inflarían su propia variabilidad.")
    for metrica, titulo in (("cantidad", "Por clientes calificados"),
                            ("cobertura", "Por cobertura (% de la base)")):
        rk, sb = charts.ranking_anomalias(cob_full, mes, metrica, 15)
        doc.sub(titulo)
        if rk.empty:
            doc.nota("Ninguna celda con historia suficiente superó el piso de "
                     "variación este mes.")
        else:
            vis = rk.drop(columns=["serie", "_cod_seg"]).copy()
            vis["var_rel"] = vis["var_rel"].map(lambda v: f"{v * 100:+.1f}%")
            vis["puntaje"] = vis["puntaje"].map(lambda v: f"{v:.1f}")
            doc.tabla(vis, maximo=15)
        if not sb.empty:
            doc.nota(f"{len(sb)} celdas quedaron fuera del ranking por tener "
                     f"menos de {charts.MESES_MINIMOS} meses de historia.")
    doc.sub("La matriz completa · variación contra el mes anterior")
    doc.figura(charts.matriz_segmento_producto(cob_full, mes, "variacion"))
    doc.cierra()

    dist = _v(data.distribucion_grupo())
    base = _v(data.base_clientes())
    cob = _v(data.cobertura_producto())
    dist_mes = dist[dist["idx_mes"] == mes]
    base_mes = base[base["idx_mes"] == mes]
    cob_mes = cob[cob["idx_mes"] == mes]

    # --- 1. Panorama -------------------------------------------------------
    doc.seccion("panorama", "Panorama del mes",
                f"Composición de la cartera por grupo de riesgo en "
                f"{theme.etiqueta_mes_idx(mes)}. Todo en participación: la base "
                f"viene cayendo y apilar conteos haría leer esa contracción "
                f"como mejora del riesgo.")
    clientes = base_mes["clientes"].sum() if not base_mes.empty else None
    doc.kpis([
        ("Clientes en la base", theme.fmt_miles(clientes)),
        ("Productos", theme.fmt_miles(dist_mes["producto"].nunique()) if not dist_mes.empty else "--"),
        ("Segmentos", theme.fmt_miles(base_mes["segmento"].nunique()) if not base_mes.empty else "--"),
    ])
    doc.sub("Composición de grupo por producto")
    doc.figura(charts.composicion_grupo(dist_mes, "todas"))
    doc.nota("En sufi_moto, sufi_cpe y sufi_con los grupos G7 y G8 vienen "
             "abiertos en bajo, medio y alto, en tonos contiguos dentro del "
             "tramo de su grupo base.")
    doc.sub("Segmento × grupo")
    doc.figura(charts.heatmap_segmento_grupo(dist_mes, "todos"))
    doc.sub("Cobertura por producto")
    doc.figura(charts.cobertura(cob_mes, "todos"))
    doc.sub("Segmento × producto · clientes calificados")
    doc.figura(charts.matriz_segmento_producto(cob, mes, "cantidad"))
    doc.cierra()

    # --- 2. Evolución ------------------------------------------------------
    doc.seccion("evolucion", "Evolución",
                f"De {theme.etiqueta_mes_idx(desde)} a {theme.etiqueta_mes_idx(hasta)}.")
    doc.sub("Mezcla de riesgo — consumo")
    doc.figura(charts.mezcla_riesgo(dist, "consumo"))
    doc.sub("Base de clientes")
    doc.figura(charts.base_clientes_tiempo(base))
    doc.sub("Modelos vivos por mes")
    doc.figura(charts.modelos_vivos(dist))
    doc.sub("Reparto de la población entre modelos")
    doc.figura(charts.vigencia_modelos(dist))
    puente = _v(data.puente_base())
    if not puente.empty:
        doc.sub("Puente de la base")
        doc.figura(charts.puente_base(puente, mes, "todos"))
        doc.sub("Entradas y salidas por segmento")
        doc.figura(charts.puente_por_segmento(puente, mes))
    doc.cierra()

    # --- 3. Migración ------------------------------------------------------
    primer_valido = theme.idx_mes(2025, 5) + rezago
    desde_ok, mes_mig = max(desde, primer_valido), max(mes, primer_valido)
    doc.seccion("migracion", "Migración",
                f"Comparación contra {rezago} "
                f"{'mes' if rezago == 1 else 'meses'} atrás. La primera matriz "
                f"válida con este rezago es la de "
                f"{theme.etiqueta_mes_idx(primer_valido)}.")
    if hasta >= primer_valido:
        mig = _v(data.migracion(rezago))
        mig_mes = mig[mig["idx_mes"] == mes_mig]
        doc.sub(f"Matriz de migración · consumo · {theme.etiqueta_mes_idx(mes_mig)}")
        doc.figura(charts.matriz_migracion(mig_mes, "consumo", True))
        doc.nota("El tono dice la dirección y la intensidad el volumen, como "
                 "porcentaje de la fila de origen. La diagonal es neutra a "
                 "propósito: es estabilidad, no señal.")
        doc.sub("Estabilidad y deterioro en el tiempo")
        doc.figura(charts.estabilidad_deterioro(mig, "consumo"))
        doc.sub("Peores saltos")
        doc.tabla(charts.tabla_peores_saltos(mig_mes))
        mig_pd = _v(data.migracion_pd(rezago))
        if not mig_pd.empty:
            doc.sub("Migración de deciles de PD — serie general")
            doc.figura(charts.matriz_migracion_pd(
                mig_pd[mig_pd["idx_mes"] == mes_mig], "general"))
            doc.nota("No se lee como la matriz de grupo: los deciles se "
                     "recalculan cada mes, así que esto mide reordenamiento "
                     "del ranking, no desplazamiento de la distribución.")
    else:
        doc.nota("La ventana termina antes del primer mes comparable con este "
                 "rezago.")
    doc.cierra()

    # --- 4. Modelos --------------------------------------------------------
    pdm = _v(data.pd_por_modelo())
    cortes = _v(data.cortes_por_producto())
    cortes_mes = cortes[cortes["idx_mes"] == mes] if not cortes.empty else cortes
    doc.seccion("modelos", "Modelos",
                "Solo hay dos PD: una para los doce productos que no son de "
                "vivienda y otra para los cuatro que sí. Lo que es del producto "
                "son los cortes que traducen esa PD a grupo.")
    solap = charts.tabla_solapamientos(cortes_mes)
    doc.kpis([
        ("Modelos activos",
         theme.fmt_miles(pdm[pdm["idx_mes"] == mes]["modelo"].nunique()) if not pdm.empty else "--"),
        ("Cortes solapados", theme.fmt_miles(len(solap)) if solap is not None else "0"),
    ])
    doc.sub("Sensibilidad de cortes")
    doc.figura(charts.sensibilidad_cortes(cortes_mes, "todos"))
    doc.nota("Cada fila es un producto; cada banda, el rango de PD de un grupo. "
             "Como todos traducen la misma PD, las filas se comparan "
             "verticalmente. Las cruces rojas marcan solapamientos.")
    doc.sub("Solapamientos de corte")
    doc.tabla(solap)
    for escala in sorted(pdm["escala"].unique()) if not pdm.empty else []:
        nombre = "puntaje 0–999" if escala == "puntaje_0_999" else "probabilidad 0–1"
        doc.sub(f"Histograma de PD — {nombre}")
        doc.figura(charts.histograma_pd(pdm[pdm["idx_mes"] == mes], escala))
    doc.cierra()

    # --- 5. PSI, los tres niveles -----------------------------------------
    # El HTML tiene que mostrar EXACTAMENTE lo mismo que la app. Antes esta
    # sección llamaba a la versión vieja del PSI -- epsilon sin descarte, un
    # solo nivel -- así que el archivo que circulaba por mail traía valores
    # inflados mientras la pantalla mostraba los corregidos.
    #
    # Sin interactividad se fija la variante por defecto: base contra el primer
    # mes de la ventana (deriva acumulada) y grupo_base.
    base_movil = False
    serie_n1 = charts.psi_grupos(dist, "todos", None, "grupo_base", base_movil)
    mes_base = (theme.etiqueta_mes_idx(int(serie_n1["idx_base"].iloc[-1]))
                if not serie_n1.empty else "--")

    doc.seccion("psi", "PSI",
                "Mide cuánto se movió la población entre grupos de riesgo "
                "frente a un mes de referencia. Si el reparto entre G1 y G8 es "
                "igual, da cero; mientras más población cambie de grupo, más "
                "sube. Debajo de 0,10 el cambio es despreciable; entre 0,10 y "
                "0,25 hay que revisarlo; por encima de 0,25 la población ya no "
                "se parece a la de referencia.")
    doc.partes.append(
        f'<div class="banda" style="background:#eef4fb;'
        f'border:1px solid {theme.SERIES[0]};color:{theme.INK}">'
        f'<b>Regla de lectura.</b> El nivel 1 es el que dispara acción. Los '
        f'niveles 2 y 3 explican por qué, no deciden. Si el nivel 1 y el 3 se '
        f'contradicen, manda el 1: los grupos son la unidad con la que se '
        f'oferta.<br><b>Base de comparación:</b> {mes_base} '
        f'(primer mes de la ventana, deriva acumulada).</div>')

    doc.sub("Nivel 1 · General")
    doc.partes.append(
        '<p class="sub">¿Se está moviendo el riesgo del banco? PSI sobre la '
        'distribución de grupos de toda la población, sin partir por modelo.</p>')
    fig1, _, _ = charts.psi_grupos_grafico(dist, "todos", None, "grupo_base",
                                           base_movil)
    doc.figura(fig1)

    doc.sub("De dónde sale el número")
    doc.partes.append(
        '<p class="sub">Aporte de cada grupo al índice del mes de corte.</p>')
    doc.tabla(charts.aporte_psi_grupo(dist, mes, "todos", None, "grupo_base",
                                      base_movil), maximo=14)

    # Nivel 2: sin selector, se elige el modelo de mayor población.
    if not dist.empty and dist["modelo"].notna().any():
        mod = (dist[dist["modelo"].notna()].groupby("modelo")["clientes"].sum()
               .sort_values(ascending=False).index[0])
        doc.sub(f"Nivel 2 · Por modelo — {mod}")
        doc.partes.append(
            f'<p class="sub">¿Qué población le está entrando a este modelo? Se '
            f'muestra <b>{mod}</b>, el de mayor población; en la app el modelo '
            f'se elige.</p>')
        doc.partes.append(
            f'<div class="banda" style="background:#fdf5e3;'
            f'border:1px solid {theme.ESTADO_ALERTA};color:#7a5800">'
            f'<b>Esto mide reasignación de población, no deriva del modelo.</b> '
            f'Si otro modelo se lleva parte de sus clientes, este PSI sube sin '
            f'que el modelo haya cambiado nada. Contrastar con «Vigencia de '
            f'modelos» y con el flujo entre modelos de la sección de '
            f'Migración.</div>')
        fig2, _, _ = charts.psi_grupos_grafico(dist, "todos", mod, "grupo_base",
                                               base_movil)
        doc.figura(fig2)

    doc.sub("Nivel 3 · Diagnóstico: PSI sobre la PD")
    doc.partes.append(
        '<p class="sub">¿Se movió la PD sin cruzar cortes? Sirve cuando el '
        'nivel 1 está tranquilo pero se sospecha deriva.</p>')
    fig3, n_m, n_t, descartados = charts.psi_pd_grafico(pdm, "general", base_movil)
    doc.figura(fig3)
    partes = []
    if n_t:
        partes.append(f"Mostrando los <b>{n_m} de {n_t}</b> modelos con mayor PSI.")
    if descartados:
        partes.append(
            f"Se descartaron <b>{descartados}</b> comparaciones de bin con menos "
            f"del 0,1% de población en alguno de los dos meses, y el resto se "
            f"renormalizó: sin eso, unos pocos clientes moviéndose entre bins "
            f"de cola irrelevantes producían PSI sostenidos de 1,5.")
    if partes:
        doc.nota(" ".join(partes))
    doc.cierra()

    generado = datetime.now().strftime("%d/%m/%Y %H:%M")
    return doc.render(
        "Calificaciones de riesgo — seguimiento de modelos",
        f"Ventana {theme.etiqueta_mes_idx(desde)} a {theme.etiqueta_mes_idx(hasta)} · "
        f"corte {theme.etiqueta_mes_idx(mes)} · rezago {rezago} · "
        f"versión de tablas <code>{data.idunico()}</code> · "
        f"generado el {generado}")


def main() -> int:
    p = argparse.ArgumentParser(description="Exporta el tablero a un HTML estático.")
    p.add_argument("--desde", type=int, default=202505, help="mes inicial, YYYYMM")
    p.add_argument("--hasta", type=int, default=202608, help="mes final, YYYYMM")
    p.add_argument("--mes", type=int, default=None, help="mes de corte, YYYYMM")
    p.add_argument("--rezago", type=int, default=1, choices=[1, 6])
    p.add_argument("--salida", type=Path, default=None)
    a = p.parse_args()

    def a_idx(yyyymm: int) -> int:
        return theme.idx_mes(int(yyyymm) // 100, int(yyyymm) % 100)

    desde, hasta = a_idx(a.desde), a_idx(a.hasta)
    mes = a_idx(a.mes) if a.mes else hasta

    html = construir(desde, hasta, mes, a.rezago)

    DIR_SALIDA.mkdir(exist_ok=True)
    destino = a.salida or (DIR_SALIDA /
                           f"calificaciones_{datetime.now():%Y%m%d_%H%M}.html")
    destino.write_text(html, encoding="utf-8")
    print(f"Escrito: {destino}  ({destino.stat().st_size / 1e6:.1f} MB)")
    print("Contiene datos: no subirlo al repositorio (exportes/ está en .gitignore).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
