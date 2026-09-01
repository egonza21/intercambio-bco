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
            'salen de <code>sql/10_agregados/</code>; las figuras, de '
            '<code>app/charts.py</code>, las mismas que muestra la app.<br>'
            'Este archivo contiene datos: no subirlo al repositorio.</footer>'
            "</div></body></html>")


def construir(desde: int, hasta: int, mes: int, rezago: int) -> str:
    doc = Doc()

    dist = data.distribucion_grupo(desde, hasta)
    base = data.base_clientes(desde, hasta)
    cob = data.cobertura_producto(desde, hasta)
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
    doc.cierra()

    # --- 2. Evolución ------------------------------------------------------
    doc.seccion("evolucion", "Evolución",
                f"De {theme.etiqueta_mes_idx(desde)} a {theme.etiqueta_mes_idx(hasta)}.")
    doc.sub("Mezcla de riesgo — consumo")
    doc.figura(charts.mezcla_riesgo(dist, "consumo"))
    doc.sub("Base de clientes")
    doc.figura(charts.base_clientes_tiempo(base))
    doc.sub("Vigencia de modelos")
    doc.figura(charts.vigencia_modelos(dist))
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
        mig = data.migracion(desde_ok, hasta, rezago)
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
        mig_pd = data.migracion_pd(desde_ok, hasta, rezago)
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
    pdm = data.pd_por_modelo(desde, hasta)
    cortes = data.cortes_por_producto(desde, hasta)
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
    doc.sub("PSI en el tiempo — serie general")
    doc.figura(charts.psi_tiempo(pdm, "general"))
    doc.cierra()

    generado = datetime.now().strftime("%d/%m/%Y %H:%M")
    return doc.render(
        "Calificaciones de riesgo — seguimiento de modelos",
        f"Ventana {theme.etiqueta_mes_idx(desde)} a {theme.etiqueta_mes_idx(hasta)} · "
        f"corte {theme.etiqueta_mes_idx(mes)} · rezago {rezago} · "
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
