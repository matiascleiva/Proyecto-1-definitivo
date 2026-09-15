"""Paso 2c — Muros (RLE-MURO) normalizados a la grilla local.

Cada muro se dibuja como dos caras paralelas (LINEas); los vanos se
reflejan como huecos en una o ambas caras. Se emparejan las caras
próximas (0.05..0.6 m) y se obtienen los paños máximos donde ambas
caras tienen cobertura; los huecos entre paños consecutivos sobre el
mismo eje son aberturas.

Salidas:
    out/etapaN/muros_<lamina>.json   (+ muros_<lamina>.png)

Uso:
    python scripts/step2c_muros.py [etapa] [lámina]
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


def segmentos_capa(doc, capa, x0, y0, xmin, xmax, ymin, ymax):
    """Segmentos LINE (+ LWPOLYLINE cerrada) contenidos por completo en la
    región del plano principal → (x1,y1,x2,y2) en m local."""
    segs = []
    for e in dxfio.entidades(doc, capa):
        if e.dxftype() == "LINE":
            s, p = e.dxf.start, e.dxf.end
            segs.append((float(s[0]), float(s[1]), float(p[0]), float(p[1])))
        elif e.dxftype() == "LWPOLYLINE" and e.is_closed:
            pts = [(float(a), float(b)) for a, b, *_ in e.get_points()]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
                segs.append((x1, y1, x2, y2))
    out = []
    for a, b, c, d in segs:
        la, lb = (a - x0) / 100.0, (b - y0) / 100.0
        lc, ld = (c - x0) / 100.0, (d - y0) / 100.0
        if (min(la, lc) >= xmin and max(la, lc) <= xmax
                and min(lb, ld) >= ymin and max(lb, ld) <= ymax):
            out.append((la, lb, lc, ld))
    return out


def intervalos(segs):
    """Runs por posición de cara: dict pos → lista ordenada de (a,b).
    Solo lineas con largo >= 0.5 (dirección = recorre la cara)."""
    ver = {}   # pos x -> [(y0,y1)]
    hor = {}   # pos y -> [(x0,x1)]
    for x1, y1, x2, y2 in segs:
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        if dx >= 0.5 and dy < 0.05:
            hor.setdefault(round((y1 + y2) / 2, 2), []).append(
                (min(x1, x2), max(x1, x2)))
        elif dy >= 0.5 and dx < 0.05:
            ver.setdefault(round((x1 + x2) / 2, 2), []).append(
                (min(y1, y2), max(y1, y2)))
    def fusionar(lista):
        runs = []
        for a, b in sorted(lista):
            g = [r for r in runs if a <= r[1] + 0.05 and b >= r[0] - 0.05]
            if g:
                r = g[0]
                runs[runs.index(r)] = (min(r[0], a), max(r[1], b))
            else:
                runs.append((a, b))
        return runs
    for p in list(ver):
        ver[p] = fusionar(ver[p])
    for p in list(hor):
        hor[p] = fusionar(hor[p])
    return ver, hor


def cobertura(A, B):
    """Paños donde las listas de intervalos A y B están ambas cubiertas."""
    ev = []
    for a, b in A:
        ev.append((a, 1)); ev.append((b, -1))
    for a, b in B:
        ev.append((a, 2)); ev.append((b, -2))
    ev.sort()
    c1 = c2 = 0
    seg = None
    out = []
    for x, d in ev:
        if d == 1:
            c1 += 1
        elif d == -1:
            c1 -= 1
        elif d == 2:
            c2 += 1
        else:
            c2 -= 1
        ambos = c1 > 0 and c2 > 0
        if seg is None and ambos:
            seg = x
        elif seg is not None and not ambos:
            out.append((seg, x))
            seg = None
    return out


def muros_por_ejes(segs, grilla):
    xs = {e["etiqueta"]: e["x_m"] for e in grilla["ejes_x_local_m"]}
    ys = {e["etiqueta"]: e["y_m"] for e in grilla["ejes_y_local_m"]}

    ver, hor = intervalos(segs)
    muros = []

    def ejes(pos, tabla):
        return next((k for k, v in tabla.items() if abs(v - pos) <= 0.35), None)

    def procesar(caras, directriz, tabla):
        usadas = set()
        for p1 in sorted(caras):
            if p1 in usadas:
                continue
            p2 = min((p for p in caras if p not in (p1, )),
                     key=lambda p: abs(p - p1),
                     default=None)
            if p2 is None or not (0.05 <= abs(p2 - p1) <= 0.6):
                continue
            usadas.add(p1)
            usadas.add(p2)
            paños = cobertura(caras[p1], caras[p2])
            if not paños:
                continue
            centro = abs(p1) < abs(p2) and (p1 + p2) / 2 or (p1 + p2) / 2
            espesor = abs(p2 - p1)
            if espesor > 0.6:
                continue
            paños = [p for p in paños if p[1] - p[0] >= 0.3]
            eje_tag = ejes(centro, tabla)
            # agrupar en muros: paño nuevo con hueco > 0.1 m
            mur = {"directriz": directriz, "pos_m": round(centro, 3),
                   "espesor_m": round(espesor, 3),
                   "paneles": [], "aberturas": []}
            for a, b in paños:
                if mur["paneles"] and a - mur["paneles"][-1][1] > 0.1:
                    ab = (mur["paneles"][-1][1], a)
                    if ab[1] - ab[0] > 0.2:
                        mur["aberturas"].append(
                            {"desde_m": round(ab[0], 3), "hasta_m": round(ab[1], 3),
                             "alto_m": round(ab[1] - ab[0], 3)})
                m = mur["paneles"]
                if m and a - m[-1][1] <= 0.1:
                    m[-1] = (m[-1][0], max(m[-1][1], b))
                else:
                    m.append((a, b))
            largo = mur["paneles"][-1][1] - mur["paneles"][0][0]
            if largo < 1.0:
                continue
            suf = "X" if directriz == "X" else "Y"
            if eje_tag:
                if directriz == "X":
                    tag = f"M-X-{eje_tag}"
                else:
                    tag = f"M-Y-{eje_tag}"
            else:
                tag = f"M-{suf}-{round(centro, 2):g}"
            ini, fin = mur["paneles"][0][0], mur["paneles"][-1][1]
            muros.append({
                "tag": tag,
                "directriz": directriz,
                "pos_m": round(centro, 3),
                "espesor_m": round(espesor, 3),
                "inicio_m": round(ini, 3),
                "fin_m": round(fin, 3),
                "largo_m": round(largo, 3),
                "eje": eje_tag,
                "extremos": (next((k for k, v in tabla.items()
                                   if abs(v - ini) <= 0.5), None),
                             next((k for k, v in tabla.items()
                                   if abs(v - fin) <= 0.5), None)),
                "aberturas": mur["aberturas"],
            })
    procesar(ver, "Y", xs)
    procesar(hor, "X", ys)
    muros.sort(key=lambda m: (m["directriz"], m["pos_m"], m["inicio_m"]))
    return muros


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
    segs = segmentos_capa(doc, "RLE-MURO", x0, y0, xmin, xmax, ymin, ymax)
    muros = muros_por_ejes(segs, grilla)

    out_dir = OUT / f"etapa{etapa}"
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {"etapa": etapa, "lamina": lamina, "muros": muros}
    jp = out_dir / f"muros_{lamina.strip('-')}.json"
    jp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(12, 9))
    for m in muros:
        if m["directriz"] == "Y":
            ax.plot([m["pos_m"], m["pos_m"]], [m["inicio_m"], m["fin_m"]],
                    color="tab:green", lw=m["espesor_m"] * 12,
                    solid_capstyle="butt")
            ax.text(m["pos_m"] + 0.3, (m["inicio_m"] + m["fin_m"]) / 2,
                    m["tag"], fontsize=6, va="center")
        else:
            ax.plot([m["inicio_m"], m["fin_m"]], [m["pos_m"], m["pos_m"]],
                    color="tab:green", lw=m["espesor_m"] * 12,
                    solid_capstyle="butt")
            ax.text((m["inicio_m"] + m["fin_m"]) / 2, m["pos_m"] + 0.3,
                    m["tag"], fontsize=6, ha="center")
    for ex in grilla["ejes_x_local_m"]:
        ax.axvline(ex["x_m"], color="tab:red", lw=0.7, ls=":")
    for ey in grilla["ejes_y_local_m"]:
        ax.axhline(ey["y_m"], color="tab:blue", lw=0.7, ls=":")
    ax.set_aspect("equal")
    ax.set_title(f"Etapa {etapa} · {lamina} · muros ({len(muros)})")
    fig.tight_layout()
    png = out_dir / f"muros_{lamina.strip('-')}.png"
    fig.savefig(png, dpi=110)
    plt.close(fig)

    print(f"{len(muros)} muros en {lamina}:")
    for m in muros:
        abert = f"  | {len(m['aberturas'])} abertura(s)" if m["aberturas"] else ""
        print(f"  {m['tag']:<14} {m['directriz']}  t={m['espesor_m']}"
              f"  L={m['largo_m']:>5.2f}  [{m['inicio_m']}..{m['fin_m']}]{abert}")
        for ab in m["aberturas"]:
            print(f"      abertura {ab['desde_m']}..{ab['hasta_m']} (h={ab['alto_m']})")
    print(f"-> {jp}  (+ {png.name})")


if __name__ == "__main__":
    raise SystemExit(main())