"""Nombres que no existen, detectados SIN ejecutar el código.

La prueba de figuras ejecuta los cuerpos, pero solo las ramas que sus casos
abren. Esta mira el código entero: todo nombre que una función usa como global
tiene que estar definido en su módulo, importado, o ser un builtin. Es
exactamente el error de `_FAM`: usado en charts_panorama y charts_modelos,
definido en otro módulo e importado en ninguno. Esta prueba lo habría marcado
aunque el filtro de familia no se usara nunca.

Usa `symtable`, de la biblioteca estándar: resuelve los ámbitos igual que el
compilador (funciones anidadas, lambdas, comprensiones) sin tener que
reimplementarlo.

También verifica que las referencias `charts.X`, `data.X` y `theme.X` de las
páginas, del export y de main.py existan, y que toda guía pedida esté
registrada.
"""
from __future__ import annotations

import builtins
import logging
import os
import re
import symtable
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP))
# Fuera de `streamlit run`, el caché avisa que no hay runtime. Streamlit arma
# sus loggers al importarse, así que un setLevel previo no alcanza: la opción
# de configuración sí la respeta.
os.environ.setdefault("STREAMLIT_LOGGER_LEVEL", "error")
logging.getLogger("streamlit").setLevel(logging.ERROR)

ARCHIVOS = sorted(APP.glob("*.py")) + sorted((APP / "pages").glob("*.py"))
# `__conditional_annotations__` lo agrega el compilador de Python 3.14 para las
# anotaciones diferidas (PEP 649); no es un nombre del código.
BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__",
                                 "__conditional_annotations__"}


def _definidos_en_modulo(tabla: symtable.SymbolTable) -> set[str]:
    return {s.get_name() for s in tabla.get_symbols()
            if s.is_assigned() or s.is_imported() or s.is_namespace()}


def nombres_indefinidos(ruta: Path) -> list[str]:
    src = ruta.read_text(encoding="utf-8")
    top = symtable.symtable(src, str(ruta), "exec")
    del_modulo = _definidos_en_modulo(top)
    problemas = []

    def recorrer(t: symtable.SymbolTable, camino: str) -> None:
        for s in t.get_symbols():
            n = s.get_name()
            if not s.is_referenced():
                continue
            implicito = (t.get_type() == "module" and not s.is_assigned()
                         and not s.is_imported() and not s.is_namespace()) \
                or (t.get_type() != "module" and s.is_global()
                    and not s.is_declared_global())
            if implicito and n not in del_modulo and n not in BUILTINS:
                problemas.append(f"{ruta.name}: `{n}` en {camino or 'nivel módulo'}")
        for hijo in t.get_children():
            recorrer(hijo, f"{camino}.{hijo.get_name()}".lstrip("."))

    recorrer(top, "")
    return problemas


class TestNombres(unittest.TestCase):
    def test_ningun_nombre_indefinido(self):
        problemas = [p for f in ARCHIVOS for p in nombres_indefinidos(f)]
        self.assertFalse(problemas, "nombres usados y no definidos:\n  "
                         + "\n  ".join(problemas))

    def test_referencias_a_modulos_existen(self):
        import charts
        import data
        import theme
        mods = {"charts": charts, "data": data, "theme": theme}
        rotas = []
        for f in sorted((APP / "pages").glob("*.py")) + [APP / "export.py", APP / "main.py"]:
            txt = f.read_text(encoding="utf-8")
            for mod, obj in mods.items():
                for n in sorted(set(re.findall(rf"\b{mod}\.([A-Za-z_]\w*)", txt))):
                    if n != "py" and not hasattr(obj, n):     # "charts.py" en prosa
                        rotas.append(f"{f.name}: {mod}.{n}")
        self.assertFalse(rotas, f"referencias que no existen: {rotas}")

    def test_guias_pedidas_estan_registradas(self):
        import charts
        pedidas = set()
        for f in sorted((APP / "pages").glob("*.py")) + [APP / "export.py"]:
            txt = f.read_text(encoding="utf-8")
            pedidas |= set(re.findall(r'(?:charts|doc)\.guia\("(\w+)"\)', txt))
        faltan = sorted(pedidas - set(charts.GUIAS))
        self.assertFalse(faltan, f"guías pedidas y no registradas: {faltan}")


if __name__ == "__main__":
    unittest.main()
