#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.private_model import discover_run_dir, load_model


def write_table(conn: sqlite3.Connection, name: str, df: pd.DataFrame) -> None:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
    out.to_sql(name, conn, if_exists="replace", index=False)


def build(run_dir: Path, output: Path) -> None:
    model = load_model(run_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with sqlite3.connect(output) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        write_table(conn, "empresas", model["companies"])
        write_table(conn, "personas", model["people"])
        write_table(conn, "mandatos", model["mandates"])
        write_table(conn, "membresias_actuales", model["current"])
        write_table(conn, "interlocks_empresas", model["interlocks"])
        write_table(conn, "metricas_red_empresas", model["network_metrics"])
        write_table(conn, "diversidad_empresas", model["diversity"])
        write_table(conn, "reporte_ley_21757", model["law"])
        write_table(conn, "quality_flags", model["quality_flags"])
        write_table(conn, "personas_private_identity_map", model["private_people"])
        pd.DataFrame([{"snapshot": model["snapshot"], "source_dir": str(run_dir)}]).to_sql(
            "snapshots", conn, if_exists="replace", index=False
        )
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_mandatos_empresa ON mandatos(rut_empresa);
            CREATE INDEX IF NOT EXISTS idx_mandatos_persona ON mandatos(persona_id);
            CREATE INDEX IF NOT EXISTS idx_memberships_empresa ON membresias_actuales(rut_empresa);
            CREATE INDEX IF NOT EXISTS idx_memberships_persona ON membresias_actuales(persona_id);
            CREATE INDEX IF NOT EXISTS idx_interlocks_a ON interlocks_empresas(empresa_a);
            CREATE INDEX IF NOT EXISTS idx_interlocks_b ON interlocks_empresas(empresa_b);
            """
        )

    print(f"SQLite creado: {output}")
    print(f"Snapshot: {model['snapshot']}")
    print(f"Empresas: {len(model['companies'])}")
    print(f"Personas: {len(model['people'])}")
    print(f"Mandatos fuente: {len(model['mandates'])}")
    print(f"Interlocks empresa-empresa: {len(model['interlocks'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye la base relacional de Directorios CMF.")
    parser.add_argument("--run-dir", help="Carpeta corrida_*; por defecto usa la más reciente.")
    parser.add_argument("--output", default="private_data/directorios_cmf.sqlite", help="Ruta del SQLite privado de salida.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else discover_run_dir(ROOT / "private_data")
    if run_dir is None:
        raise SystemExit("No se encontró una corrida con los archivos requeridos.")
    build(run_dir.resolve(), Path(args.output).resolve())


if __name__ == "__main__":
    main()
