"""Paso 2b — Vigas (RLE-VIGA) normalizadas a la grilla local.

En planta, cada viga se dibuja como un rectángulo (dos LINEas paralelas)
centrado sobre el eje de grilla y limitado por las caras de las columnas;
el ancho del rectángulo (dimensión transversal al eje) es el ancho de la
viga (b). El modelo la representa de nudo a nudo (luces entre ejes).

Salidas:
    out/etapaN/vigas_<lamina>.json   (+ vigas_<lamina>.png)

Uso:
    python scripts/step2b_vigas.py [etapa] [lámina]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from config.paths import OUT, planos_dir, prefijo  # noqa: E402
from src.extract import dxfio  # noqa: E402


def leer_grilla(etapa):
    p = OUT / f"etapa{etapa}" / "grilla_local.json"
    return json.loads(p.read_text(encoding="utf-8"))


def lineas_capa(doc, capa):
    """LINEas de la capa → lista de (x1,y1,x2,y2) en m local."""
    out = []
    for e in dxfio.entidades(doc, capa):
        if e.dxftype() != "LINE":
            continue
        s, p = e.dxf.start, e.dxf.end
        out.append((float(s[0]), float(s[1]), float(p[0]), float(p[1])))
    return out


def vigas_por_ejes(lineas, grilla):
    """Detecta vigas emparejando las dos caras paralelas (rect de dos LINEas)
    y fusionando tramos colineales sobre un mismo centro. Clasifica en
    primaria (extremos sobre ejes de columnas) o secundaria."""
    X = grilla["ejes_x_local_m"]
    Y = grilla["ejes_y_local_m"]
    xs = {e["etiqueta"]: e["x_m"] for e in X}
    ys = {e["etiqueta"]: e["y_m"] for e in Y}

    hor = []   # (a, b, y) con a,b = extremos X
    ver = []   # (a, b, x) con a,b = extremos Y
    for lx0, ly0, lx1, ly1 in lineas:
        a, b = min(lx0, lx1), max(lx0, lx1)
        c, d = min(ly0, ly1), max(ly0, ly1)
        if (b - a) >= 1.0 and (d - c) < 0.05:
            hor.append((a, b, round((c + d) / 2, 2)))
        elif (d - c) >= 1.0 and (b - a) < 0.05:
            ver.append((c, d, round((a + b) / 2, 2)))

    def fusionar(lista):
        """Fusiona segmentos colineales (misma pos) con solape o hueco <= 0.8."""
        runs = []
        for a, b, p in sorted(lista, key=lambda t: (t[2], t[0])):
            g = [r for r in runs if r["p"] == p
                 and a <= r["b"] + 0.8 and b >= r["a"] - 0.8]
            if g:
                r = g[0]
                r["a"], r["b"] = min(r["a"], a), max(r["b"], b)
            else:
                runs.append({"a": a, "b": b, "p": p})
        return runs

    def pares(lista, transversal):
        """Empareja dos tramos paralelos separados en 'transversal' por 0.2..0.9 m.
        Devuelve rectángulos (a,b,pos,ancho_t)."""
        rects = []
        usados = set()
        for i in range(len(lista)):
            for j in range(i + 1, len(lista)):
                a1, b1, p1 = lista[i]
                a2, b2, p2 = lista[j]
                if abs(p1 - p2) > 0.9:
                    continue
                span = min(b1, b2) - max(a1, a2)
                if span < 1.0:            # deben superponerse casi por completo
                    continue
                aa, bb = min(a1, a2), max(b1, b2)
                clave = (round(aa, 1), round(bb, 1), round(min(p1, p2), 1))
                if clave in usados:
                    continue
                usados.add(clave)
                rects.append({"a": aa, "b": bb,
                              "p": round((p1 + p2) / 2, 2),
                              "w": abs(p1 - p2)})
                break
        return rects

    def por_extremos(rects, dir_):
        vigas = []
        seen = set()
        for r in rects:
            clave = (r["a"], r["b"], r["p"])
            if clave in seen:
                continue
            seen.add(clave)
            if r["w"] < 0.25 or (r["b"] - r["a"]) < 1.2:
                continue   # basura: detalles/aristas sueltas
            if dir_ == "X":
                e1 = next((k for k, v in xs.items() if abs(v - r["a"]) <= 0.6), None)
                e2 = next((k for k, v in xs.items() if abs(v - r["b"]) <= 0.6), None)
                prim = e1 is not None and e2 is not None \
                    and any(abs(v - r["p"]) <= 0.35 for v in ys.values())
                vigas.append({
                    "tag": f"V-X-{r['p']:g}-{e1 or round(r['a'],1)}-{e2 or round(r['b'],1)}",
                    "directriz": "X", "tipo": "primaria" if prim else "secundaria",
                    "pos_m": r["p"],
                    "extremos_m": (round(r["a"], 3), round(r["b"], 3)),
                    "extremos": (e1, e2),
                    "centro_m": {"x": round((r["a"] + r["b"]) / 2, 3),
                                 "y": round(r["p"], 3)},
                    "largo_m": round(r["b"] - r["a"], 3),
                    "b_m": round(r["w"], 3),
                    "h_m": 0.8,
                })
            else:
                e1 = next((k for k, v in ys.items() if abs(v - r["a"]) <= 0.6), None)
                e2 = next((k for k, v in ys.items() if abs(v - r["b"]) <= 0.6), None)
                prim = e1 is not None and e2 is not None \
                    and any(abs(v - r["p"]) <= 0.35 for v in xs.values())
                vigas.append({
                    "tag": f"V-Y-{r['p']:g}-{e1 or round(r['a'],1)}-{e2 or round(r['b'],1)}",
                    "directriz": "Y", "tipo": "primaria" if prim else "secundaria",
                    "pos_m": r["p"],
                    "extremos_m": (round(r["a"], 3), round(r["b"], 3)),
                    "extremos": (e1, e2),
                    "centro_m": {"x": round(r["p"], 3),
                                 "y": round((r["a"] + r["b"]) / 2, 3)},
                    "largo_m": round(r["b"] - r["a"], 3),
                    "b_m": round(r["w"], 3),
                    "h_m": 0.8,
                })
        return vigas

    # fusionar tramos cortados por vigas transversales, luego emparejar caras
    h_merge = fusionar(hor)
    v_merge = fusionar(ver)
    vh = [(r["a"], r["b"], r["p"]) for r in h_merge]
    vv = [(r["a"], r["b"], r["p"]) for r in v_merge]
    vigas = []
    vigas += por_extremos(pares(vh, "X"), "X")
    vigas += por_extremos(pares(vv, "Y"), "Y")
    vigas.sort(key=lambda v: (v["directriz"], v["pos_m"], v["extremos_m"][0]))
    return vigas


def main():
    etapa = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    lamina = sys.argv[2] if len(sys.argv) > 2 else "-101"

    grilla = leer_grilla(etapa)
    x0, y0 = grilla["origen_cm"]["x"], grilla["origen_cm"]["y"]

    doc = dxfio.cargar(planos_dir() / f"{prefijo(etapa)}{lamina}.dxf")
    xmin = min(e["x_m"] for e in grilla["ejes_x_local_m"]) - 0.6
    xmax = max(e["x_m"] for e in grilla["ejes_x_local_m"]) + 0.6
    ymin = min(e["y_m"] for e in grilla["ejes_y_local_m"]) - 0.6
    ymax = max(e["y_m"] for e in grilla["ejes_y_local_m"]) + 0.6
    lineas = []
    for a, b, c, d in lineas_capa(doc, "RLE-VIGA"):
        la, lb = (a - x0) / 100.0, (b - y0) / 100.0
        lc, ld = (c - x0) / 100.0, (d - y0) / 100.0
        # conservar solo líneas COMPLETAS dentro de la región del plano principal:
        # evita arrastrar el subterráneo (-y) o los planos duplicados.
        if (min(la, lc) >= xmin and max(la, lc) <= xmax
                and min(lb, ld) >= ymin and max(lb, ld) <= ymax):
            lineas.append((la, lb, lc, ld))
    vigas = vigas_por_ejes(lineas, grilla)

    out_dir = OUT / f"etapa{etapa}"
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {"etapa": etapa, "lamina": lamina, "vigas": vigas}
    jp = out_dir / f"vigas_{lamina.strip('-')}.json"
    jp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(12, 9))
    for v in vigas:
        x, y = v["centro_m"]["x"], v["centro_m"]["y"]
        if v["directriz"] == "X":
            ax.plot([x - v["largo_m"] / 2, x + v["largo_m"] / 2],
                    [y, y], color="tab:blue", lw=2, solid_capstyle="butt")
        else:
            ax.plot([x, x], [y - v["largo_m"] / 2, y + v["largo_m"] / 2],
                    color="tab:blue", lw=2, solid_capstyle="butt")
        ax.text(x, y, v["tag"], fontsize=5, ha="center", va="center")
    for ex in grilla["ejes_x_local_m"]:
        ax.axvline(ex["x_m"], color="tab:red", lw=0.7, ls=":")
    for ey in grilla["ejes_y_local_m"]:
        ax.axhline(ey["y_m"], color="tab:blue", lw=0.7, ls=":")
    ax.set_aspect("equal")
    ax.set_title(f"Etapa {etapa} · {lamina} · vigas ({len(vigas)})")
    fig.tight_layout()
    png = out_dir / f"vigas_{lamina.strip('-')}.png"
    fig.savefig(png, dpi=110)
    plt.close(fig)

    print(f"{len(vigas)} vigas en {lamina}:")
    for v in vigas:
        print(f"  {v['tag']:<16} {v['tipo']:<10} {v['directriz']}"
              f"  L={v['largo_m']:>5.2f}  b={v['b_m']}")
    print(f"-> {jp}  (+ {png.name})")


if __name__ == "__main__":
    raise SystemExit(main())