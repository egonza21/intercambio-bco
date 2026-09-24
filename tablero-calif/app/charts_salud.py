"""Chequeos de salud del dato y su único gráfico.

Cada chequeo devuelve un `Chequeo`: verde, rojo o SIN EJECUTAR, con una línea
de explicación y el detalle solo si falla.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go

import theme
from theme import aplicar_template as _t
from charts_base import (
    _sin_datos, banda_historica, leyenda_banda, registrar_guia)


@dataclass
class Chequeo:
    """Resultado de un chequeo. El estado es de TRES valores, no de dos.

    `ejecutado=False` es distinto de `ok=False`: un chequeo que no corrió no
    afirma nada. Antes esto se marcaba con un centinela en `nota`, que el
    banner global no miraba, así que un chequeo sin ejecutar contaba como
    aprobado. Es un campo propio justamente para que no se pueda ignorar.
    """
    nombre: str
    ok: bool
    resumen: str
    detalle: pd.DataFrame | None = None
    nota: str = ""
    ejecutado: bool = True
    # Pasó, pero hay algo que mirar que NO invalida los números: un modelo
    # nuevo con PD entre 0 y 1, por ejemplo. Es un cuarto estado y no un
    # "casi OK": si se pintara verde nadie lo abriría, y si se pintara rojo
    # el chequeo saltaría por cosas que no rompen nada y se dejaría de mirar.
    aviso: bool = False

    @property
    def estado(self) -> str:
        if not self.ejecutado:
            return "SIN EJECUTAR"
        if not self.ok:
            return "REVISAR"
        return "AVISO" if self.aviso else "OK"

    @property
    def color(self) -> str:
        if not self.ejecutado:
            return theme.INK_MUTED
        if not self.ok:
            return theme.ESTADO_CRITICO
        return theme.ESTADO_ALERTA if self.aviso else theme.ESTADO_OK

    @property
    def icono(self) -> str:
        if not self.ejecutado:
            return "○"
        if not self.ok:
            return "▲"
        return "◆" if self.aviso else "●"

    @property
    def tiene_detalle(self) -> bool:
        """El detalle se despliega si falla O si avisa."""
        return (self.ejecutado and (not self.ok or self.aviso)
                and self.detalle is not None and not self.detalle.empty)


def resumen_global(chequeos: list[Chequeo]) -> tuple[str, str, bool]:
    """Cuenta los tres estados por separado y arma el mensaje del banner.

    Devuelve (nivel, mensaje, todo_verde). El nivel es 'ok', 'alerta' o
    'aviso'. **Solo es verde si los cuatro se ejecutaron y los cuatro
    pasaron**: un archivo que afirma que todo está bien sin haber corrido un
    chequeo está diciendo algo que no verificó.
    """
    total = len(chequeos)
    fallan = [c for c in chequeos if c.ejecutado and not c.ok]
    sin_correr = [c for c in chequeos if not c.ejecutado]
    avisan = [c for c in chequeos if c.ejecutado and c.ok and c.aviso]
    pasan = total - len(fallan) - len(sin_correr)

    if fallan:
        partes = [f"{len(fallan)} de {total} chequeos piden revisión"]
        if sin_correr:
            partes.append(f"{len(sin_correr)} sin ejecutar")
        return ("alerta", ", ".join(partes) + ". Los números de las otras "
                "páginas pueden no significar lo que parecen.", False)
    if sin_correr:
        return ("aviso",
                f"{pasan} de {total} chequeos pasan, {len(sin_correr)} sin "
                f"ejecutar ({', '.join(c.nombre for c in sin_correr)}). "
                f"Mientras no corra, no hay nada verificado sobre ese punto.",
                False)
    if avisan:
        return ("aviso",
                f"Los {total} chequeos pasan, {len(avisan)} con avisos "
                f"({', '.join(c.nombre for c in avisan)}). No invalidan los "
                f"números, pero hay algo que actualizar.", False)
    return ("ok", f"Los {total} chequeos pasan. Los supuestos sobre los que se "
            f"apoya el resto del tablero se sostienen en esta ventana.", True)


def chequeo_ingestion_day(df: pd.DataFrame) -> Chequeo:
    """1. Un solo ingestion_day por mes.

    Todo el repo asume una fila por cliente + mes: sin eso, cada `count(*)`
    duplica en silencio. Ver CLAUDE.md, "La deduplicación por ingestion_day NO
    se hace en SQL".
    """
    if df.empty:
        return Chequeo("Un solo ingestion_day por mes", False,
                       "La consulta no devolvió filas: no se pudo verificar.")
    malos = df[df["dias_distintos"] > 1]
    if malos.empty:
        return Chequeo(
            "Un solo ingestion_day por mes", True,
            f"Los {len(df)} meses de la ventana traen una sola ingestión. "
            f"La premisa de una fila por cliente y mes se sostiene.")
    return Chequeo(
        "Un solo ingestion_day por mes", False,
        f"{len(malos)} de {len(df)} meses traen más de una ingestión. Los "
        f"conteos de esos meses están duplicados: hay que borrar la ingestión "
        f"sobrante antes de mirar cualquier otro número.",
        malos[["mes", "dias_distintos", "primer_dia", "ultimo_dia"]])


def chequeo_mapeo(df: pd.DataFrame) -> Chequeo:
    """2. El mapeo idx -> columna del unpivot está alineado.

    Un CASE desalineado no da error: etiqueta los datos con el producto
    equivocado. Contar por los dos caminos y comparar es la única forma de
    atraparlo.
    """
    nota = ("Es la consulta más lenta de la página: el lado ancho son 16 "
            "agregados, uno por producto, sobre la misma partición. Se corre "
            "sobre un solo mes por eso.")
    if df.empty:
        return Chequeo("Mapeo idx → columna alineado", False,
                       "La consulta no devolvió filas: no se pudo verificar.",
                       nota=nota)
    malos = df[df["diferencia"] != 0]
    if malos.empty:
        return Chequeo(
            "Mapeo idx → columna alineado", True,
            f"Los {len(df)} productos cuadran exactamente entre la tabla ancha "
            f"y la larga. El unpivot está etiquetando bien.", nota=nota)
    return Chequeo(
        "Mapeo idx → columna alineado", False,
        f"{len(malos)} de {len(df)} productos NO cuadran. Hay un CASE "
        f"desalineado en el unpivot: los datos están bien contados pero mal "
        f"etiquetados, así que todo el tablero atribuye clientes al producto "
        f"equivocado.", malos, nota=nota)


def chequeo_dominio(grupos: pd.DataFrame,
                    modelos: pd.DataFrame) -> Chequeo:
    """3. Dominio de grupos y escala de modelos.

    `modelos` es la salida de data.clasificar_modelos(): la MISMA regla que
    usa la construcción de pd_por_modelo, contra config/modelos.csv. Antes
    comparaba contra una lista de ocho en data.py, y como los modelos reales
    eran doce, marcaba novedad todos los meses. Un chequeo que salta siempre
    se deja de mirar, y entonces tampoco se mira el mes que importa.

    Severidades:
      REVISAR  grupo fuera del dominio, o un modelo cuya escala no cuadra con
               lo declarado (sus bins de PD salen mal).
      AVISO    modelo nuevo con PD entre 0 y 1, u otra cosa que pide
               actualizar el CSV pero no rompe los números.
      OK       lo demás. Los declarados que no aparecen van como nota.
    """
    esperados = set(theme.GRUPOS_ORDENADOS)
    g_raros = pd.DataFrame()
    if not grupos.empty:
        g_raros = grupos[~grupos["grupo"].isin(esperados)]

    m = modelos if modelos is not None else pd.DataFrame(
        columns=["modelo", "severidad", "motivo"])
    fallas = m[m["severidad"] == "falla"]
    avisos = m[m["severidad"] == "aviso"]
    ausentes = m[m["severidad"] == "info"]
    declarados = int((m["escala_declarada"] != "--").sum()) if not m.empty else 0

    nota = ""
    if not ausentes.empty:
        nota = (f"Declarados en config/modelos.csv que no aparecen en esta "
                f"ventana: {', '.join(ausentes['modelo'])}. No es un problema: "
                f"puede ser un modelo que ya no está vigente.")

    def _lista(df):
        return "; ".join(f"**{r.modelo}** — {r.motivo}" for r in df.itertuples())

    if g_raros.empty and fallas.empty and avisos.empty:
        return Chequeo(
            "Dominio de grupos y escala de modelos", True,
            f"Los grupos caen todos dentro de G1–G8 y las seis aperturas de "
            f"sufi. Cada modelo tiene la escala que declara config/modelos.csv "
            f"({declarados} declarados).", nota=nota)

    detalle = []
    if not g_raros.empty:
        detalle.append(g_raros.assign(hallazgo="grupo desconocido"))
    if not fallas.empty or not avisos.empty:
        detalle.append(pd.concat([fallas, avisos]).assign(hallazgo="modelo"))
    det = pd.concat(detalle, ignore_index=True) if detalle else None

    if not g_raros.empty or not fallas.empty:
        partes = []
        if not g_raros.empty:
            partes.append(f"{g_raros['grupo'].nunique()} valores de grupo fuera "
                          f"de G1–G8 y las aperturas conocidas")
        if not fallas.empty:
            partes.append(f"{len(fallas)} modelos con una escala que no cuadra "
                          f"con lo declarado: {_lista(fallas)}. Sus bins de PD "
                          f"salen mal, y la construcción de pd_por_modelo se "
                          f"aborta hasta corregir el CSV")
        if not avisos.empty:
            partes.append(f"además, {len(avisos)} avisos: {_lista(avisos)}")
        return Chequeo("Dominio de grupos y escala de modelos", False,
                       "Hay " + "; ".join(partes) + ".", det, nota=nota)

    return Chequeo(
        "Dominio de grupos y escala de modelos", True,
        f"Los grupos están bien y ningún modelo rompe su escala, pero hay "
        f"{len(avisos)} {'aviso' if len(avisos) == 1 else 'avisos'}: "
        f"{_lista(avisos)}. Si es un modelo nuevo, se agrega una línea a "
        f"config/modelos.csv.", det, nota=nota, aviso=True)


def chequeo_pd_grupo(df: pd.DataFrame) -> Chequeo:
    """4. PD y grupo concuerdan.

    Las filas con pd nula y grupo poblado existen (~726 en un mes) y no son un
    error: el filtro del tablero es por grupo. Lo que importa es que no
    crezcan, porque eso indicaría que la replicación de PD se está degradando.
    """
    if df.empty:
        return Chequeo("PD y grupo concuerdan", False,
                       "La consulta no devolvió filas: no se pudo verificar.")
    por_mes = (df.groupby(["idx_mes", "mes"], as_index=False)["pd_nulo_grupo_no_nulo"]
               .sum().sort_values("idx_mes"))
    ultimo = por_mes.iloc[-1]
    n = int(ultimo["pd_nulo_grupo_no_nulo"])
    if len(por_mes) < 2:
        return Chequeo(
            "PD y grupo concuerdan", True,
            f"{theme.fmt_miles(n)} filas con PD nula y grupo poblado en "
            f"{ultimo['mes']}. Con un solo mes en la ventana no hay contra qué "
            f"comparar la tendencia.")
    anterior = por_mes.iloc[-2]
    previo = int(anterior["pd_nulo_grupo_no_nulo"])
    # `iloc[-2]` es el mes disponible más cercano, que no siempre es el mes
    # calendario anterior. Se nombra el mes concreto y, si hay hueco, se dice.
    salto = int(ultimo["idx_mes"]) - int(anterior["idx_mes"])
    hueco = (f" (a {salto} meses: falta la partición intermedia)"
             if salto > 1 else "")
    if n <= previo:
        return Chequeo(
            "PD y grupo concuerdan", True,
            f"{theme.fmt_miles(n)} filas con PD nula y grupo poblado en "
            f"{ultimo['mes']}, contra {theme.fmt_miles(previo)} en "
            f"{anterior['mes']}{hueco}. No crece: la replicación de PD se "
            f"sostiene.")
    return Chequeo(
        "PD y grupo concuerdan", False,
        f"La discordancia CRECIÓ: {theme.fmt_miles(n)} filas en "
        f"{ultimo['mes']} contra {theme.fmt_miles(previo)} en "
        f"{anterior['mes']}{hueco} (+{theme.fmt_miles(n - previo)}). Que "
        f"existan no es un problema; que aumenten sugiere que el proceso que "
        f"replica la PD se está degradando.",
        (df[df["idx_mes"] == ultimo["idx_mes"]]
         [["mes", "producto", "filas_totales", "pd_nulo_grupo_no_nulo",
           "pd_no_nulo_grupo_nulo"]]
         .sort_values("pd_nulo_grupo_no_nulo", ascending=False)))


def discordancia_pd_grupo(df: pd.DataFrame) -> go.Figure:
    """Filas con PD nula y grupo poblado, por mes y producto.

    Es el único de los cuatro chequeos donde la tendencia dice algo: los otros
    tres son binarios. Si esta línea sube, la replicación de PD se degrada.

    Va SIEMPRE abierto por producto, nunca agregado en una sola serie. Hoy la
    discordancia está concentrada en un producto: si mañana aparece en otro, un
    total agregado podría no moverse lo suficiente para que se note, que es
    justo el caso que este gráfico existe para detectar.

    Solo entran los productos con algún valor distinto de cero en la ventana.
    Los que están en cero todo el tiempo quedan fuera de la leyenda, para que
    el gráfico no se llene de líneas planas donde no hay nada que mirar.
    """
    if df.empty:
        return _sin_datos()
    meses = sorted(df["idx_mes"].unique())
    etiquetas = [theme.etiqueta_mes_idx(m) for m in meses]

    # Productos con discordancia en ALGÚN mes. El filtro es sobre el total de
    # la ventana, no fila a fila: así un producto que tiene meses en cero
    # conserva esos ceros en su línea, en vez de quedar con huecos.
    total = (df.groupby("producto")["pd_nulo_grupo_no_nulo"].sum()
             .sort_values(ascending=False))
    activos = total[total > 0].index.tolist()
    if not activos:
        return _sin_datos("ningún producto con PD nula y grupo poblado "
                          "en esta ventana")

    principales, resto = activos[:4], activos[4:]
    fig = go.Figure()
    hubo = False
    for i, prod in enumerate(principales):
        s = (df[df["producto"] == prod].groupby("idx_mes")["pd_nulo_grupo_no_nulo"]
             .sum().reindex(meses).fillna(0))
        fig.add_scatter(
            x=etiquetas, y=s.values, name=prod, mode="lines+markers",
            line=dict(color=theme.SERIES[i], width=2, dash=theme.SERIES_DASH[i]),
            marker=dict(size=7, line=dict(color=theme.SURFACE, width=2)),
            hovertemplate=prod + " · %{y:,.0f} filas<extra></extra>")
        hubo = banda_historica(fig, s.values, theme.SERIES[i]) or hubo
    if resto:
        # Más de cuatro productos con discordancia ya es de por sí una señal:
        # se agregan para no salir de la paleta, pero el gráfico lo dice.
        s = (df[df["producto"].isin(resto)].groupby("idx_mes")["pd_nulo_grupo_no_nulo"]
             .sum().reindex(meses).fillna(0))
        fig.add_scatter(x=etiquetas, y=s.values,
                        name=f"otros {len(resto)} productos", mode="lines",
                        line=dict(color=theme.INK_MUTED, width=1.5, dash="dot"),
                        hovertemplate="otros · %{y:,.0f} filas<extra></extra>")
        fig.add_annotation(
            x=0, y=-0.22, xref="paper", yref="paper", xanchor="left",
            showarrow=False,
            text=f"Hay {len(activos)} productos con discordancia: "
                 f"{len(resto)} van agregados en «otros».",
            font=dict(size=11, color=theme.ESTADO_ALERTA, family=theme.FONT))

    if hubo:
        leyenda_banda(fig)
    fig.update_layout(height=360)
    fig.update_xaxes(title_text="")
    fig.update_yaxes(title_text="Filas con PD nula y grupo poblado",
                     tickformat=",.0f", rangemode="tozero")
    return _t(fig, unified=True)


# ===========================================================================
# GUÍAS DE LECTURA (ver charts_base.guia)
# ===========================================================================
registrar_guia(
    "chequeos",
    "Los cuatro supuestos sobre los que se apoya el resto del tablero, "
    "verificados sobre la ventana.",
    "Verde pasa; ámbar pasa con algo que actualizar; rojo pide revisión; gris "
    "no se ejecutó. El detalle se despliega solo si falla o avisa.",
    "Los cuatro en verde. Un rojo significa que los números de las otras "
    "páginas pueden no significar lo que parecen; un gris no afirma nada.")
registrar_guia(
    "discordancia_pd_grupo",
    "Filas con PD nula y grupo poblado, por producto, mes a mes.",
    "Una línea por producto con discordancia; la banda es su rango habitual.",
    "Que existan no es un problema: hoy se concentran en un producto. Llama "
    "la atención que crezcan o que aparezca un producto nuevo: la "
    "replicación de la PD se estaría degradando.")
