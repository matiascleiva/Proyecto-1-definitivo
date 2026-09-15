# -*- coding: utf-8 -*-
"""Barre los bloques de elevación de la Serie 300 en busca de anotaciones de
nivel (N.O.G., N.R., ±0.00) y números de cota con formato decimal."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ezdxf  # noqa: E402

from config.paths import planos_dir, prefijo  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PAT = re.compile(r"(N\s*\.?\s*O\s*\.?\s*G|N\s*\.?\s*R|\u00b1\s*0{1,2}\.\s*0{1,2}|\d+[.,]\d\d\s*$|\d[.,]\d\d)")

SKIP = {"viñeta-rl", "Alfa", "*Model_Space", "*Paper_Space"}


def main() -> int:
    for lamina in [str(n) for n in range(300, 311)]:
        ruta = planos_dir() / f"{prefijo(1)}-{lamina}.dxf"
        doc = ezdxf.readfile(str(ruta))
        hallazgos = []
        for blk in doc.blocks:
            nombre = blk.name
            if nombre in SKIP or nombre.startswith("*"):
                continue
            for e in blk:
                if e.dxftype() not in ("TEXT", "MTEXT"):
                    continue
                txt = (e.dxf.text if e.dxftype() == "TEXT" else e.text)
                txt = txt.replace("\n", " ").strip()
                if txt and PAT.search(txt):
                    p = e.dxf.insert
                    hallazgos.append((nombre, p.x, p.y, txt))
        if hallazgos:
            print(f"== lámina {lamina} ==")
            for nombre, x, y, txt in hallazgos:
                print(f"  [{nombre:14s}] ({x:9.2f},{y:9.2f}) {txt!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())