"""Explorador de plano DXF — vuelca estructura, capas, textos y dimensiones.

Uso:
    python scripts/explorar_dxf.py <ruta.dxf> [--textos N] [--capas] [--lineas N]
"""
import sys
from pathlib import Path

import ezdxf


def main():
    ruta = Path(sys.argv[1])
    n_textos = 40
    n_lineas = 0
    flag_capas = "--capas" in sys.argv
    for a in sys.argv[2:]:
        if a.startswith("--textos"):
            n_textos = int(sys.argv[sys.argv.index(a) + 1])
        if a.startswith("--lineas"):
            n_lineas = int(sys.argv[sys.argv.index(a) + 1])

    doc = ezdxf.readfile(str(ruta))
    msp = doc.modelspace()
    print(f"ARCHIVO {ruta}\n  entidades: {len(msp)}")
    layers = {}
    for e in msp:
        layers[e.dxftype()] = layers.get(e.dxftype(), 0) + 1
    for t, c in sorted(layers.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")

    if flag_capas:
        print("\nCAPAS:")
        for l in doc.layers:
            print(f"  {l.dxf.name}  color={l.dxf.color}  on={l.is_on()}")

    texts = [e for e in msp if e.dxftype() in ("TEXT", "MTEXT")]
    print(f"\nTEXTOS ({len(texts)}):")
    for t in texts[:n_textos]:
        txt = (t.dxf.text if t.dxftype() == "TEXT" else
               t.text.replace("\n", " ")) if True else ""
        pt = t.dxf.insert
        print(f'  [{t.dxf.layer}] "{txt}" @ ({pt[0]:.2f}, {pt[1]:.2f})')

    if n_lineas:
        lignes = [e for e in msp if e.dxftype() == "LINE"]
        print(f"\nLINEAS (primeras {n_lineas}):")
        for e in lignes[:n_lineas]:
            print(f"  [{e.dxf.layer}] ({e.dxf.start.x:.2f},{e.dxf.start.y:.2f}) -> "
                  f"({e.dxf.end.x:.2f},{e.dxf.end.y:.2f})")

    if "--dimensiones" in sys.argv:
        import math
        print("\n=== DIMENSIONES (cotas) ===")
        n = 0
        for e in msp:
            if e.dxftype() != "DIMENSION":
                continue
            if e.dxf.layer not in ("RLA-COTAS", "RLA-COTAS1"):
                continue
            txt = getattr(e.dxf, "text", None) or "?"
            p1 = e.dxf.defpoint
            p2 = e.dxf.defpoint2
            if e.dimtype in (0, 1):
                L = math.hypot(p1[0] - p2[0], p1[1] - p2[1])
                print(f"  [{e.dxf.layer}] dimtype={e.dimtype} txt={txt!r} "
                      f"L_papel={L:7.1f} defpoints=({p1[0]:.1f},{p1[1]:.1f})/"
                      f"({p2[0]:.1f},{p2[1]:.1f})")
            elif e.dimtype == 4:
                print(f"  [{e.dxf.layer}] RADIAL txt={txt!r} r_papel={e.dxf.actual_measurement:.1f}")
            else:
                print(f"  [{e.dxf.layer}] dimtype={e.dimtype} txt={txt!r}")
            n += 1
            if n >= 80:
                break

    if "--estructural" in sys.argv:
        xs, ys = [], []
        for e in msp:
            if e.dxf.layer in ("RLA-FORMATO", "DEFPOINTS", "RLA-COTAS",
                               "RLA-COTAS1", "CONTORNOS"):
                continue
            if e.dxftype() == "LINE":
                xs += [e.dxf.start.x, e.dxf.end.x]
                ys += [e.dxf.start.y, e.dxf.end.y]
            elif e.dxftype() == "CIRCLE":
                xs.append(e.dxf.center.x)
                ys.append(e.dxf.center.y)
            elif e.dxftype() in ("MTEXT", "TEXT"):
                p = e.dxf.insert
                xs.append(p[0])
                ys.append(p[1])
        print(f"  BBox contenido: X {min(xs):.1f}..{max(xs):.1f}  "
              f"Y {min(ys):.1f}..{max(ys):.1f}  "
              f"(L={max(xs)-min(xs):.1f}, W={max(ys)-min(ys):.1f})")

        un_dx, un_dy = set(), set()
        for e in msp:
            if e.dxftype() == "LINE" and e.dxf.layer == "RLE-EJES":
                p1, p2 = e.dxf.start, e.dxf.end
                if abs(p1.y - p2.y) < 0.01:
                    un_dy.add(round(p1.y, 3))
                if abs(p1.x - p2.x) < 0.01:
                    un_dx.add(round(p1.x, 3))
        print("  Coord. ejes X (lineas horizontales):", sorted(un_dy))
        print("  Coord. ejes Y (lineas verticales):", sorted(un_dx))

        print("  Etiquetas de ejes (TEXT/MTEXT RLE-EJE):")
        for t in msp:
            if t.dxftype() in ("MTEXT", "TEXT") and t.dxf.layer == "RLE-EJE":
                txt = t.dxf.text if t.dxftype() == "TEXT" else t.text.strip()
                p = t.dxf.insert
                print(f"    \"{txt}\" @ ({p[0]:.1f}, {p[1]:.1f})")


if __name__ == "__main__":
    main()