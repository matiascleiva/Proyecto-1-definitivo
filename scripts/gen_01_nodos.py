# -*- coding: utf-8 -*-
"""Genera y ejecuta el modelo base OpenSeesPy de nodos basales (Z=0).

Lee data/etapa1/fundaciones.json y escribe:

    out/etapa1/01_nodos_base.py     # módulo OpenSeesPy importable
    out/etapa1/resumen_nodos.txt    # estadísticas del paso

Uso:
    python scripts/gen_01_nodos.py
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.paths import OUT  # noqa: E402


def main() -> int:
    data_dir = Path(__file__).resolve().parents[1] / "data" / "etapa1"
    with open(data_dir / "fundaciones.json", encoding="utf-8") as f:
        data = json.load(f)

    nodos = [(i + 1, c["tag"], c["x_m"], c["y_m"], c["z_m"])
             for i, c in enumerate(data["columnas_basales"])]
    n = len(nodos)
    bx = (min(c["x_m"] for c in data["columnas_basales"]),
          max(c["x_m"] for c in data["columnas_basales"]))
    by = (min(c["y_m"] for c in data["columnas_basales"]),
          max(c["y_m"] for c in data["columnas_basales"]))

    mantisa = "".join(
        f"    ({t}, \"{nom}\", {x: .4f}, {y: .4f}, {z: .4f}),\n"
        for t, nom, x, y, z in nodos
    )

    src = (
        "# -*- coding: utf-8 -*-\n"
        '"""Nodos basales Z=0 — Nivel Superior de Fundaciones (S1).\n'
        "Generado por scripts/gen_01_nodos.py a partir de data/etapa1/fundaciones.json.\n"
        "Convención: X = ejes 1,2,3 (crece 1->3) · Y = ejes E..J (crece E->J).\n"
        '"""\n'
        "import openseespy.opensees as ops\n"
        "\n"
        "_FORMATO = \"fundaciones\"\n"
        "_LAMINA = " + repr(data["lamina"]) + "\n"
        f"_NODOS = {n}\n"
        "_BBOX_X = " + repr(bx) + "\n"
        "_BBOX_Y = " + repr(by) + "\n"
        "_NODOS_LIST = [\n" + mantisa + "]\n"
        "\n"
        "\n"
        "def crear():\n"
        '    ops.wipe()\n'
        '    ops.model("basic", "-ndm", 3, "-ndf", 6)\n'
        "    tabla = {}\n"
        "    for tag, nombre, x, y, z in _NODOS_LIST:\n"
        "        ops.node(tag, x, y, z)\n"
        "        tabla[tag] = nombre\n"
        "    for tag, *_ in _NODOS_LIST:\n"
        '        ops.fix(tag, 1, 1, 1, 1, 1, 1)\n'
        "    return tabla\n"
        "\n"
        "\n"
        "def info():\n"
        "    return {\"nodos\": _NODOS, \"formato\": _FORMATO, \"lamina\": _LAMINA,\n"
        "            \"bbox_x_m\": _BBOX_X, \"bbox_y_m\": _BBOX_Y}\n"
        "\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    tabla = crear()\n"
        '    print(f"Modelo base listo: {len(tabla)} nodos empotrados en Z=0")\n'
    )

    out_dir = OUT / "etapa1"
    out_dir.mkdir(parents=True, exist_ok=True)
    py_out = out_dir / "01_nodos_base.py"
    py_out.write_text(src, encoding="utf-8")

    resumen = (
        f"PASO 1 — NODOS BASALES (Z = Nivel Superior de Fundaciones)\n"
        f"lámina: {data['lamina']} · {data['lamina_nombre']}\n"
        f"formato: {data['formato']}\n"
        f"nodos: {n} · bbox: X {bx[0]}..{bx[1]} m · Y {by[0]}..{by[1]} m\n"
        "tags: " + ", ".join(c["tag"] for c in data["columnas_basales"]) + "\n"
    )
    (out_dir / "resumen_nodos.txt").write_text(resumen, encoding="utf-8")

    print(py_out)
    print(resumen)

    try:
        subprocess.run([sys.executable, str(py_out)], check=True)
    except Exception as err:
        print(f"  [aviso] no se pudo correr el modelo base: {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())