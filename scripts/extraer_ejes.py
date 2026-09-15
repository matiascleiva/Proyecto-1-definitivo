"""Extrae los ejes (líneas largas RLE-EJES) de un plano para definir la grilla.

Uso:
    python scripts/extraer_ejes.py <dxf> [--min-len 1000]
"""
import sys

import ezdxf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MIN_LEN = 1000.0  # u (1 u = 1 cm) → 10 m, para descartar segmentos cortos


def main():
    global MIN_LEN
    ruta = sys.argv[1]
    if "--min-len" in sys.argv:
        MIN_LEN = float(sys.argv[sys.argv.index("--min-len") + 1])
    doc = ezdxf.readfile(ruta)
    msp = doc.modelspace()

    vert = {}   # x -> (min_y, max_y, n)
    horz = {}   # y -> (min_x, max_x, n)
    for e in msp:
        if e.dxftype() != "LINE" or e.dxf.layer != "RLE-EJES":
            continue
        a, b = e.dxf.start, e.dxf.end
        L = ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
        if L < MIN_LEN:
            continue
        if abs(a.x - b.x) < 1.0:      # línea vertical de eje
            x = a.x
            y0, y1 = sorted((a.y, b.y))
            v = vert.get(x)
            vert[x] = (min(v[0], y0) if v else y0,
                       max(v[1], y1) if v else y1, v[2] + 1 if v else 1)
        elif abs(a.y - b.y) < 1.0:    # línea horizontal de eje
            y = a.y
            x0, x1 = sorted((a.x, b.x))
            v = horz.get(y)
            horz[y] = (min(v[0], x0) if v else x0,
                       max(v[1], x1) if v else x1, v[2] + 1 if v else 1)

    print("EJES VERTICALES (lineas |, coordenada X = sheet-x):")
    for x, (y0, y1, n) in sorted(vert.items()):
        print(f"  X={x/100:8.2f} m  | sheet-x={x:8.1f} u  | y {y0/100:7.2f}..{y1/100:7.2f} m | {n}")
    print("EJES HORIZONTALES (lineas --, coordenada Y = sheet-y):")
    for y, (x0, x1, n) in sorted(horz.items()):
        print(f"  Y={y/100:8.2f} m  | sheet-y={y:8.1f} u  | x {x0/100:7.2f}..{x1/100:7.2f} m | {n}")


if __name__ == "__main__":
    main()