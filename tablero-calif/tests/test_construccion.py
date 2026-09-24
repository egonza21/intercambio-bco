"""El SQL que la app manda a Impala, armado sin ejecutarlo.

Existe porque "Reconstruir todo" se rompió en la primera sentencia de 01: el
marcador {PRODUCTOS_DECLARADOS} se resolvía ANTES de quitar los comentarios,
y como el encabezado de 01 lo nombra, 15 líneas de SQL quedaron pegadas
delante del primer `drop`. La verificación de entonces miró solo la sentencia
que crea tmp_productos y el conteo total, que no cambiaba.

Por eso acá se revisa CADA sentencia de CADA script:

  - empieza con un comando que la construcción usa (drop, create, compute
    stats) o es una verificación marcada;
  - no le queda ningún marcador sin resolver;
  - las tmp_ que crea un script son las mismas que borra;
  - el conteo por script y el total coinciden con sql/20_construccion/00_orden.md.

Y cada sentencia de sql/00_perfilado/ empieza con `with` o `select`.

No hace falta Impala ni el helper: data.pasos() y data._leer_perfilado() solo
arman texto.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))
os.environ.setdefault("STREAMLIT_LOGGER_LEVEL", "error")
logging.getLogger("streamlit").setLevel(logging.ERROR)

import data  # noqa: E402

COMANDO = re.compile(r"^(drop table if exists|create table|compute stats)\s", re.I)
MARCADOR = re.compile(r"\{[A-Z_]+\}")          # {IDUNICO}, {MODELOS_DECLARADOS}...
IDU = "vprueba"


def _pasos():
    return {r.name: data.pasos(r, IDU) for r in data.scripts_construccion()}


class TestConstruccion(unittest.TestCase):
    def test_cada_sentencia_empieza_con_un_comando(self):
        for script, ps in _pasos().items():
            for i, p in enumerate(ps, 1):
                if p.startswith("@@verificacion:"):
                    continue
                with self.subTest(script=script, sentencia=i):
                    self.assertRegex(
                        p, COMANDO,
                        f"la sentencia {i} de {script} no empieza con un comando: "
                        f"{p[:120]!r}")

    def test_ningun_marcador_sin_resolver(self):
        for script, ps in _pasos().items():
            for i, p in enumerate(ps, 1):
                with self.subTest(script=script, sentencia=i):
                    self.assertIsNone(MARCADOR.search(p),
                                      f"marcador sin resolver en {script}: "
                                      f"{MARCADOR.search(p)}")
                    self.assertNotIn("{", p, f"llave suelta en {script}: {p[:120]!r}")

    def test_tmp_creadas_son_las_borradas(self):
        for script, ps in _pasos().items():
            sql = "\n".join(ps)
            creadas = set(re.findall(rf"create table \w+\.(tmp_\w+)_{IDU}\b", sql))
            borradas = set(re.findall(rf"drop table if exists \w+\.(tmp_\w+)_{IDU}\b", sql))
            with self.subTest(script=script):
                self.assertEqual(creadas, borradas)

    def test_conteos_coinciden_con_00_orden(self):
        doc = (RAIZ / "sql/20_construccion/00_orden.md").read_text(encoding="utf-8")
        por_script = {f"{n}.sql": int(c) for n, c in
                      re.findall(r"^\|\s*(\d\d_\w+)\s*\|\s*(\d+)\s*\|", doc, re.M)}
        reales = {s: sum(1 for p in ps if not p.startswith("@@"))
                  for s, ps in _pasos().items()}
        self.assertEqual(reales, por_script, "00_orden.md no coincide con el SQL")
        total = int(re.search(r"\*\*total\*\*\s*\|\s*\*\*(\d+)\*\*", doc).group(1))
        self.assertEqual(sum(reales.values()), total)

    def test_verificaciones_conocidas(self):
        for script, ps in _pasos().items():
            for p in ps:
                if p.startswith("@@verificacion:"):
                    with self.subTest(script=script):
                        self.assertIn(p.split(":", 1)[1], data._VERIFICACIONES)


class TestPerfilado(unittest.TestCase):
    def test_cada_sentencia_es_una_consulta(self):
        for ruta in sorted((RAIZ / "sql/00_perfilado").glob("*.sql")):
            codigo = "\n".join(l for l in ruta.read_text(encoding="utf-8").splitlines()
                               if not l.strip().startswith("--"))
            n = len([p for p in codigo.split(";") if p.strip()])
            for i in range(n):
                with self.subTest(consulta=ruta.name, sentencia=i + 1):
                    q = data._leer_perfilado(ruta.name, i)
                    self.assertRegex(q, r"^(with|select)\s", q[:120])
                    self.assertIsNone(MARCADOR.search(q), f"marcador sin resolver: {q[:120]}")


if __name__ == "__main__":
    unittest.main()
