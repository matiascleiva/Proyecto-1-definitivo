"""Paso 3 — Modelo estructural 3D en OpenSeesPy (ndm=3, ndf=6) por ETAPA.

Ensambla, con la geometría extraída en el Paso 2 (grilla, columnas, vigas,
muros, tributarias), un modelo elástico lineal por nivel:

  - Niveles: 5 losas (1° Subterráneo + 1º..4º Piso), h=3.96 m, Z=k·h.
  - Columnas  70×70 cm  (elasticBeamColumn, tramo por nivel).
  - Vigas     60×80 cm  (elasticBeamColumn, entre columnas en grilla).
  - Muros     e=0.20 m  (elasticBeamColumn vertical en el centro del paño).
  - Diafragma rígido por nivel (nodo maestro en el centro de masa).
  - Carga gravitatoria qG por área de influencia de columna + pesos propios.

Parámetros de material/sección y cargas → secciones_verticales.json /
cargas_piso.json del modelo de referencia (G35, E=27.8 GPa, γ=24 kN/m³).

Salidas (out/etapaN/):
    modelo_ops.py            script OpenSeesPy generado (listo para ejecutar)
    modelo_geometria.json    nodos/elementos por nivel (visores/Unity)
    modelo_reacciones.json   reacciones en la base (ΣRz = 0 débil...)
    modelo_columnas.json     axial por columna y nivel (validación)

Uso:
    python scripts/step3_modelo.py [etapa]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.paths import OUT  # noqa: E402

H_PISO = 3.96
N_NIVELES = 5
SECCOL = dict(A=0.49, Iy=0.020008, Iz=0.020008, J=0.033758)   # 70×70
SECVIG = dict(A=0.48, Iy=0.025600, Iz=0.014400, J=0.056779)   # 60×80
E = 27_805_600.0          # kPa = kN/m² (G35)
G = 11_585_700.0
GAMMA = 24.0
SPP_COL = SECCOL["A"] * GAMMA * H_PISO          # 46.6 kN/columna/nivel
# Cargas de piso del modelo de referencia (1° Subterráneo, planta cielos):
QGP = {"pp_losa": 3.675, "pm": 2.55, "sc": 3.92}   # kN/m²
Q_SUB = QGP["pp_losa"] + QGP["pm"] + QGP["sc"]     # ≈ 10.145 kN/m²


def z_nivel(k):
    return k * H_PISO


def leer(etapa, nombre):
    return json.loads((OUT / f"etapa{etapa}" / nombre).read_text(encoding="utf-8"))


def tag_losa(k, base):
    return 1000 + (k - 1) * 100 + base


def tag_master(k):
    return 9500 + k


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    etapa = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    grilla = leer(etapa, "grilla_local.json")
    cols = leer(etapa, f"pilares_101.json")["columnas"]
    vigas = [v for v in leer(etapa, "vigas_101.json")["vigas"]
             if v["tipo"] == "primaria"]
    muros = [m for m in leer(etapa, "muros_101.json")["muros"]
             if m["largo_m"] >= 1.5]
    tribut = leer(etapa, "tributarias_101.json")

    ejes_x = {e["etiqueta"]: round(e["x_m"], 3) for e in grilla["ejes_x_local_m"]}
    ejes_y = {e["etiqueta"]: round(e["y_m"], 3) for e in grilla["ejes_y_local_m"]}

    apoyos = []
    for c in cols:
        apoyos.append({
            "tag": c["tag"], "x": c["centro_m"]["x"], "y": c["centro_m"]["y"],
            "a_infl": next((p["area_influencia_m2"] for p in tribut["columnas"]
                            if p["tag"] == c["tag"]), 0.0),
        })
    # centro de masa (promedio de columnas)
    cm = (sum(a["x"] for a in apoyos) / len(apoyos),
          sum(a["y"] for a in apoyos) / len(apoyos))

    # --- generación del script OpenSeesPy ---
    L = ["from openseespy.opensees import *",
         'wipe()', 'model("basic", "-ndm", 3, "-ndf", 6)',
         f"# {len(apoyos)} columnas, {len(vigas)} vigas primarias, "
         f"{len(muros)} muros, {N_NIVELES} niveles",
         f"uniaxialMaterial('Elastic', 1, {E:g})",
         f"section('Elastic', 100, {E:g}, {SECCOL['A']:g}, {SECCOL['Iz']:g}, "
         f"{SECCOL['Iy']:g}, {G:g}, {SECCOL['J']:g})",
         f"section('Elastic', 300, {E:g}, {SECVIG['A']:g}, {SECVIG['Iz']:g}, "
         f"{SECVIG['Iy']:g}, {G:g}, {SECVIG['J']:g})",
         "geomTransf('Linear', 1, 1.0, 0.0, 0.0)",
         "geomTransf('Linear', 2, 0.0, 0.0, 1.0)",
         ]
    nbase = {}

    # nodos base + losas por nivel + columnas
    for i, a in enumerate(apoyos, start=1):
        nbase[a["tag"]] = i
        L.append(f"node({i}, {a['x']:g}, {a['y']:g}, 0.0)")
        L.append(f"fix({i}, 1,1,1,1,1,1)")
    for k in range(1, N_NIVELES + 1):
        zn = z_nivel(k)
        L.append(f"node({tag_master(k)}, {cm[0]:g}, {cm[1]:g}, {zn:g})")
        L.append(f"fix({tag_master(k)}, 0,0,1,1,1,0)")
        for a in apoyos:
            L.append(f"node({tag_losa(k, nbase[a['tag']])}, {a['x']:g}, "
                     f"{a['y']:g}, {zn:g})")
    for a in apoyos:
        b = nbase[a["tag"]]
        for k in range(1, N_NIVELES + 1):
            ini = b if k == 1 else tag_losa(k - 1, b)
            fin = tag_losa(k, b)
            etag = 10000 + k * 1000 + b
            L.append(f"element('elasticBeamColumn', {etag}, {ini}, {fin}, "
                     f"100, 1)")

    # vigas: conectar columnas consecutivas en los ejes presentes
    idx = 0
    nodo_x = {ex: {} for ex in ejes_x}
    for a in apoyos:
        for ex, xv in ejes_x.items():
            if abs(a["x"] - xv) < 0.05:
                nodo_x[ex][a["y"]] = nbase[a["tag"]]
    nodo_y = {ey: {} for ey in ejes_y}
    for a in apoyos:
        for ey, yv in ejes_y.items():
            if abs(a["y"] - yv) < 0.05:
                nodo_y[ey][a["x"]] = nbase[a["tag"]]

    vigas_ids = []
    for ex in ejes_x:
        ys = sorted(nodo_x[ex])
        for y1, y2 in zip(ys, ys[1:]):
            i1, i2 = nodo_x[ex][y1], nodo_x[ex][y2]
            for k in range(1, N_NIVELES + 1):
                etag = 20000 + k * 100 + idx
                L.append(f"element('elasticBeamColumn', {etag}, "
                         f"{tag_losa(k, i1)}, {tag_losa(k, i2)}, 300, 2)")
                vigas_ids.append(etag)
            idx += 1
    for ey in ejes_y:
        xs = sorted(nodo_y[ey])
        for x1, x2 in zip(xs, xs[1:]):
            i1, i2 = nodo_y[ey][x1], nodo_y[ey][x2]
            for k in range(1, N_NIVELES + 1):
                etag = 30000 + k * 100 + idx
                L.append(f"element('elasticBeamColumn', {etag}, "
                         f"{tag_losa(k, i1)}, {tag_losa(k, i2)}, 300, 2)")
                vigas_ids.append(etag)
            idx += 1

    # muros: paño vertical en su eje de grilla → nodo en el centro del paño
    muro_ids = []
    slaves_por_nivel = {k: [] for k in range(1, N_NIVELES + 1)}
    for j, m in enumerate(muros, start=100):
        xc, yc = 0.0, 0.0
        if m["directriz"] == "Y":
            xc, yc = m["pos_m"], (m["inicio_m"] + m["fin_m"]) / 2
        else:
            xc, yc = (m["inicio_m"] + m["fin_m"]) / 2, m["pos_m"]
        b = 3000 + j
        L.append(f"node({b}, {xc:g}, {yc:g}, 0.0)")
        L.append(f"fix({b}, 1,1,1,1,1,1)")
        for k in range(1, N_NIVELES + 1):
            L.append(f"node({tag_losa(k, b)}, {xc:g}, {yc:g}, {z_nivel(k):g})")
            slaves_por_nivel[k].append(tag_losa(k, b))
        Lm = m["largo_m"]
        sec_id = 500 + j
        A = 0.2 * Lm
        Iy = 0.2 * Lm ** 3 / 12.0
        Iz = Lm * 0.2 ** 3 / 12.0
        J = 0.2 * Lm * (0.2 ** 2 + Lm ** 2) / 12.0
        L.append(f"section('Elastic', {sec_id}, {E:g}, {A:g}, {Iz:g}, "
                 f"{Iy:g}, {G:g}, {J:g})")
        for k in range(1, N_NIVELES + 1):
            ini = b if k == 1 else tag_losa(k - 1, b)
            fin = tag_losa(k, b)
            etag = 12000 + k * 1000 + j
            L.append(f"element('elasticBeamColumn', {etag}, {ini}, {fin}, "
                     f"{sec_id}, 1)")
            muro_ids.append(etag)

    # diafragma rígido por nivel (columnas + muros)
    for k in range(1, N_NIVELES + 1):
        slaves = [tag_losa(k, nbase[a["tag"]]) for a in apoyos]
        slaves += slaves_por_nivel[k]
        L.append(f"rigidDiaphragm(3, {tag_master(k)}, "
                 f"{', '.join(str(s) for s in slaves)})")

    # carga: qG×A_influ + peso propio columna, aplicada en cada nivel
    L.append("timeSeries('Linear', 100)")
    L.append("pattern('Plain', 100, 100)")
    for a in apoyos:
        F = Q_SUB * a["a_infl"] + SPP_COL
        for k in range(1, N_NIVELES + 1):
            L.append(f"load({tag_losa(k, nbase[a['tag']])}, 0.0, 0.0, {-F:g}, "
                     f"0.0, 0.0, 0.0)")

    L += ["system('BandSPD')", "numberer('RCM')", "constraints('Transformation')",
          "algorithm('Newton')", "integrator('LoadControl', 1.0)",
          "analysis('Static')", "ok = analyze(1)",
          "print('analisis:', ok)"]

    # extracción de axial por columna/nivel + reacciones
    L.append("import json")
    L.append("res = {}")
    L.append("for k in range(1, 6):")
    L.append("    rows = []")
    for i, a in enumerate(apoyos, start=1):
        L.append(f"    rows.append((\"{a['tag']}\", "
                 f"eleResponse(10000 + k * 1000 + {i}, 'localForces')[0]))")
    L.append("    res[k] = dict(rows)")
    L.append("with open(" +
             repr(str(OUT / f"etapa{etapa}" / "modelo_columnas.json")) +
             ", 'w', encoding='utf-8') as f:")
    L.append("    json.dump(res, f, ensure_ascii=False, indent=2)")
    L.append("reactions()")
    L.append("print('SigmaRz =', sum(nodeReaction(i, 3) "
             f"for i in range(1, {len(apoyos) + 1})))")

    out_dir = OUT / f"etapa{etapa}"
    out_dir.mkdir(parents=True, exist_ok=True)
    script = out_dir / "modelo_ops.py"
    script.write_text("\n".join(L), encoding="utf-8")

    geom = {
        "etapa": etapa, "n_niveles": N_NIVELES, "h_piso_m": H_PISO,
        "z_niveles_m": {k: z_nivel(k) for k in range(1, N_NIVELES + 1)},
        "centro_masa_m": cm,
        "n_columnas": len(apoyos), "n_vigas": len(vigas_ids),
        "n_muros": len(muros), "qG_kN_m2": Q_SUB,
    }
    (out_dir / "modelo_geometria.json").write_text(
        json.dumps({"config": geom,
                    "columnas": apoyos,
                    "vigas": [{"dir": "X" if e < 30000 else "Y",
                               "etag": e} for e in vigas_ids],
                    "muros": muros}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    print(f"MODELO Etapa {etapa} → {script}")
    print(f"  {len(apoyos)} columnas · {len(vigas_ids)} vigas · "
          f"{len(muros)} muros · {N_NIVELES} niveles (h={H_PISO}m)")
    print(f"  Cargas: qG={Q_SUB:.2f} kN/m²  (referencia 1° Subterráneo) + "
          f"PP columna {SPP_COL:.1f} kN/nivel")


if __name__ == "__main__":
    raise SystemExit(main())