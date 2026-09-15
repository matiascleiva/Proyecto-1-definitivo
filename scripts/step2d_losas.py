"""Paso 2d — Losas (RLE-LOSA) normalizadas a la grilla local.

Los bordes de losa se dibujan como LINEas (borde de paño sobre las caras
de columnas/vigas, con huecos en los apoyos) y los huecos de losa como
polilíneas cerradas. Este paso:
  1. reconstruye la huella (rectángulo envolvente de los bordes dibujados),
  2. cuenta la cobertura de cada lado de la huella (detección de faltantes),
  3. registra los huecos cerrados interiores,
  4. calcula área bruta y neta.

Salidas:
    out/etapaN/losas_<lamina>.json   (+ losas_<lamina>.png)

Uso:
    python scripts/step2d_losas.py [etapa] [lámina]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from config.paths import OUT, planos_dir, prefijo  # noqa: E402
from src.extract import dxfio  # noqa: E402

MARGEN_X = 4.5   # m: captura zona de rampa/junta en X
MARGEN_Y = 2.5   # m: volados de losa en Y (excluye el subterráneo y 2ª copia)


def leer_grilla(etapa):
    p = OUT / f"etapa{etapa}" / "grilla_local.json"
    return json.loads(p.read_text(encoding="utf-8"))


def bordes_losa(doc, capa, x0, y0, xmin, xmax, ymin, ymax):
    """Segmentos LINE de losa completamente dentro de la región."""
    segs = []
    for e in dxfio.entidades(doc, capa):
        if e.dxftype() != "LINE":
            continue
        s, p = e.dxf.start, e.dxf.end
        la, lb = (s[0] - x0) / 100.0, (s[1] - y0) / 100.0
        lc, ld = (p[0] - x0) / 100.0, (p[1] - y0) / 100.0
        if (min(la, lc) >= xmin and max(la, lc) <= xmax
                and min(lb, ld) >= ymin and max(lb, ld) <= ymax):
            segs.append((la, lb, lc, ld))
    return segs


def huecos_cerrados(doc, capa, x0, y0, xmin, xmax, ymin, ymax):
    """LWPOLYLINE cerradas como huecos de losa (polígono interior)."""
    huecos = []
    for e in dxfio.entidades(doc, capa):
        if e.dxftype() != "LWPOLYLINE" or not e.is_closed:
            continue
        pts = [((a - x0) / 100.0, (b - y0) / 100.0) for a, b, *_ in e.get_points()]
        if (min(p[0] for p in pts) >= xmin and max(p[0] for p in pts) <= xmax
                and min(p[1] for p in pts) >= ymin
                and max(p[1] for p in pts) <= ymax):
            huecos.append(pts)
    return huecos


def area_poligono(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def cobertura_por_lado(segs, xmin, xmax, ymin, ymax, tol=0.08):
    """Para cada lado cardinal de la huella, intervalos de borde dibujado."""
    lados = {"inferior": [], "superior": [], "izquierdo": [], "derecho": []}
    for x1, y1, x2, y2 in segs:
        a, b = min(x1, x2), max(x1, x2)
        c, d = min(y1, y2), max(y1, y2)
        if abs(c - ymin) <= tol and abs(d - ymin) <= tol:
            lados["inferior"].append((round(a, 3), round(b, 3)))
        elif abs(c - ymax) <= tol and abs(d - ymax) <= tol:
            lados["superior"].append((round(a, 3), round(b, 3)))
        elif abs(a - xmin) <= tol and abs(b - xmin) <= tol:
            lados["izquierdo"].append((round(c, 3), round(d, 3)))
        elif abs(a - xmax) <= tol and abs(b - xmax) <= tol:
            lados["derecho"].append((round(c, 3), round(d, 3)))
    return lados


def calibre(intervalos, total):
    """Largo cubierto y huecos de cada lado."""
    ints = sorted(intervalos)
    largo = 0.0
    huecos = []
    ult = 0.0
    for a, b in ints:
        a = max(a, 0.0)
        b = min(b, total)
        if a < ult:
            a = ult
        if b > a:
            largo += b - a
            ult = max(ult, b)
    pos = 0.0
    for a, b in ints:
        if a > pos + 0.15:
            huecos.append((round(pos, 3), round(a, 3)))
        pos = max(pos, b)
    if total > pos + 0.15:
        huecos.append((round(pos, 3), round(total, 3)))
    return round(largo, 2), huecos


def main():
    etapa = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    lamina = sys.argv[2] if len(sys.argv) > 2 else "-101"

    grilla = leer_grilla(etapa)
    x0, y0 = grilla["origen_cm"]["x"], grilla["origen_cm"]["y"]
    gx = [e["x_m"] for e in grilla["ejes_x_local_m"]]
    gy = [e["y_m"] for e in grilla["ejes_y_local_m"]]
    xmin, xmax = min(gx) - MARGEN_X, max(gx) + MARGEN_X
    ymin, ymax = min(gy) - MARGEN_Y, max(gy) + MARGEN_Y

    doc = dxfio.cargar(planos_dir() / f"{prefijo(etapa)}{lamina}.dxf")
    segs = bordes_losa(doc, "RLE-LOSA", x0, y0, xmin, xmax, ymin, ymax)
    huecos = huecos_cerrados(doc, "RLE-LOSA", x0, y0, xmin, xmax, ymin, ymax)

    # huella envolvente de los bordes dibujados, anclada a las caras de eje
    if segs:
        fx = [v for s in segs for v in (s[0], s[2])]
        fy = [v for s in segs for v in (s[1], s[3])]
        hx0, hy0, hx1, hy1 = min(fx), min(fy), max(fx), max(fy)
    else:
        hx0, hy0, hx1, hy1 = xmin, ymin, xmax, ymax
    cara = 0.35                  # cara de viga/columna sobre el eje
    volado = 1.15                # volado de losa observado (y=17.3)
    hx0 = round(max(hx0, min(gx) - cara), 3)
    hx1 = round(min(hx1, max(gx) + cara), 3)
    hy0 = round(max(hy0, min(gy) - cara), 3)
    hy1 = round(max(hy1, max(gy) + volado), 3)

    lados = cobertura_por_lado(segs, hx0, hx1, hy0, hy1)
    resumen = {}
    an = (hx1 - hx0) * (hy1 - hy0)
    for lado, ints in lados.items():
        largo, huecos_lado = calibre(ints,
                                     (hx1 - hx0) if lado in ("inferior", "superior")
                                     else (hy1 - hy0))
        resumen[lado] = {"cubierto_m": largo, "huecos_m": huecos_lado}

    huecos_info = []
    for pts in huecos:
        huecos_info.append({
            "poligono": [tuple(round(float(v), 3) for v in p) for p in pts],
            "area_m2": round(area_poligono(pts), 3),
        })
    area_neta = round(an - sum(h["area_m2"] for h in huecos_info), 2)

    out_dir = OUT / f"etapa{etapa}"
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "etapa": etapa, "lamina": lamina,
        "huella_m": {"x0": round(hx0, 3), "y0": round(hy0, 3),
                     "x1": round(hx1, 3), "y1": round(hy1, 3)},
        "largo_x_m": round(hx1 - hx0, 3), "largo_y_m": round(hy1 - hy0, 3),
        "area_bruta_m2": round(an, 2), "area_neta_m2": area_neta,
        "cobertura_por_lado": resumen,
        "huecos": huecos_info,
    }
    jp = out_dir / f"losas_{lamina.strip('-')}.json"
    jp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(12, 9))
    ax.add_patch(Rectangle((hx0, hy0), hx1 - hx0, hy1 - hy0,
                           fill=False, ec="tab:orange", lw=1.4))
    for s in segs:
        ax.plot([s[0], s[2]], [s[1], s[3]], color="tab:purple", lw=1.1)
    for pts in huecos:
        xs = [p[0] for p in pts] + [pts[0][0]]
        ys = [p[1] for p in pts] + [pts[0][1]]
        ax.fill(xs, ys, color="tab:red", alpha=0.5)
    for ex in gx:
        ax.axvline(ex, color="tab:red", lw=0.7, ls=":")
    for ey in gy:
        ax.axhline(ey, color="tab:blue", lw=0.7, ls=":")
    ax.set_aspect("equal")
    ax.set_title(f"Etapa {etapa} · {lamina} · losa (A={data['area_neta_m2']} m² neta)")
    fig.tight_layout()
    png = out_dir / f"losas_{lamina.strip('-')}.png"
    fig.savefig(png, dpi=110)
    plt.close(fig)

    print(f"Huella losa {lamina}: {hx0}..{hx1} x {hy0}..{hy1} m"
          f"  (A bruta={data['area_bruta_m2']} m², neta={area_neta} m²)")
    for lado, r in resumen.items():
        print(f"  lat {lado:11}: cubierto {r['cubierto_m']:>6.2f} m"
              + (f"   huecos: {r['huecos_m']}" if r["huecos_m"] else ""))
    if huecos_info:
        for h in huecos_info:
            print(f"  hueco: {h['poligono']}  A={h['area_m2']} m²")
    else:
        print("  huecos: ninguno (revisar vanos de ascensor/escalera)")
    print(f"-> {jp}  (+ {png.name})")


if __name__ == "__main__":
    raise SystemExit(main())