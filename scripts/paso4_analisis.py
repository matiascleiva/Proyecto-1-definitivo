"""Paso 4 - Analisis estructural de una seccion del edificio (resultados en consola).

Que hace:
  1) Reconstruye la seccion (piso) del edificio desde los JSON.
  2) Analisis de GRAVEDAD: esfuerzos internos (columnas y vigas),
     reacciones en base y desplazamientos.
  3) Analisis MODAL: periodos y frecuencias (con masa lumped por piso).

Siempre imprime un encabezado que identifica QUE seccion del edificio
se esta analizando.

Uso:
    python scripts/paso4_analisis.py [--nivel S1]
"""
import json
import math
import sys
from pathlib import Path

import openseespy.opensees as ops

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA = Path(__file__).resolve().parents[1] / "data" / "etapa1"

Q_LOSA_KPA = 7.5    # kN/m^2 (losa 15cm + acabados, 1a estimacion)
GRAV = 9.81          # m/s^2

# Informacion que identifica lo que se analiza (se amplia por piso)
SECCIONES = {
    "S1": {
        "nombre": "1 SUBTERRANEO (S1)",
        "planos": "2017_67-100 (fundaciones) + 2017_67-101 (planta cielo S1)",
        "z0_m": 0.0,
        "z1_m": 3.96,
        "tipos": "17 columnas P70x70 + 25 vigas V60x80",
    },
}

SEC_Z = 3.96  # cota de losa del nivel analizado (m)


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def construir_modelo():
    """Nodos, fijos, geomTransf, columnas, vigas y masas lumped en losa."""
    nodos = load("nodos.json")
    cols = load("elementos_verticales_Z1.json")
    vgs = load("vigas_1S.json")
    secs = load("secciones.json")
    mat = secs["material"]

    ops.wipe()
    ops.model("basic", "-ndm", 3)

    for n in nodos:
        ops.node(n["tag"], n["x_m"], n["y_m"], n["z_m"])
        if n["z_m"] == 0.0:
            ops.fix(n["tag"], 1, 1, 1, 1, 1, 1)

    ops.geomTransf("Linear", 1, 1.0, 0.0, 0.0)   # columnas (verticales)
    ops.geomTransf("Linear", 2, 1.0, 0.0, 0.0)   # vigas paralelas a Y
    ops.geomTransf("Linear", 3, 0.0, 1.0, 0.0)   # vigas paralelas a X

    E = mat["E_kpa"]; Go = mat["G_kpa"]
    pc = secs["secciones"]["P70_70"]
    pv = secs["secciones"]["V60x80"]

    for c in cols:
        ops.element("elasticBeamColumn", c["elementTag"], c["iNode"], c["jNode"],
                    pc["A_m2"], E, Go, pc["J_m4"], pc["Iy_m4"], pc["Iz_m4"], 1)
    for v in vgs["vigas"]:
        gt = 2 if v["directriz"] == "Y" else 3
        ops.element("elasticBeamColumn", v["elementTag"], v["iNode"], v["jNode"],
                    pv["A_m2"], E, Go, pv["J_m4"], pv["Iy_m4"], pv["Iz_m4"], gt)

    esclavos = [n for n in nodos if n["z_m"] > 0]
    area = max(n["x_m"] for n in nodos) * max(n["y_m"] for n in nodos)
    w_total = area * Q_LOSA_KPA
    m_nodo = (w_total / GRAV) / len(esclavos)

    for n in esclavos:
        ops.mass(n["tag"], m_nodo, m_nodo, m_nodo, 0, 0, 0)

    return nodos, cols, vgs["vigas"], secs, w_total, m_nodo


def encabezado(nivel):
    info = SECCIONES[nivel]
    print("=" * 72)
    print(f" ANALISIS ESTRUCTURAL - SECCION ANALIZADA: {info['nombre']}")
    print("=" * 72)
    print(f"  planos       : {info['planos']}")
    print(f"  rango en Z   : {info['z0_m']:.2f} m (fundacion) -> {info['z1_m']:.2f} m (losa)")
    print(f"  elementos    : {info['tipos']}")
    print(f"  carga        : losas {Q_LOSA_KPA:.0f} kPa repartida en {info['z1_m']:.2f} m")
    print(f"  modelo       : OpenSeesPy, elasticBeamColumn 3D (secc. brutas sin armadura)")
    print("=" * 72)


def leer_recorder(path, ncols):
    """Ultima fila COMPLETA (con ncols valores) de un recorder por paso."""
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    for ln in reversed(lines):
        v = [float(x) for x in ln.split()]
        if len(v) == ncols:
            return v
    return [0.0] * ncols


def analisis_gravedad(nodos, cols, vigas, w_total, tmpdir):
    ops.wipeAnalysis()
    basal = [n["tag"] for n in nodos if n["z_m"] == 0.0]
    esclavos = [n for n in nodos if n["z_m"] > 0]
    all_ele = [c["elementTag"] for c in cols] + [v["elementTag"] for v in vigas]

    reacf = tmpdir / "reac.txt"
    forcf = tmpdir / "forc.txt"
    for p in (reacf, forcf):
        p.unlink(missing_ok=True)

    ops.recorder("Node", "-file", str(reacf), "-node", *basal,
                 "-dof", 1, 2, 3, "reaction")
    ops.recorder("Element", "-file", str(forcf), "-ele", *all_ele,
                 "globalForce")

    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    w_nodo = w_total / len(esclavos)
    for n in esclavos:
        ops.load(n["tag"], 0.0, 0.0, -w_nodo, 0, 0, 0)

    ops.constraints("Plain")
    ops.numberer("RCM")
    ops.system("BandGeneral")
    ops.test("NormDispIncr", 1.0e-8, 50)
    ops.algorithm("Linear")
    ops.integrator("LoadControl", 1.0)
    ops.analysis("Static")
    ok = ops.analyze(1)
    ops.record()
    if ok != 0:
        print(f"\n  ATENCION: analisis NO convergio (ok={ok})")
        return

    reac = leer_recorder(reacf, len(basal) * 3)
    forc = leer_recorder(forcf, len(all_ele) * 12)
    n_escl = len(esclavos)

    # ---------- REACCIONES EN BASE ----------
    print(f"\n  REACCIONES EN BASE (por columna)  [W aplicado = {w_total:.1f} kN]")
    print("  " + "-" * 62)
    print(f"  {'Nodo':>4s} {'Columna':>7s} {'Rx (kN)':>10s} {'Ry (kN)':>10s} {'Rz (kN)':>10s}")
    print("  " + "-" * 62)
    sumrx = sumry = sumrz = 0.0
    for i, b in enumerate(basal):
        r = reac[3 * i:3 * i + 3]
        sumrx += r[0]; sumry += r[1]; sumrz += r[2]
        nom = next(n["nombre"] for n in nodos if n["tag"] == b)
        print(f"  {b:4d} {nom:>7s} {r[0]:10.1f} {r[1]:10.1f} {r[2]:10.1f}")
    print("  " + "-" * 62)
    print(f"  {'Suma':>11s} {sumrx:10.1f} {sumry:10.1f} {sumrz:10.1f}")
    bal = abs(sumrz - w_total) / w_total * 100
    print(f"  Balance vertical: |suma Rz - W| / W = {bal:.2f} %  "
          f"({'OK (cargas equilibradas)' if bal < 1.0 else 'DESBALANCE'})")

    # ---------- ESFUERZOS INTERNOS COLUMNAS ----------
    print(f"\n  ESFUERZOS INTERNOS - COLUMNAS  (en extremo inferior/base)")
    print("  " + "-" * 62)
    print(f"  {'Col':>4s} {'Elemento':>9s} {'N (kN)':>10s} {'Mx (kNm)':>10s} {'My (kNm)':>10s}")
    print("  " + "-" * 62)
    for k, c in enumerate(cols):
        f = forc[12 * k:12 * k + 12]   # [Fx,Fy,Fz, Mx,My,Mz]_i + [Fx,Fy,Fz, Mx,My,Mz]_j
        nom = next(n["nombre"] for n in nodos if n["tag"] == c["iNode"])
        print(f"  {nom:>4s} {c['elementTag']:9d} {-f[2]:10.1f} {f[3]:10.3f} {f[4]:10.3f}")
    print("  " + "-" * 62)
    print("  N = axial (signo: negativo compresion) | M = momento flector en base")

    # ---------- ESFUERZOS INTERNOS VIGAS ----------
    print(f"\n  ESFUERZOS INTERNOS - VIGAS nivel losa (Z={SEC_Z:.2f} m)")
    print("  " + "-" * 62)
    print(f"  {'Elem':>4s} {'Tramo':>9s} {'Dir':>3s} {'V_max (kN)':>11s} {'M_max (kNm)':>12s}")
    print("  " + "-" * 62)
    for k, v in enumerate(vigas):
        f = forc[12 * (len(cols) + k):12 * (len(cols) + k) + 12]
        v_i = abs(f[2])          # corte vertical (global Fz) en ambos extremos
        v_j = abs(f[8])
        vmax = max(v_i, v_j)
        if v["directriz"] == "X":    # viga paralela a X -> flexa sobre Y
            m_i, m_j = abs(f[4]), abs(f[10])
        else:                        # viga paralela a Y -> flexa sobre X
            m_i, m_j = abs(f[3]), abs(f[9])
        mmax = max(m_i, m_j)
        print(f"  {v['elementTag']:4d} {v['tramo']:>9s} {v['directriz']:>3s}"
              f" {vmax:11.2f} {mmax:12.2f}")
    print("  " + "-" * 62)
    print("  V = corte vertical (carga de gravedad) | M = max |momento flector|")

    # ---------- DESPLAZAMIENTOS ----------
    print(f"\n  DESPLAZAMIENTOS EN LOSA  (Z={SEC_Z:.2f} m, 17 nodos de piso)")
    print("  " + "-" * 62)
    print(f"  {'Nodo':>4s} {'Columna':>7s} {'dx (mm)':>10s} {'dy (mm)':>10s} {'dz (mm)':>10s}")
    print("  " + "-" * 62)
    rows = []
    for n in esclavos:
        d = ops.nodeDisp(n["tag"])
        rows.append((n, d[0] * 1000, d[1] * 1000, d[2] * 1000))
        print(f"  {n['tag']:4d} {n['nombre']:>7s} {d[0]*1000:10.3f} {d[1]*1000:10.3f} {d[2]*1000:10.3f}")
    print("  " + "-" * 62)
    maxdz = max(rows, key=lambda r: abs(r[3]))
    maxdx = max(rows, key=lambda r: abs(r[1]))
    maxdy = max(rows, key=lambda r: abs(r[2]))
    print(f"  Max |dz| = {abs(maxdz[3]):.3f} mm en nodo {maxdz[0]['tag']}")
    print(f"  Max |dx| = {abs(maxdx[1]):.3f} mm | Max |dy| = {abs(maxdy[2]):.3f} mm "
          "(esperado ~0 en gravedad simetrica)")


def analisis_modal(vigas_count, m_nodo, tmpdir):
    ops.wipeAnalysis()
    try:
        vals = list(ops.eigen(8))
    except Exception as e:
        print(f"\n  eigen fallo: {e}")
        return
    print(f"\n  ANALISIS MODAL DE LA SECCION (masa lumped {m_nodo:.1f} Mg/nodo de piso)")
    print("  " + "-" * 62)
    print(f"  {'Modo':>4s} {'Periodo T (s)':>13s} {'Frec. (Hz)':>11s} {'Omega (rad/s)':>13s} {'T/T1':>6s}")
    print("  " + "-" * 62)
    t1 = 2 * math.pi / math.sqrt(vals[0]) if vals[0] > 0 else float("nan")
    for i, o2 in enumerate(vals[:8], 1):
        if o2 <= 0:
            continue
        w = math.sqrt(o2)
        T = 2 * math.pi / w
        print(f"  {i:4d} {T:13.4f} {w/(2*math.pi):11.3f} {w:13.3f} {T/t1:6.3f}")
    print("  " + "-" * 62)
    print(f"  Periodo fundamental T1 = {t1:.4f} s  (rigidez alta en edificio bajo)")


if __name__ == "__main__":
    nivel = sys.argv[sys.argv.index("--nivel") + 1] if "--nivel" in sys.argv else "S1"
    if nivel not in SECCIONES:
        nivel = "S1"

    nodos, cols, vigas, secs, w_total, m_nodo = construir_modelo()

    encabezado(nivel)
    print(f"  Datos del modelo: {len(nodos):2d} nodos | {len(cols):2d} columnas | "
          f"{len(vigas):2d} vigas | W total = {w_total:.0f} kN")
    print(f"  Carga por nodo de piso: {w_total/len([n for n in nodos if n['z_m']>0]):.1f} kN")

    tmpdir = Path(__file__).resolve().parent / "_tmp_analisis"
    tmpdir.mkdir(exist_ok=True)

    analisis_gravedad(nodos, cols, vigas, w_total, tmpdir)
    analisis_modal(len(vigas), m_nodo, tmpdir)

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"\n  Fin del analisis de la seccion {SECCIONES[nivel]['nombre']} (OK).")