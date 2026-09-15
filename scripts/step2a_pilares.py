"""Paso 2a — Columnas (RLE-PILAR) normalizadas a la grilla local.

Cada columna se dibuja como 4 LINEas formando un rectángulo cerrado y
ligeramente desplazado del nudo de grilla; el script:

  1. lee la grilla local (out/etapaN/grilla_local.json),
  2. agrupa las LINEas en rectángulos cerrados (matching de extremos),
  3. calcula centroide y dimensiones (m),
  4. asigna cada columna al nudo de grilla más cercano (eje X, eje Y).

Salidas:
    out/etapaN/pilares_<lamina>.json   (+ pilares_<lamina>.png)

Uso:
    python scripts/step2a_pilares.py [etapa] [lámina]
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

TOL = 1.0  # cm: tolerancia geométrica


def leer_grilla(etapa):
    p = OUT / f"etapa{etapa}" / "grilla_local.json"
    return json.loads(p.read_text(encoding="utf-8"))


def lineas_pilar(doc, capa="RLE-PILAR"):
    """LINEas de la capa → lista de (x1,y1,x2,y2) en cm (coordenadas de hoja)."""
    out = []
    for e in dxfio.entidades(doc, capa):
        if e.dxftype() != "LINE":
            continue
        s, p = e.dxf.start, e.dxf.end
        out.append((float(s[0]), float(s[1]), float(p[0]), float(p[1])))
    return out


def rectangulos(lineas):
    """Detecta rectángulos cerrados (ejes alineados) por matching de extremos."""
    hoz = {}  # y -> [(x1,x2)]
    ver = {}  # x -> [(y1,y2)]
    for x1, y1, x2, y2 in lineas:
        if abs(y1 - y2) <= TOL:          # horizontal
            hoz.setdefault(round(y1, 1), []).append(
                (round(min(x1, x2), 1), round(max(x1, x2), 1)))
        elif abs(x1 - x2) <= TOL:        # vertical
            ver.setdefault(round(x1, 1), []).append(
                (round(min(y1, y2), 1), round(max(y1, y2), 1)))
        else:
            continue
    usados = set()
    rects = []
    for yt, tops in hoz.items():
        for xt1, xt2 in tops:
            if abs(xt1 - xt2) <= TOL:
                continue
            # verticales en ambos extremos que LLEGUEN hasta este y (borde superior)
            v1 = [v for v in ver.get(xt1, []) if abs(v[1] - yt) <= TOL]
            v2 = [v for v in ver.get(xt2, []) if abs(v[1] - yt) <= TOL]
            for (ya1, _) in v1:
                for (ya2, _) in v2:
                    if abs(ya1 - ya2) > TOL:      # mismas alturas abajo
                        continue
                    # horizontal inferior de cierre
                    for (xb1, xb2) in hoz.get(ya1, []):
                        if (abs(xb1 - xt1) <= TOL and abs(xb2 - xt2) <= TOL
                                and abs(ya1 - yt) > TOL):
                            clave = (min(xt1, xt2), min(yt, ya1),
                                     max(xt1, xt2), max(yt, ya1))
                            if clave in usados:
                                continue
                            usados.add(clave)
                            rects.append(clave)
    return rects


def columnas_por_nudo(lineas, grilla, tol=0.5):
    """Por cada nudo de grilla, agrupa las lineas de pilar cuyas cajas caen en
    la vecindad del nudo y calcula bbox resultante. Tolera rectángulos
    incompletos (aristas omitidas). Devuelve lista de dicts con metros."""
    ejes_x = grilla["ejes_x_local_m"]
    ejes_y = grilla["ejes_y_local_m"]
    cols = []
    for ex in ejes_x:
        for ey in ejes_y:
            xg, yg = ex["x_m"], ey["y_m"]
            bx0, by0, bx1, by1 = xg - tol, yg - tol, xg + tol, yg + tol
            pts = []
            for x1, y1, x2, y2 in lineas:
                lx0, ly0 = min(x1, x2), min(y1, y2)
                lx1, ly1 = max(x1, x2), max(y1, y2)
                # la línea debe caber COMPLETA dentro de la vecindad del nudo
                # (±0.5 m): evita contaminar con detalles cercanos.
                if (lx0 >= bx0 and lx1 <= bx1 and ly0 >= by0 and ly1 <= by1):
                    pts.append((lx0, ly0, lx1, ly1))
            if len(pts) < 2:
                continue
            cx0 = min(p[0] for p in pts); cy0 = min(p[1] for p in pts)
            cx1 = max(p[2] for p in pts); cy1 = max(p[3] for p in pts)
            cols.append({
                "tag": f"C-{ex['etiqueta']}-{ey['etiqueta']}",
                "eje_x": ex["etiqueta"], "eje_y": ey["etiqueta"],
                "centro_m": {"x": round((cx0 + cx1) / 2, 3),
                             "y": round((cy0 + cy1) / 2, 3)},
                "b_m": round(cx1 - cx0, 3), "h_m": round(cy1 - cy0, 3),
                "b_cm": round((cx1 - cx0) * 100, 1),
                "h_cm": round((cy1 - cy0) * 100, 1),
            })
    cols.sort(key=lambda c: (c["eje_y"], c["eje_x"]))
    return cols


def main():
    etapa = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    lamina = sys.argv[2] if len(sys.argv) > 2 else "-101"

    grilla = leer_grilla(etapa)
    x0, y0 = grilla["origen_cm"]["x"], grilla["origen_cm"]["y"]

    doc = dxfio.cargar(planos_dir() / f"{prefijo(etapa)}{lamina}.dxf")
    lineas = [( (a - x0) / 100.0, (b - y0) / 100.0,    # cm hoja → m local
                (c - x0) / 100.0, (d - y0) / 100.0)
              for a, b, c, d in lineas_pilar(doc)]
    cols = columnas_por_nudo(lineas, grilla)
    out_dir = OUT / f"etapa{etapa}"
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {"etapa": etapa, "lamina": lamina, "columnas": cols}
    jp = out_dir / f"pilares_{lamina.strip('-')}.json"
    jp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(12, 9))
    for c in cols:
        x, y = c["centro_m"]["x"], c["centro_m"]["y"]
        ax.add_patch(Rectangle((x - c["b_m"], y - c["h_m"]),
                               c["b_m"], c["h_m"],
                               facecolor="tab:red", edgecolor="black", lw=0.5,
                               alpha=0.6))
        ax.text(x, y, c["tag"], fontsize=5, ha="center", va="center")
    for ex in grilla["ejes_x_local_m"]:
        ax.axvline(ex["x_m"], color="tab:red", lw=0.7, ls=":")
    for ey in grilla["ejes_y_local_m"]:
        ax.axhline(ey["y_m"], color="tab:blue", lw=0.7, ls=":")
    ax.set_aspect("equal")
    ax.set_title(f"Etapa {etapa} · {lamina} · columnas ({len(cols)})")
    fig.tight_layout()
    png = out_dir / f"pilares_{lamina.strip('-')}.png"
    fig.savefig(png, dpi=110)
    plt.close(fig)

    print(f"{len(cols)} columnas en {lamina}:")
    for c in cols:
        print(f"  {c['tag']:<18} centro=({c['centro_m']['x']:>6.2f},"
              f"{c['centro_m']['y']:>6.2f})  b={c['b_m']} h={c['h_m']}")
    print(f"-> {jp}  (+ {png.name})")


if __name__ == "__main__":
    raise SystemExit(main())