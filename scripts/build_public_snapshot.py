"""Run locally; publish data/public only, never the registry or inputs."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_model import PUBLIC_COLUMNS, validate_public_table
from scripts.private_model import load_model


def build(source: Path, output: Path, registry: Path) -> dict:
    if registry.resolve().is_relative_to(output.resolve()) or source.resolve().is_relative_to(output.resolve()):
        raise ValueError("Fuentes y correspondencias deben estar fuera del directorio público")
    if (output / "manifest.json").exists() and not registry.exists():
        raise ValueError("Falta la correspondencia persistente: restaurar su copia privada antes de actualizar")
    if not re.fullmatch(r"corrida_\d{8}(?:_[a-zA-Z]+[0-9]?(?:_[0-9])?)?", source.name):
        raise ValueError("Nombre de edición inválido; no publicar nombres de rutas arbitrarios")
    expected = {"manifest.json", *(f"{name}.json" for name in PUBLIC_COLUMNS)}
    if output.exists() and any(p.name not in expected or not p.is_file() for p in output.iterdir()):
        raise ValueError("El directorio público contiene archivos ajenos al contrato")
    model = load_model(source, registry)
    tables = {}
    for name, columns in PUBLIC_COLUMNS.items():
        frame = model[name].reindex(columns=columns).copy()
        if name == "current":
            def public_url(row):
                query = parse_qs(urlparse(str(row.source_url)).query)
                return "https://www.cmfchile.cl/institucional/mercados/detalle_listado_directorios.php?" + urlencode({
                    "rut": row.rut_empresa,
                    "tipoentidad": query.get("tipoentidad", [""])[0],
                    "mercado": query.get("mercado", [""])[0],
                }) if row.source_url else ""
            frame["source_url"] = frame.apply(public_url, axis=1)
        validate_public_table(name, frame)
        tables[name] = frame
    output.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_json(output / f"{name}.json", orient="table", force_ascii=False, indent=2)
    (output / "manifest.json").write_text(json.dumps({"schema_version": 1, "snapshot": model["snapshot"]}, indent=2), encoding="utf-8")
    return model


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "data/public")
    parser.add_argument("--registry", type=Path, default=ROOT / "private_data/person_ids.json")
    args = parser.parse_args()
    model = build(args.source, args.output, args.registry)
    print(f"Snapshot público: {len(model['people'])} personas; {len(model['current'])} membresías")
