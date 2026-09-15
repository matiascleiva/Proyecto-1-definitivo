"""Paso 4 — Sismo y cargas laterales (NCh433.Of1996 mod.2009 + DS61).

Genera y ejecuta, para cada etapa, un script OpenSeesPy que:

  1. Arma el modelo 3D (misma base del Paso 3, reutilizando
     `lineas_base` de step3_modelo).
  2. Sonda elástica por dirección → período Rayleigh T (secciones brutas);
     T* = 1.5·T (influencia del agrietamiento, DS61).
  3. Método de análisis estático DS61 Art. 15:
        Q0 = C·I·P                    (NCh433 6.2.3)
        C  = 2.75·(A0/g)·(T'/T*)^n/R  (NCh433 6.2.3.1)
        A0·S/(6g) ≤ C ≤ Cmax/R
     F_k = V·P_k·h_k / Σ(P_j·h_j)     (NCh433 6.2.5)
  4. Aplica fuerzas por nivel + gravedad + torsión accidental (e=0.1·B)
     en los 4 casos (dir X/Y, excentricidad ±).
  5. Reporta reacciones, cortante basal, momentos de volteo, drift por
     nivel y fuerzas en columnas/muros (sismo.json), y lista de F_k.

Parámetros normativos por defecto (configurables):
    Zona sísmica 2: A0 = 0.30g ; Suelo II: S=1.0, To=0.30, T'=0.35, n=1.0
    R = 11 (estructura de muros de H.A. + marcos) ; I = 1.0 (habitacional)

Uso:
    python scripts/step4_sismo.py [etapa]
"""
import json
import math
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.paths import OUT  # noqa: E402
import step3_modelo as S  # noqa: E402

# --- parámetros normativos ------------------------------------------------
A0_G = 0.30          # zona sísmica 2 (A0 = 0.30g)
S_SUELO = 1.00       # suelo II
TO = 0.30
TPRIME = 0.35
N_EXP = 1.0          # exponente n (análisis estático, suelo II)
CMAX = 2.75          # Tabla 6.4 (suelos I/II)
R = 11
I_FACT = 1.0
G_GRAV = 9.81
FCT_AGRI = 1.5       # T* = 1.5·T_bruto (DS61, secciones agrietadas)
EEX = 0.10           # excentricidad accidental = 0.1·B
PCT_SC = 0.25        # peso sísmico = D + 25% SC (NCh433 6.2.2)
QG_SISM = S.QGP["pp_losa"] + S.QGP["pm"] + PCT_SC * S.QGP["sc"]  # kN/m²

VIGA_KM = S.SECVIG["A"] * S.GAMMA                 # 11.52 kN/m
MUR_KM = 0.20 * S.GAMMA * S.H_PISO                # 19.01 kN/m/nivel (e=0.20)


def peso_por_nivel(etapa, meta):
    """Peso sísmico P_k (kN) por nivel, uniforme entre pisos."""
    vigas = json.loads((OUT / f"etapa{etapa}" / "vigas_101.json")
                       .read_text(encoding="utf-8"))["vigas"]
    lon_vigas = sum(v["largo_m"] for v in vigas)
    muros = meta["muros"]
    lon_muros = sum(m["largo_m"] for m in muros)
    p = (meta["area_piso_m2"] * QG_SISM
         + len(meta["apoyos"]) * S.SPP_COL
         + lon_vigas * VIGA_KM
         + lon_muros * MUR_KM)
    return p


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    etapa = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    filas, meta = S.lineas_base(etapa)
    out_dir = OUT / f"etapa{etapa}"
    out_dir.mkdir(parents=True, exist_ok=True)

    n_col = meta["n_col"]
    n_mur = meta["n_mur"]
    apoyos = meta["apoyos"]
    vigas_ids = meta["vigas_ids"]
    VIG = {k: vigas_ids[(k - 1)::S.N_NIVELES]
           for k in range(1, S.N_NIVELES + 1)}
    BX = float(json.loads((OUT / f"etapa{etapa}" / "losas_101.json")
                          .read_text(encoding="utf-8"))["largo_x_m"])
    BY = float(json.loads((OUT / f"etapa{etapa}" / "losas_101.json")
                          .read_text(encoding="utf-8"))["largo_y_m"])
    p_nivel = peso_por_nivel(etapa, meta)
    p_k = [p_nivel] * S.N_NIVELES
    z_k = [S.z_nivel(k) for k in range(1, S.N_NIVELES + 1)]
    den = sum(p * z for p, z in zip(p_k, z_k))
    f_k = [p * z / den for p, z in zip(p_k, z_k)]

    marcas_col = [f'"{a["tag"]}"' for a in apoyos]
    j_muros = list(range(100, 100 + n_mur))

    LJ = ["from openseespy.opensees import *",
          "import sys, json, math",
          f"P = {p_k!r}",
          f"Z = {z_k!r}",
          f"F = {f_k!r}",
          f"CM = ({meta['cm'][0]:g}, {meta['cm'][1]:g})",
          f"BX, BY = {[BX, BY]!r}",
          f"NBASE = {n_col}",
          f"MWAL = {j_muros!r}",
          f"COLS = [{', '.join(marcas_col)}]",
          f"VIG = {VIG!r}",
          f"QG = {S.Q_SUB:g}", f"SPP = {S.SPP_COL:g}",
          "def _anal():",
          "    system('BandSPD'); numberer('RCM')",
          "    constraints('Transformation'); algorithm('Newton')",
          "    integrator('LoadControl', 1.0); analysis('Static')",
          "    return analyze(1)"]

    # --- builder (copiado de lineas_base, indentado dentro de función) ---
    LJ += ["def _base():", "    wipe()"]
    for ln in filas:
        if ln.startswith("wipe()") or ln.startswith("from openseespy"):
            continue
        if ln.startswith("import "):
            continue
        LJ.append("    " + ln)

    # --- PESO SÍSMICO + fórmula Rayleigh aplicada en runtime --------------

    # sonda dirección X e Y → período Rayleigh por dirección
    LJ += ["def _sonda(dx, dy):",
           "    _base()",
           "    timeSeries('Linear', 100)",
           "    pattern('Plain', 200, 100)",
           "    for k in range(5):",
           "        kz = 9500 + k + 1",
           "        load(kz, P[k]*dx, P[k]*dy, 0.0, 0.0, 0.0, 0.0)",
           "    ok = _anal()",
           "    return [nodeDisp(9500 + k + 1, 1 if dx > 0 else 2) "
           "for k in range(5)]"]
    LJ += ["UX = _sonda(1.0, 0.0)", "UY = _sonda(0.0, 1.0)",
           "TX = 2*math.pi*math.sqrt(sum(P[k]*UX[k]**2 for k in range(5)) / "
           "(9.81*sum(P[k]*UX[k] for k in range(5))))",
           "TY = 2*math.pi*math.sqrt(sum(P[k]*UY[k]**2 for k in range(5)) / "
           "(9.81*sum(P[k]*UY[k] for k in range(5))))",
           "print('T Rayleigh   X: %.4f s   Y: %.4f s' % (TX, TY))"]

    # --- corte basal y fuerzas por nivel (estático DS61) ------------------
    LJ += [f"AO, Rr, II = {A0_G}, {R}, {I_FACT}",
           f"TS, TT = {S_SUELO}, {TPRIME}",
           "def C_calc(T):",
           f"    Tst = T * {FCT_AGRI}",
           "    C = 2.75 * AO * (TT / Tst)**%g / Rr" % N_EXP,
           f"    cmax = {CMAX / R:.6f}",
           f"    cmin = AO * TS / 6.0",
           "    return Tst, max(cmin, min(C, cmax))",
           "TXs, CX = C_calc(TX)", "TYs, CY = C_calc(TY)",
           "Wtot = sum(P)",
           "VX = CX * II * Wtot", "VY = CY * II * Wtot",
           "print('  T* X=%.4fs  C_X=%.4f  V_X=%.1f kN' % (TXs, CX, VX))",
           "print('  T* Y=%.4fs  C_Y=%.4f  V_Y=%.1f kN' % (TYs, CY, VY))",
           "fx = [VX * f for f in F]", "fy = [VY * f for f in F]"]

    # --- 4 casos: dir (X/Y) × excentricidad accidental (±) ----------------
    LJ += ["todo = {}"]
    for dx, dy, ejex, sign in ((1.0, 0.0, "X", 1.0), (1.0, 0.0, "X", -1.0),
                               (0.0, 1.0, "Y", 1.0), (0.0, 1.0, "Y", -1.0)):
        exl = EEX * (BY if ejex == "X" else BX)
        nm = f"{ejex} e{'+' if sign > 0 else '-'}"
        LI = ["_base()", "timeSeries('Linear', 100)",
              "pattern('Plain', 300, 100)"]
        for i, a in enumerate(apoyos, start=1):
            b = meta["nbase"][a["tag"]]
            Fg = S.Q_SUB * a["a_infl"] + S.SPP_COL
            for k in range(1, S.N_NIVELES + 1):
                LI.append("load(%d, 0.0, 0.0, %.6f, 0.0, 0.0, 0.0)"
                          % (S.tag_losa(k, b), -Fg))
        LI += ["for k in range(5):",
               "    kz = 9500 + k + 1"]
        if ejex == "X":
            LI += ["    load(kz, fx[k]*%g, 0.0, 0.0, 0.0, 0.0, %.6f)"
                   % (sign, sign * exl)]
        else:
            LI += ["    load(kz, 0.0, fy[k]*%g, 0.0, 0.0, 0.0, %.6f)"
                   % (sign, sign * exl)]
        LI += ["ok = _anal()", "reactions()",
               "rx = [nodeReaction(i, 1) for i in range(1, NBASE + 1)]",
               "ry = [nodeReaction(i, 2) for i in range(1, NBASE + 1)]",
               "rw = [nodeReaction(3000 + j, %s) for j in MWAL]"
               % (ejex == "X" and 1 or 2),
               "Vbase = sum(rx) + sum(rw)" if ejex == "X" else
               "Vbase = sum(ry) + sum(rw)",
               "disp = [nodeDisp(9500 + k + 1, %s) for k in range(5)]"
               % (ejex == "X" and 1 or 2),
               "drift = [(disp[k] - (disp[k-1] if k else 0.0))/%g "
               "for k in range(5)]" % S.H_PISO,
               "col = {}",
               "for k in range(1, 6):",
               "    col[k] = {}",
               "    for i in range(NBASE):",
               "        lf = eleResponse(10000 + k * 1000 + (i + 1), "
               "'localForces')",
               "        col[k][COLS[i]] = lf",
               "    for j in MWAL:",
               "        lf = eleResponse(12000 + k * 1000 + j, 'localForces')",
               f"        col[k]['MUR-' + str(j)] = lf",
               "    for etag in VIG[k]:",
               "        col[k]['B-' + str(etag)] = eleResponse(etag, 'localForces')",
               "todo[" + repr(nm) + "] = dict("
               "V=abs(Vbase), disp=disp, drift=drift, col=col)"]
        LJ += LI

    LJ += ["import json",
           "with open(" + repr(str(out_dir / "sismo.json")) +
           ", 'w', encoding='utf-8') as f:",
           "    json.dump(dict(TX=TX, TY=TY, TXs=TXs, TYs=TYs, CX=CX, CY=CY, "
           "VX=VX, VY=VY, W=Wtot, Fx=fx, Fy=fy, " + "todo=" +
           repr("__TODO__").replace("'__TODO__'", "todo") +
           "), f, ensure_ascii=False, indent=2, sort_keys=True)",
           "print('sismo ok')"]

    # corregir el dump: todo ya es dict; reemplazar placeholder
    txt = "\n".join(LJ)
    txt = txt.replace("__TODO__", "todo")
    script = out_dir / "sismo_ops.py"
    script.write_text(txt, encoding="utf-8")

    print(f"SISMO Etapa {etapa} → {script}")
    print(f"  P_nivel={p_nivel:.1f} kN, W={sum(p_k):.0f} kN, "
          f"A_piso={meta['area_piso_m2']:.1f} m², B=({BX}×{BY})")

    r = subprocess.run([sys.executable, str(script)],
                       capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        raise SystemExit(1)

    # orden de resultados por elemento y envolvente (para Unity)
    sismo = json.loads((out_dir / "sismo.json").read_text(encoding="utf-8"))
    env = _envolv(sismo)
    (out_dir / "sismo_envolvente.json").write_text(
        json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    _documento(etapa, meta, sismo, env, out_dir)


def _envolv(sismo):
    """Envolvente por elemento/nivel: |P|,|Vy|,|Vz|,|My|,|Mz| entre los 4 casos.

    localForces de elasticBeamColumn devuelve 12 valores (extremo i y j);
    se emparan por posición (0↔6, 1↔7, ...).
    """
    env = {}
    for nm, caso in sismo.get("todo", {}).items():
        for k, cols in caso["col"].items():
            for tag, lf in cols.items():
                e = env.setdefault(tag, {}).setdefault(int(k), [0.0] * 6)
                for i in range(6):
                    e[i] = max(e[i], abs(lf[i]), abs(lf[i + 6]))
    nombres = ("P", "Vy", "Vz", "T", "My", "Mz")
    return {tag: {str(k): {nombres[i]: v[i] for i in range(6)}
             for k, v in ks.items()} for tag, ks in env.items()}


def _documento(etapa, meta, sismo, env, out_dir):
    dr = max((max(abs(d) for d in c.get("drift", [0])) for c in
              sismo.get("todo", {}).values()), default=0.0)
    L = [f"# Documento Sismo — Etapa {etapa}",
         "",
         "Parámetros normativos (NCh433.Of1996 mod.2009 + DS61):",
         f"- Zona sísmica 2, A0 = {A0_G:.2f}g   Suelo II (S={S_SUELO:.2f}, "
         f"To={TO}, T'={TPRIME}, n={N_EXP})   R={R}   I={I_FACT}",
         f"- Peso sísmico P_k = D + {PCT_SC:.0%}SC = {QG_SISM:.3f} kN/m²"
         f" + PP columnas/vigas/muros",
         f"- Área de piso: {meta['area_piso_m2']:.1f} m²; "
         f"W = {sismo['W']:.0f} kN en {len(sismo['Fx'])} niveles",
         "",
         "Períodos (T bruto por Rayleigh, T* = 1.5·T por agrietamiento):",
         f"- X: T = {sismo['TX']:.3f} s → T* = {sismo['TXs']:.3f} s",
         f"- Y: T = {sismo['TY']:.3f} s → T* = {sismo['TYs']:.3f} s",
         "",
         "Corte basal estático (DS61 Art. 15):",
         f"- C_X = {sismo['CX']:.3f}   V_X = {sismo['VX']:.0f} kN "
         f"(V/W = {sismo['VX']/sismo['W']:.2%})",
         f"- C_Y = {sismo['CY']:.3f}   V_Y = {sismo['VY']:.0f} kN "
         f"(V/W = {sismo['VY']/sismo['W']:.2%})",
         "",
         f"Drift máximo de entrepiso: {dr*1000:.2f}‰ (h = {S.H_PISO:.2f} m)",
         "",
         "Resultados detallados en sismo.json (F_k, fuerzas por elemento/nivel "
         "para los 4 casos X±, Y±) y envolvente en sismo_envolvente.json.",
         ]
    (out_dir / "DOCUMENTO_SISMO.md").write_text("\n".join(L),
                                                encoding="utf-8")
    print("\n".join(L[5:]))


if __name__ == "__main__":
    raise SystemExit(main())