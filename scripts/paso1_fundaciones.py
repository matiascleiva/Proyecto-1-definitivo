# -*- coding: utf-8 -*-
"""Paso 1 — Planta Fundaciones (Etapa 1, 2017_67-100).

Detecta los ejes principales de columnas en la capa RLE-EJES por sus líneas
full-span, los confronta con la retícula declarada por el usuario
(Ese: X = ejes 1,2,3 · Y = ejes E,F,G,H,I,J) y genera:

    data/etapa1/fundaciones.json   # nodos basales Z=0 (fuente de datos)
    out/etapa1/paso1_fundaciones.png

Uso:
    python scripts/paso1_fundaciones.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ezdxf  # noqa: E402

from config.paths import OUT, planos_dir, prefijo  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

LAMINA = "-100"
NOMBRE = "Planta Fundaciones (Subterráneo 1)"
ESCALA_M = 0.01          # 1 unidad DXF = 1 cm

# Retícula declarada por el usuario (coordenadas esperadas en cm).
MAIN_VERT = {"E": 802.1, "F": 1802.1, "G": 2802.1,
             "H": 3802.1, "I": 4802.1, "J": 5302.1}   # ejes Y (constant X-sheet)
MAIN_HORZ = {"3": 4795.1, "2": 5520.1, "1": 6410.1}   # ejes X (constant Y-sheet)

# Columnas según usuario: Eje X {1,2,3} → intersecciones con ejes Y indicados.
COMBOS = {
    "3": ["E", "F", "G", "H", "I", "J"],
    "2": ["E", "F", "G", "H", "I", "J"],
    "1": ["E", "F", "G", "H", "I"],
}

TOL_SNAP = 25.0   # cm de tolerancia para "snap" de cada eje a una línea


def main() -> int:
    ruta = planos_dir() / f"{prefijo(1)}{LAMINA}.dxf"
    doc = ezdxf.readfile(str(ruta))
    msp = doc.modelspace()

    lin = [e for e in msp if e.dxftype() == "LINE" and e.dxf.layer == "RLE-EJES"]
    full = [e for e in lin
            if ((e.dxf.end.x - e.dxf.start.x) ** 2 +
                (e.dxf.end.y - e.dxf.start.y) ** 2) ** 0.5 >= 1000.0]

    def pos_vertical(e):
        return abs(e.dxf.start.x - e.dxf.end.x) < 1.0

    vert = {round((e.dxf.start.x + e.dxf.end.x) / 2, 1) for e in full if pos_vertical(e)}
    horz = {round((e.dxf.start.y + e.dxf.end.y) / 2, 1) for e in full if not pos_vertical(e)}

    def snap(esperados, observados):
        out, restr = {}, list(observados)
        for etiqueta in esperados:
            esp = esperados[etiqueta]
            cand = min(restr, key=lambda v: abs(v - esp))
            if abs(cand - esp) > TOL_SNAP:
                print(f"  [aviso] eje {etiqueta}: no se encontró línea en {esp} "
                      f"(más cercana {cand}) — se usa la esperada")
                out[etiqueta] = esp
            else:
                out[etiqueta] = cand
                restr.remove(cand)
        return out

    s_vert = snap(MAIN_VERT, vert)
    s_horz = snap(MAIN_HORZ, horz)

    # Coordenadas locales (m): X=0 en Eje 1 (crece 1→3), Y=0 en Eje E (crece E→J).
    y1_m = s_horz["1"] * ESCALA_M          # sheet-y del Eje 1 (origen local X)
    y0_m = s_vert["E"] * ESCALA_M          # sheet-x del Eje E (origen local Y)

    ord_ejes = ["1", "2", "3"]
    ejes_x = [{"etiqueta": k, "sheet_y_cm": s_horz[k],
               "x_m": round(abs(s_horz[k] * ESCALA_M - y1_m), 4)} for k in ord_ejes]
    ejes_y = [{"etiqueta": k, "sheet_x_cm": s_vert[k],
               "y_m": round(s_vert[k] * ESCALA_M - y0_m, 4)} for k in MAIN_VERT]

    columnas = []
    for ex in ord_ejes:
        x_m = abs(s_horz[ex] * ESCALA_M - y1_m)
        for ey in COMBOS[ex]:
            columnas.append({
                "tag": f"{ex}-{ey}",
                "eje_x": ex, "eje_y": ey,
                "x_m": round(x_m, 4),
                "y_m": round(s_vert[ey] * ESCALA_M - y0_m, 4),
                "z_m": 0.0,
                "sheet_cm": [s_vert[ey], s_horz[ex]],
            })

    secundarios_v = sorted(v for v in vert if all(abs(v - cv) > TOL_SNAP for cv in s_vert.values()))
    secundarios_h = sorted(y for y in horz if all(abs(y - cy) > TOL_SNAP for cy in s_horz.values()))

    data = {
        "formato": "fundaciones",
        "etapa": 1,
        "lamina": f"{prefijo(1)}{LAMINA}",
        "lamina_nombre": NOMBRE,
        "escala": {"u_dxf": "cm", "factor_m": ESCALA_M},
        "convencion": {
            "z_0": "Nivel Superior de Fundaciones (base columnas/muros, Subterráneo 1)",
            "origen_local": "Intersección Eje 1 × Eje E",
            "x0_m": y1_m, "y0_m": y0_m,
            "orientacion": {
                "X": "ejes 1,2,3 (crece 1→3)",
                "Y": "ejes E,F,G,H,I,J (crece E→J)",
                "Z": "vertical arriba",
                "nota": "convención del usuario: X = ejes 1,2,3 / Y = ejes E..J",
            },
        },
        "ejes_principales": {"X": ejes_x, "Y": ejes_y},
        "columnas_basales": columnas,
        "n_columnas": len(columnas),
        "extent_m": {"x": round(max(c["x_m"] for c in columnas), 4),
                     "y": round(max(c["y_m"] for c in columnas), 4)},
        "ejes_secundarios_cm": {
            "verticales": secundarios_v,   # vértices de muros/núcleos (rutina aparte)
            "horizontales": secundarios_h, # incluye eje 8 excluido de columnas
        },
        "fuente": {
            "plano": f"{prefijo(1)}{LAMINA}.dxf",
            "capa": "RLE-EJES",
            "metodo": "líneas full-span + snap a retícula declarada por el usuario",
            "script": "scripts/paso1_fundaciones.py",
        },
    }

    data_dir = Path(__file__).resolve().parents[1] / "data" / "etapa1"
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_dir / "fundaciones.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    _render(doc, columnas, ejes_x, ejes_y, data["extent_m"], OUT / "etapa1" / "paso1_fundaciones.png")

    print(f"Etapa 1 · {LAMINA} · {NOMBRE}")
    print("  ejes Y (E..J): " + ", ".join(f'{e["etiqueta"]}={s_vert[e["etiqueta"]]}cm'
                                           for e in ejes_y))
    print("  ejes X (1,2,3): " + ", ".join(f'{e["etiqueta"]}={s_horz[e["etiqueta"]]}cm'
                                            for e in ejes_x))
    print(f"  extend {data['extent_m']['x']} m x {data['extent_m']['y']} m "
          f"· {data['n_columnas']} columnas basales")
    print("  "+ " | ".join(c["tag"] for c in columnas))
    print(f"  -> {data_dir / 'fundaciones.json'}")
    return 0


def _render(doc, columnas, ejes_x, ejes_y, extent, out_png):
    from matplotlib.patches import Circle
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(13, 9))

    def dib(capa, color, lw=0.7, alpha=0.85):
        for e in doc.modelspace():
            if e.dxftype() != "LINE" or e.dxf.layer != capa:
                continue
            s, t = e.dxf.start, e.dxf.end
            ax.plot([s[0], t[0]], [s[1], t[1]], color=color, lw=lw, alpha=alpha)

    dib("RLE-EJES", "gray", lw=0.5, alpha=0.4)
    dib("RLE-FUNDACION", "tab:orange", lw=0.8)
    dib("RLE-PILAR", "tab:red", lw=1.0)
    dib("RLE-MURO", "tab:green", lw=0.8)

    for e in ejes_x:
        ax.axhline(e["sheet_y_cm"], color="purple", lw=1.1, ls="--")
        ax.text(5300, e["sheet_y_cm"] + 30, e["etiqueta"], fontsize=9,
                ha="center", color="purple")
    for e in ejes_y:
        ax.axvline(e["sheet_x_cm"], color="purple", lw=1.1, ls="--")
        ax.text(e["sheet_x_cm"], 8020, e["etiqueta"], fontsize=9,
                ha="center", va="bottom", color="purple")

    for c in columnas:
        x, y = c["sheet_cm"]
        ax.add_patch(Circle((x, y), 10, fill=True, color="red", zorder=5))
        ax.text(x, y + 14, c["tag"], fontsize=7, ha="center", color="red")

    ax.set_aspect("equal")
    ax.set_title(f"Etapa 1 · {LAMINA} · {NOMBRE} — grilla E..J x 1,2,3 · "
                 f"{len(columnas)} columnas basales Z=0")
    ax.grid(True, lw=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    print(f"  imagen de verificación -> {out_png}")


if __name__ == "__main__":
    raise SystemExit(main())