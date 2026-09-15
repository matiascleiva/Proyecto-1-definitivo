"""Paso 2e — Áreas tributarias y cargas por viga/columna.

Área tributaria de cada viga = ancho tributario (mitad de vano a las
vigas paralelas vecinas, acotado por los bordes de losa) × largo. La
partición de medio vano cubre exactamente el paño de losa en cada
dirección (la suma de anchos = ancho de la huella).

Cargas tipo (CM/SC) y pesos propios → A CONFIRMAR contra planos/memoria
de cálculo; se concentran en el dict CARGAS al inicio del archivo.

Salidas:
    out/etapaN/tributarias_<lamina>.json   (+ tributarias_<lamina>.png)

Uso:
    python scripts/step2e_tributarias.py [etapa] [lámina]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from config.paths import OUT  # noqa: E402

# ---------------------------------------------------------------------------
# Cargas tipo (kN/m²) — VALORES PRELIMINARES A CONFIRMAR
CARGAS = {
    "peso_losa": 3.6,      # losa hormigón e=0.15 m ≈ 24×0.15
    "terminaciones": 0.5,  # cielo/terminaciones
    "tabiqueria": 1.0,     # tabiquería móvil (uso departamento)
    "CM_losa": 5.1,        # subtotal CM por m² de losa
    "SC_uso": 2.0,         # NCh1537, uso departamento/habitación
    "g_concreto": 25.0,    # kN/m³
}
# ---------------------------------------------------------------------------


def leer_json(etapa, nombre):
    return json.loads((OUT / f"etapa{etapa}" / nombre)
                      .read_text(encoding="utf-8"))


def ancho_tributario(pos, vecinos, lo, hi):
    """Ancho de franja tributaria de un elemento paralelo en 'pos':
    mitad de vano a cada vecino, acotado por bordes [lo, hi]."""
    pre = max((v for v in vecinos if v < pos), default=None)
    sig = min((v for v in vecinos if v > pos), default=None)
    w = 0.0
    if pre is not None:
        w += (pos - pre) / 2.0
    else:
        w += pos - lo
    if sig is not None:
        w += (sig - pos) / 2.0
    else:
        w += hi - pos
    return w


def main():
    etapa = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    lamina = sys.argv[2] if len(sys.argv) > 2 else "-101"

    grilla = leer_json(etapa, "grilla_local.json")
    data_v = leer_json(etapa, f"vigas_{lamina.strip('-')}.json")
    data_l = leer_json(etapa, f"losas_{lamina.strip('-')}.json")
    data_p = leer_json(etapa, f"pilares_{lamina.strip('-')}.json")
    vigas = data_v["vigas"]
    huella = data_l["huella_m"]
    lo = huella["x0"]; hi = huella["x1"]
    bo = huella["y0"]; bt = huella["y1"]

    pos_x = sorted({v["pos_m"] for v in vigas if v["directriz"] == "X"})
    pos_y = sorted({v["pos_m"] for v in vigas if v["directriz"] == "Y"})

    cm_losa = CARGAS["CM_losa"]
    sc_uso = CARGAS["SC_uso"]
    g = CARGAS["g_concreto"]

    rows = []
    suma_area_x = suma_area_y = 0.0
    for v in vigas:
        if v["directriz"] == "X":
            ancho_t = ancho_tributario(v["pos_m"], pos_x, bo, bt)
            area = v["largo_m"] * ancho_t
            suma_area_x += area
            l_lo, l_hi = bo, bt
        else:
            ancho_t = ancho_tributario(v["pos_m"], pos_y, lo, hi)
            area = v["largo_m"] * ancho_t
            suma_area_y += area
            l_lo, l_hi = lo, hi
        q_trib = (cm_losa + sc_uso) * ancho_t
        pp = g * v["b_m"] * v["h_m"]
        v["ancho_tributario_m"] = round(ancho_t, 3)
        v["area_tributaria_m2"] = round(area, 2)
        v["q_msc_m2"] = round(q_trib, 2)      # kN/m por m² tributario
        v["q_msc_kNm"] = round(q_trib, 2)
        v["q_pp_kNm"] = round(pp, 2)
        v["q_total_kNm"] = round(q_trib + pp, 2)
        v["CM_kN"] = round(cm_losa * ancho_t * v["largo_m"], 1)
        v["SC_kN"] = round(sc_uso * ancho_t * v["largo_m"], 1)
        rows.append(v)

    # columnas: área de influencia por partición de medio vano (ambas dir.)
    ejes_x = sorted(e["x_m"] for e in grilla["ejes_x_local_m"])
    ejes_y = sorted(e["y_m"] for e in grilla["ejes_y_local_m"])
    cols = []
    for p in data_p["columnas"]:
        xi = p["centro_m"]["x"]
        yj = p["centro_m"]["y"]
        ax = ancho_tributario(xi, ejes_x, lo, hi)
        ay = ancho_tributario(yj, ejes_y, bo, bt)
        a = ax * ay
        p["area_influencia_m2"] = round(a, 2)
        p["q_axial_por_piso_kN"] = round((cm_losa + sc_uso) * a, 1)
        p["axial_1piso_CM_kN"] = round(cm_losa * a, 1)
        p["axial_1piso_SC_kN"] = round(sc_uso * a, 1)
        cols.append(p)

    out_dir = OUT / f"etapa{etapa}"
    data = {
        "etapa": etapa, "lamina": lamina,
        "cargas": CARGAS,
        "suma_area_X_m2": round(suma_area_x, 1),
        "suma_area_Y_m2": round(suma_area_y, 1),
        "area_losa_neta_m2": data_l["area_neta_m2"],
        "vigas": rows,
        "columnas": cols,
    }
    jp = out_dir / f"tributarias_{lamina.strip('-')}.json"
    jp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # PNG: vigas coloreadas por área tributaria
    fig, ax = plt.subplots(figsize=(12, 9))
    areas = [v["area_tributaria_m2"] for v in rows]
    vmax = max(areas) if areas else 1.0
    for v in rows:
        x, y = v["centro_m"]["x"], v["centro_m"]["y"]
        c = v["area_tributaria_m2"] / vmax
        if v["directriz"] == "X":
            ax.plot([x - v["largo_m"] / 2, x + v["largo_m"] / 2],
                    [y, y], color=plt.cm.viridis(c), lw=3)
            ax.text(x, y + 0.4, f"{v['area_tributaria_m2']:.0f}", fontsize=7,
                    ha="center")
        else:
            ax.plot([x, x], [y - v["largo_m"] / 2, y + v["largo_m"] / 2],
                    color=plt.cm.viridis(c), lw=3)
            ax.text(x + 0.4, y, f"{v['area_tributaria_m2']:.0f}", fontsize=7,
                    va="center")
    for ex in grilla["ejes_x_local_m"]:
        ax.axvline(ex["x_m"], color="tab:red", lw=0.6, ls=":")
    for ey in grilla["ejes_y_local_m"]:
        ax.axhline(ey["y_m"], color="tab:blue", lw=0.6, ls=":")
    ax.set_aspect("equal")
    ax.set_title(f"Etapa {etapa} · áreas tributarias (m² por piso)")
    fig.tight_layout()
    png = out_dir / f"tributarias_{lamina.strip('-')}.png"
    fig.savefig(png, dpi=110)
    plt.close(fig)

    print(f"TRIBUTARIAS Etapa {etapa} ({lamina})  ·  CM={cm_losa} SC={sc_uso} kN/m²")
    print(f"  Suma franjas X = {data['suma_area_X_m2']} m², Y = {data['suma_area_Y_m2']}"
          f"  (losa neta {data['area_losa_neta_m2']} m²)")
    print(f"  Vigas ({len(rows)}):")
    for v in rows:
        print(f"    {v['tag']:<16} A={v['area_tributaria_m2']:>7.1f} m²"
              f"  q_total={v['q_total_kNm']:>6.1f} kN/m")
    print(f"  Columnas ({len(cols)}): axial/piso = CM+SC por área de influencia")
    for p in cols:
        print(f"    {p['tag']:<6} A_infl={p['area_influencia_m2']:>6.1f} m²"
              f"  axial/piso={p['axial_1piso_CM_kN'] + p['axial_1piso_SC_kN']:>7.1f} kN")
    print(f"-> {jp}  (+ {png.name})")


if __name__ == "__main__":
    raise SystemExit(main())