# -*- coding: utf-8 -*-
"""Inspecciona los bloques de elevación de la Serie 300 de la Etapa 1.

Uso:
    python scripts/explorar_elevaciones.py <lámina: 300..310> [bloque]
      con bloque -> detalla su contenido (textos, cotas, líneas de nivel)
      sin bloque  -> lista los bloques INSERT de la lámina
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ezdxf  # noqa: E402

from config.paths import planos_dir, prefijo  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    lamina = sys.argv[1] if len(sys.argv) > 1 else "300"
    relevante = "--relevantes" in sys.argv or "--cota" in sys.argv
    ruta = planos_dir() / f"{prefijo(1)}-{lamina}.dxf"
    doc = ezdxf.readfile(str(ruta))

    if len(sys.argv) < 3 or sys.argv[2].startswith("--"):
        print(f"SERIE 300 · lámina {lamina}")
        for e in doc.modelspace():
            if e.dxftype() != "INSERT":
                continue
            if e.dxf.name in ("viñeta-rl", "Alfa"):
                continue
            ins = e.dxf.insert
            x = round(ins[0], 1)
            y = round(ins[1], 1)
            print(f"  INSERT {e.dxf.name!r:20s} @ ({x:9.1f}, {y:9.1f})")
        return 0

    nombre = sys.argv[2]
    try:
        b = doc.blocks.get(nombre)
    except KeyError:
        print(f"No existe el bloque {nombre!r} en {lamina}")
        return 1

    print(f"BLOQUE {nombre!r} (lámina {lamina}) — {sum(1 for _ in b)} entidades")

    from collections import Counter
    c = Counter((e.dxf.layer, e.dxftype()) for e in b)
    print("  capas:", ", ".join(f"{l}:{n}" for (l, t), n in c.most_common(10)))

    if relevante:
        _txt_f = lambda e: (e.dxf.text if e.dxftype() == "TEXT" else e.text).strip()
        print("\n-- TEXTOS RELEVANTES (niveles/cortes/números) --")
        for e in b:
            if e.dxftype() not in ("TEXT", "MTEXT"):
                continue
            txt = _txt_f(e)
            if not txt or not _es_relevante(txt):
                continue
            p = e.dxf.insert
            print(f"  ({p[0]:8.2f},{p[1]:8.2f}) {txt!r}")
        return 0

    print("\n-- TEXTOS --")
    for e in b:
        if e.dxftype() not in ("TEXT", "MTEXT"):
            continue
        txt = (e.dxf.text if e.dxftype() == "TEXT" else e.text).strip()
        if not txt:
            continue
        p = e.dxf.insert
        print(f"  ({p[0]:8.2f},{p[1]:8.2f}) {txt!r}")

    print("\n-- COTAS (DIMENSION) --")
    for e in b:
        if e.dxftype() != "DIMENSION":
            continue
        try:
            v = e.get_measurement()
        except Exception:
            v = None
        txt = getattr(e.dxf, "text", "")
        print(f"  txt={txt!r:<12s} medición={v}")

    print("\n-- LÍNEAS por capa (conteo) --")
    for (layer, typ), n in Counter(
        (e.dxf.layer, e.dxftype()) for e in b
    ).most_common(12):
        print(f"  {n:4d} {layer:14s} {typ}")
    return 0


def _es_relevante(txt: str) -> bool:
    up = txt.upper()
    if "CORTE" in up or "COTA" in up:
        return True
    if any(m in up for m in ("N.R", "N.O.G", "1º", "2º", "3º", "4º", "PISO",
                             "SUBTERR", "NIVEL")):
        return True
    if txt in ("±0.00", "0.00") or txt.startswith(("+", "-")):
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())