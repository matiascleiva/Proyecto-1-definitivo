"""Inspecciona textos significativos y círculos de un DXF (números reales,
etiquetas de ejes, radios) para calibrar escala. Uso:
    python scripts/calibrar_dxf.py <dxf>
"""
import math
import sys

import ezdxf


def main():
    doc = ezdxf.readfile(sys.argv[1])
    msp = doc.modelspace()

    print("== TEXTOS con valor numérico (capas estructurales) ==")
    omitir = {"RLA-FORMATO", "DEFPOINTS", "RLA-COTAS", "RLA-COTAS1"}
    for e in msp:
        if e.dxftype() not in ("TEXT", "MTEXT"):
            continue
        if e.dxf.layer in omitir:
            continue
        txt = (e.dxf.text if e.dxftype() == "TEXT"
               else e.text.replace("\n", " "))
        s = txt.strip()
        if not s:
            continue
        pos = e.dxf.insert
        try:
            val = float(s.replace(",", "."))
        except ValueError:
            continue
        print(f'  [{e.dxf.layer:<14}] {s:>12}  @ ({pos[0]:.1f},{pos[1]:.1f})')

    print("\n== DIMENSIONES con texto explícito (no automático) ==")
    for e in msp:
        if e.dxftype() != "DIMENSION":
            continue
        txt = getattr(e.dxf, "text", None) or ""
        if txt and txt != "?":
            p1 = e.dxf.defpoint
            p2 = e.dxf.defpoint2
            print(f"  [{e.dxf.layer}] {txt!r} L_papel={math.hypot(p1.x-p2.x, p1.y-p2.y):.1f}"
                  f" dp=({p1.x:.1f},{p1.y:.1f})/({p2.x:.1f},{p2.y:.1f})")

    print("\n== CIRCULOS (posibles columnas/hoyos) por capa ==")
    for e in msp:
        if e.dxftype() != "CIRCLE":
            continue
        c = e.dxf.center
        print(f"  [{e.dxf.layer:<12}] r={e.dxf.radius:8.3f} @ ({c.x:.1f},{c.y:.1f})")


if __name__ == "__main__":
    main()