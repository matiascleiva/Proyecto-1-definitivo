"""Paso 1b — Grilla local normalizada de la planta estructural de una etapa.

Detecta la grilla principal de columnas (rótulos E,F,G,H,I,I' × 1,2,3), define
un origen local en la intersección (E,3) y exporta la grilla en metros:

    out/etapa<k>/grilla_local.json
    out/etapa<k>/grilla_local_<lamina>.png

Cada lámina ubica su planta con un offset distinto en la hoja; el modelo se
construye SIEMPRE en coordenadas locales para que todas las láminas sean
consistentes.

Uso:
    python scripts/step1b_grilla_local.py [etapa] [lámina]
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from config.paths import OUT, planos_dir, prefijo  # noqa: E402
from src.extract import dxfio  # noqa: E402

EJES_X = ["E", "F", "G", "H", "I", "I'"]
EJES_Y = ["1", "2", "3"]

# Configuración por etapa: etiquetas de la grilla principal ordenadas por
# posición, luces (cm) y capas donde buscar los rótulos.
ETAPAS = {
    1: {
        "ejes_x": ["E", "F", "G", "H", "I", "I'"],
        "luces_x": [0, 1000, 2000, 3000, 4000, 4500],
        "ejes_y": ["3", "2", "1"],
        "luces_y": [0, 725, 1615],
        "capas_rotulos": ["RLE-EJE", "RLE-TEXTO-1"],
    },
    2: {
        "ejes_x": ["A", "B", "C", "D"],
        "luces_x": [0, 750, 1750, 2750],
        "ejes_y": ["3", "2", "1"],
        "luces_y": [0, 725, 1615],
        "capas_rotulos": ["RLE-EJE", "RLE-TEXTO-1"],
    },
}


def circulos_y_etiquetas(doc, capas_rotulos):
    """Círculos de rótulo de la capa RLE-EJE y sus etiquetas cercanas."""
    out = []
    for e in dxfio.entidades(doc, "RLE-EJE"):
        if e.dxftype() != "CIRCLE":
            continue
        c = e.dxf.center
        label, dmin = "", 1e18
        for capa in capas_rotulos:
            for t in dxfio.entidades(doc, capa):
                if t.dxftype() not in ("TEXT", "MTEXT"):
                    continue
                txt = dxfio.texto_entidad(t).strip()
                if not txt or len(txt) > 3:
                    continue
                ins = t.dxf.insert
                d = abs(ins[0] - c[0]) + abs(ins[1] - c[1])
                if d < dmin and d <= 90:
                    label, dmin = txt, d
        out.append((c[0], c[1], label))
    return out


def ejes_principales(cir, cfg):
    """Selecciona la grilla principal mediante coincidencia restringida:
    las posiciones de las etiquetas deben respetar las luces configuradas.
    Cada eje se ancla al rótulo base (primero de cada lista) y se busca el
    valor de ese rótulo que minimice el desvío del resto de la grilla; así se
    descartan planos duplicados y rótulos sueltos sin combinatoria."""
    cand = {}
    for x, y, lab in cir:
        cand.setdefault(lab, []).append((x, y))

    def elegir(etiquetas, plantilla, ancla, coord):
        """etiquetas ordenadas por posición; 'ancla' es la primera de ellas."""
        k = 0 if coord == "x" else 1
        cand_vals = {lab: sorted({v[k] for v in cand.get(lab, [])})
                     for lab in etiquetas}
        if any(not cv for cv in cand_vals.values()):
            return None
        mejor_vals, mejor_score, mejor_missing = None, 1e18, 1e9
        for a in cand_vals[ancla]:
            score, missing, vals = 0.0, 0, {}
            for i, lab in enumerate(etiquetas):
                tgt = a + plantilla[i]
                near = min(cand_vals[lab], key=lambda v: abs(v - tgt))
                dev = abs(near - tgt)
                score += dev
                missing += dev > 400
                vals[lab] = near
            if (missing, score) < (mejor_missing, mejor_score):
                mejor_missing, mejor_score = missing, score
                mejor_vals = vals
        return mejor_vals

    gx = elegir(cfg["ejes_x"], cfg["luces_x"], cfg["ejes_x"][0], "x")
    gy = elegir(cfg["ejes_y"], cfg["luces_y"], cfg["ejes_y"][0], "y")
    if gx is None or gy is None:
        return [], []
    gx = [{"etiqueta": lab, "val": gx[lab]} for lab in cfg["ejes_x"]]
    gy = [{"etiqueta": lab, "val": gy[lab]} for lab in cfg["ejes_y"]]
    gx.sort(key=lambda e: e["val"])
    gy.sort(key=lambda e: e["val"])
    return gx, gy


def main():
    etapa = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    lamina = sys.argv[2] if len(sys.argv) > 2 else "-101"
    cfg = ETAPAS.get(etapa, ETAPAS[1])
    EJES_X = cfg["ejes_x"]
    EJES_Y = cfg["ejes_y"]

    doc = dxfio.cargar(planos_dir() / f"{prefijo(etapa)}{lamina}.dxf")
    cir = circulos_y_etiquetas(doc, cfg["capas_rotulos"])
    gx, gy = ejes_principales(cir, cfg)

    if not gx or not gy:
        print("No se pudo identificar la grilla principal (ejes",
              EJES_X, "×", EJES_Y, ") en", lamina)
        return 1

    lab_x0 = cfg["ejes_x"][0]   # origen local: primer eje X (x = 0)
    lab_y0 = cfg["ejes_y"][0]   # origen local: primer eje Y (y = 0)
    x0 = next(e["val"] for e in gx if e["etiqueta"] == lab_x0)
    y0 = next(e["val"] for e in gy if e["etiqueta"] == lab_y0)

    out_dir = OUT / f"etapa{etapa}"
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "etapa": etapa,
        "lamina": lamina,
        "origen_cm": {"x": round(x0, 2), "y": round(y0, 2),
                      "ejes_x": lab_x0, "ejes_y": lab_y0},
        "ejes_x_local_m": [
            {"etiqueta": e["etiqueta"], "x_m": round((e["val"] - x0) / 100.0, 3)}
            for e in gx
        ],
        "ejes_y_local_m": [
            {"etiqueta": e["etiqueta"], "y_m": round((e["val"] - y0) / 100.0, 3)}
            for e in gy
        ],
    }
    with open(out_dir / "grilla_local.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # verificación visual (todos los rótulos en coordenadas locales)
    fig, ax = plt.subplots(figsize=(12, 8))
    for x, y, lab in cir:
        ax.scatter((x - x0) / 100, (y - y0) / 100, s=8, color="gray", zorder=1)
        if lab:
            ax.annotate(lab, ((x - x0) / 100, (y - y0) / 100), fontsize=6,
                        color="black", alpha=0.7, ha="center", va="center")
    for e in data["ejes_x_local_m"]:
        ax.axvline(e["x_m"], color="tab:red", lw=1.0, ls="--")
        ax.text(e["x_m"], -1, e["etiqueta"], fontsize=9, ha="center", color="tab:red")
    for e in data["ejes_y_local_m"]:
        ax.axhline(e["y_m"], color="tab:blue", lw=1.0, ls="--")
        ax.text(-1.5, e["y_m"], e["etiqueta"], fontsize=9, va="center", color="tab:blue")
    ax.set_aspect("equal")
    ax.set_title(f"Etapa {etapa} · {lamina} · grilla local (origen = {lab_x0} ∩ {lab_y0})")
    fig.tight_layout()
    png = out_dir / f"grilla_local_{lamina.strip('-')}.png"
    fig.savefig(png, dpi=110)
    plt.close(fig)

    print(f"Origen local: eje {lab_x0}={x0/100:.3f} m, eje {lab_y0}={y0/100:.3f} m")
    print("ejes X:", ", ".join(f'{e["etiqueta"]}={e["x_m"]}m' for e in data["ejes_x_local_m"]))
    print("ejes Y:", ", ".join(f'{e["etiqueta"]}={e["y_m"]}m' for e in data["ejes_y_local_m"]))
    print(f"-> {out_dir / 'grilla_local.json'}  (+ {png.name})")


if __name__ == "__main__":
    raise SystemExit(main())