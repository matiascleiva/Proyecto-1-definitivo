"""Exporta el modelo estructural 3D + esfuerzos a JSON amigable para Unity.

Replica el formato que consume `BuildingViewer.cs` del visor Unity
(VisorUnity): losas como malla plana y columnas/muros/vigas como PRISMAS
SÓLIDOS con las dimensiones reales de sección y su orientación en planta.

  edificio_unity.json     geometría: losas + sólidos (vertices/triangulos/tag)
  esfuerzos_unity.json    fuerzas por elementTag (P, Vy, Vz, T, My, Mz) desde
                          la envolvente sísmica (los casos X±/Y± ya incluyen
                          la carga gravitatoria)

Uso:
    python scripts/exportar_unity.py [etapa ...]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.paths import OUT  # noqa: E402
from step3_modelo import H_PISO, N_NIVELES, SECCOL, SECVIG, z_nivel  # noqa: E402

COL_B = SECCOL["A"] ** 0.5          # 0.70 m (columna cuadrada)
VIG_ALTO, VIG_ANCHO = 0.60, 0.80    # VIGA_60x80: alto en Z, ancho en planta
MUR_E = 0.20                        # espesor muros


def leer(etapa, nombre):
    return json.loads((OUT / f"etapa{etapa}" / nombre).read_text(encoding="utf-8"))


def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def scale(v, s):
    return [v[0] * s, v[1] * s, v[2] * s]


def half(v):
    return scale(v, 0.5)


def construir_prisma(a, b, v, w):
    """Prisma rectangular con eje a→b y sección transversal v×w (magnitudes
    reales). Devuelve 8 vértices y 12 triángulos."""
    av, bw = half(v), half(w)

    def punto(base, s0, s1):
        return [base[0] + s0 * av[0] + s1 * bw[0],
                base[1] + s0 * av[1] + s1 * bw[1],
                base[2] + s0 * av[2] + s1 * bw[2]]

    p = [punto(a, -1, -1), punto(a, +1, -1), punto(a, +1, +1), punto(a, -1, +1),
         punto(b, -1, -1), punto(b, +1, -1), punto(b, +1, +1), punto(b, -1, +1)]
    tri = [0, 3, 2, 0, 2, 1, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
           3, 7, 6, 3, 6, 2, 0, 4, 7, 0, 7, 3, 1, 2, 6, 1, 6, 5]
    return p, tri


def columnas_solidos(etapa, ejes_x, ejes_y):
    cols = leer(etapa, "pilares_101.json")["columnas"]
    solidos, ref = [], []
    for i, c in enumerate(cols, start=1):
        x, y = c["centro_m"]["x"], c["centro_m"]["y"]
        v, w = [COL_B, 0.0, 0.0], [0.0, COL_B, 0.0]
        prev = [x, y, 0.0]
        for k in range(1, N_NIVELES + 1):
            z = z_nivel(k)
            p = [x, y, z]
            tag = 10000 + k * 1000 + i
            verts, tris = construir_prisma(prev, p, v, w)
            solidos.append({"id": i, "tipo": "columna", "seccion": "COL", "nivel": k,
                            "tag": tag, "descripcion": "Columna " + c["tag"],
                            "vertices": verts, "triangulos": tris})
            ref.append((c["tag"], 10000 + k * 1000 + i, k))
            prev = p
    return solidos, ref


def muros_solidos(etapa):
    muros = [m for m in leer(etapa, "muros_101.json")["muros"]
             if m["largo_m"] >= 1.5]
    solidos, ref = [], []
    for j, m in enumerate(muros, start=100):
        L = m["largo_m"]
        if m["directriz"] == "X":
            xc, yc = (m["inicio_m"] + m["fin_m"]) / 2, m["pos_m"]
            v, w, plano = [L, 0.0, 0.0], [0.0, MUR_E, 0.0], "X"
        else:
            xc, yc = m["pos_m"], (m["inicio_m"] + m["fin_m"]) / 2
            v, w, plano = [0.0, L, 0.0], [MUR_E, 0.0, 0.0], "Y"
        prev = [xc, yc, 0.0]
        for k in range(1, N_NIVELES + 1):
            z = z_nivel(k)
            p = [xc, yc, z]
            tag = 12000 + k * 1000 + j
            verts, tris = construir_prisma(prev, p, v, w)
            solidos.append({"id": 3000 + j, "tipo": "muro", "plano": plano,
                            "seccion": "MUR", "nivel": k, "tag": tag,
                            "descripcion": m["tag"],
                            "vertices": verts, "triangulos": tris})
            ref.append(("MUR-" + str(j), tag, k))
            prev = p
    return solidos, ref


def vigas_solidos(etapa, ejes_x, ejes_y):
    cols = leer(etapa, "pilares_101.json")["columnas"]
    pos = [(c["centro_m"]["x"], c["centro_m"]["y"], c["tag"]) for c in cols]

    def en_eje(p, vcal, tol=0.05):
        return [c for c in pos if abs(c[vcal] - p) < tol]

    parejas = []            # (dir, x1, y1, x2, y2)
    for ex, xv in ejes_x.items():
        fila = sorted(en_eje(xv, 0), key=lambda c: c[1])
        for (x1, y1, _), (x2, y2, _) in zip(fila, fila[1:]):
            parejas.append(("X", x1, y1, x2, y2))
    for ey, yv in ejes_y.items():
        col = sorted(en_eje(yv, 1), key=lambda c: c[0])
        for (x1, y1, _), (x2, y2, _) in zip(col, col[1:]):
            parejas.append(("Y", x1, y1, x2, y2))

    solidos, ref = [], []
    for idx, (d, x1, y1, x2, y2) in enumerate(parejas):
        for k in range(1, N_NIVELES + 1):
            z0, z1 = 0.0, z_nivel(k)
            a = [x1, y1, z0]
            b = [x2, y2, z1]
            v = [0.0, VIG_ANCHO, 0.0] if d == "X" else [VIG_ANCHO, 0.0, 0.0]
            w = [0.0, 0.0, VIG_ALTO]
            tag = (20000 if d == "X" else 30000) + k * 100 + idx
            verts, tris = construir_prisma(a, b, v, w)
            long = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            solidos.append({"id": idx, "tipo": "viga", "dir": d,
                            "longitud_m": round(long, 3), "seccion": "VIG",
                            "nivel": k, "tag": tag,
                            "descripcion": "Viga %s" % d,
                            "vertices": verts, "triangulos": tris})
            ref.append(("B-" + str(tag), tag, k))
    return solidos, ref


def losas_niveles(etapa):
    lo = leer(etapa, "losas_101.json")
    h = lo["huella_m"]
    esquinas = ([h["x0"], h["y0"]], [h["x1"], h["y0"]],
                [h["x1"], h["y1"]], [h["x0"], h["y1"]])
    losas = []
    for k in range(1, N_NIVELES + 1):
        z = z_nivel(k)
        losas.append({"nivel": k, "nombre": f"Losa N{k}",
                      "z_m": z, "vertices": [es + [z] for es in esquinas],
                      "triangulos": [0, 1, 2, 0, 2, 3]})
    return losas


def esfuerzos(etapa, refs):
    env = leer(etapa, "sismo_envolvente.json")
    out = []
    for fuentekey, tag, k in refs:
        f = env.get(fuentekey, {}).get(str(k), {})
        out.append({
            "elementTag": tag,
            "type": ("viga" if fuentekey.startswith("B-") else
                     "muro" if fuentekey.startswith("MUR-") else "columna"),
            "P_kN": round(f.get("P", 0.0), 3),
            "Vy_kN": round(f.get("Vy", 0.0), 3),
            "Vz_kN": round(f.get("Vz", 0.0), 3),
            "T_kNm": round(f.get("T", 0.0), 3),
            "My_kNm": round(f.get("My", 0.0), 3),
            "Mz_kNm": round(f.get("Mz", 0.0), 3),
        })
    return out


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    etapas = [int(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else [1, 2]
    for etapa in etapas:
        grilla = leer(etapa, "grilla_local.json")
        ejes_x = {e["etiqueta"]: round(e["x_m"], 3)
                  for e in grilla["ejes_x_local_m"]}
        ejes_y = {e["etiqueta"]: round(e["y_m"], 3)
                  for e in grilla["ejes_y_local_m"]}

        cols, ref_col = columnas_solidos(etapa, ejes_x, ejes_y)
        murs, ref_mur = muros_solidos(etapa)
        vigs, ref_vig = vigas_solidos(etapa, ejes_x, ejes_y)
        losas = losas_niveles(etapa)

        out = {
            "_meta": {
                "destino": "Unity", "etapa": etapa,
                "unidades": "metros (m), kN y kN·m",
                "coordenadas": {"nx": "E->(+) X", "ny": "3->1 (+) Y",
                                "nz": "vertical (+Z)"},
                "n_niveles": N_NIVELES, "h_piso_m": H_PISO,
                "origen_z_base": 0.0,
                "nota": "Losas = malla plana por nivel; columnas/muros/vigas = "
                        "prismas sólidos con sección real.",
            },
            "losas": losas, "columnas": cols, "muros": murs, "vigas": vigs,
            "niveles": [z_nivel(k) for k in range(1, N_NIVELES + 1)],
        }
        refs = ref_col + ref_mur + ref_vig
        esf = {"elementos": esfuerzos(etapa, refs)}

        geo_p = OUT / f"etapa{etapa}" / "edificio_unity.json"
        esf_p = OUT / f"etapa{etapa}" / "esfuerzos_unity.json"
        geo_p.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        esf_p.write_text(json.dumps(esf, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        print(f"UNITY Etapa {etapa} → {geo_p}")
        print(f"  Losas={len(losas)} Col={len(cols)} Muros={len(murs)} "
              f"Vigas={len(vigs)} | esfuerzos={len(esf['elementos'])}")


if __name__ == "__main__":
    main()