# -*- coding: utf-8 -*-
"""Barre todos los planos DXF de la Etapa 1 buscando anotaciones de nivel
(N.O.G., N.T.N., N.R., S1, 1°S, ±0.00, cotas de altura) en TEXTO/MTEXT.

Uso:
    python scripts/buscar_cotas_global.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ezdxf  # noqa: E402

from config.paths import planos_dir  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NIVEL = re.compile(
    r"(N\s*\.?\s*O\s*\.?\s*G|N\s*\.?\s*T\s*\.?\s*N|N\s*\.?\s*R\b|NIVEL"
    r"|\u00b1\s*0[.,]00|[+-]\d{1,2}[.,]\d\d\s+(m\b)?)",
    re.IGNORECASE,
)
PISO = re.compile(r"\b(1[jº°]\s*S|S[jº°]?\s*1|PISO\s+[1-9]|SUBTERR[|ÁA]NEO\s*[0-9]?)", re.IGNORECASE)


def main() -> int:
    d = planos_dir()
    for ruta in sorted(d.glob("2017_67-*.dxf")):
        try:
            doc = ezdxf.readfile(str(ruta))
        except Exception as err:
            print(ruta.name, "ERR", err)
            continue
        hits = []
        for e in doc.modelspace():
            if e.dxftype() not in ("TEXT", "MTEXT"):
                continue
            txt = (e.dxf.text if e.dxftype() == "TEXT" else e.text)
            if not txt:
                continue
            linea = txt.replace("\n", " · ").strip()
            if NIVEL.search(linea) or PISO.search(linea):
                p = e.dxf.insert
                hits.append((e.dxf.layer, p.x, p.y, linea))
        if hits:
            print(f"== {ruta.name} ==")
            for layer, x, y, linea in hits[:40]:
                print(f"  [{layer:14s}] ({x:9.1f},{y:9.1f}) {linea!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())