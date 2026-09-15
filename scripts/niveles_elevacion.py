# -*- coding: utf-8 -*-
"""Extrae las líneas de nivel y los textos de cota de un bloque de elevación.

Uso:
    python scripts/niveles_elevacion.py <lamina: 300..310> <bloque>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ezdxf  # noqa: E402

from config.paths import planos_dir, prefijo  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    lamina = sys.argv[1]
    nombre = sys.argv[2]
    doc = ezdxf.readfile(str(planos_dir() / f"{prefijo(1)}-{lamina}.dxf"))
    b = doc.blocks.get(nombre)

    print(f"BLOQUE {nombre!r} — textos de cota (RLA*COTA*)")
    for e in b:
        if e.dxftype() in ("TEXT", "MTEXT") and "COTA" in e.dxf.layer:
            txt = (e.dxf.text if e.dxftype() == "TEXT" else e.text).strip()
            p = e.dxf.insert
            if txt:
                print(f"  [{e.dxf.layer:18s}] ({p[0]:9.2f},{p[1]:9.2f}) {txt!r}")

    # Líneas horizontales largas (posibles líneas de nivel/fachadas)
    def cota_horiz(e):
        s, t = e.dxf.start, e.dxf.end
        return abs(s.y - t.y) < 5.0

    lh = [(e,) for e in b if e.dxftype() == "LINE" and cota_horiz(e)
          and abs(e.dxf.start.x - e.dxf.end.x) > 400.0]
    ys = {}
    for (e,) in lh:
        s, t = e.dxf.start, e.dxf.end
        yk = round(s.y)
        x0, x1 = sorted((s.x, t.x))
        q = ys.setdefault(yk, [])
        q.append((x0, x1, e.dxf.layer))
    print(f"\n  líneas horizontales largas (>4 m) — {len(lh)} total, "
          f"{len(ys)} niveles distintos")
    for y in sorted(ys, reverse=True):
        segs = ys[y]
        lon = max(a[1] - a[0] for a in segs)
        x0 = min(a[0] for a in segs)
        x1 = max(a[1] for a in segs)
        print(f"  y={y:9.2f}  x {x0:9.1f}..{x1:9.1f}  lon_max {lon:7.1f}  n={len(segs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())