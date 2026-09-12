from pathlib import Path
import json
import re
import shutil
import sys

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_model import PUBLIC_COLUMNS, load_model, validate_public_table
from scripts.private_model import _person_internal_key, _public_person_ids
from scripts.build_public_snapshot import build


def test_public_files_contract():
    root = ROOT / "data/public"
    assert {p.name for p in root.iterdir()} == {"manifest.json", *(f"{key}.json" for key in PUBLIC_COLUMNS)}
    model = load_model(root)
    for name in PUBLIC_COLUMNS:
        validate_public_table(name, model[name])
        document = json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
        assert set(document) == {"schema", "data"}
        assert all(set(row) == {"index", *PUBLIC_COLUMNS[name]} for row in document["data"])
    assert not {"private_people", "mandates"} & model.keys()
    counts = model["current"].groupby("persona_id").rut_empresa.nunique()
    assert (counts > 1).any()
    assert model["people"].set_index("persona_id").empresas.sort_index().equals(counts.sort_index())


@pytest.mark.parametrize("column", ["rut_persona", "rut", "rut_hash", "identidad_director", "_person_key", "private_map"])
def test_reject_private_columns(column):
    frame = load_model(ROOT / "data/public")["people"].head(1).copy()
    frame[column] = "private"
    with pytest.raises(ValueError):
        validate_public_table("people", frame)


@pytest.mark.parametrize("value", ["12.345.678-5", "12345678-5", "123456785", "12345678", "RUT:123456785", "12.345.678", "12345678-K"])
def test_reject_personal_rut_patterns(value):
    frame = load_model(ROOT / "data/public")["people"].head(1).copy()
    frame.loc[frame.index[0], "nombre"] = "Persona " + value
    with pytest.raises(ValueError):
        validate_public_table("people", frame)


@pytest.mark.parametrize("suffix", ["&rut_persona=123456785", "#123456785", "&rut=123456785"])
def test_reject_private_source_url(suffix):
    frame = load_model(ROOT / "data/public")["current"].head(1).copy()
    frame.loc[frame.index[0], "source_url"] += suffix
    with pytest.raises(ValueError):
        validate_public_table("current", frame)


def test_identity_stable_across_reorder_additions_and_homonyms(tmp_path):
    rows = pd.DataFrame([
        {"rut_persona": "12.345.678-5", "nombre_original": "ANA", "identidad_director": "ignored"},
        {"rut_persona": "12345678-5", "nombre_original": "ANA CAMBIO"},
        {"rut_persona": "11.111.111-1", "nombre_original": "ANA"},
    ])
    rows["_person_key"] = rows.apply(_person_internal_key, axis=1)
    registry = tmp_path / "private/ids.json"
    first = _public_person_ids(rows, registry)
    assert rows._person_key.nunique() == 2
    assert len(set(first.values())) == 2
    more = pd.concat([rows.iloc[::-1], pd.DataFrame([{"_person_key": "RUT:222222222"}])])
    second = _public_person_ids(more, registry)
    assert all(second[key] == value for key, value in first.items())
    with pytest.raises(ValueError):
        _person_internal_key(pd.Series({"nombre_original": "ANA"}))


def test_foreign_placeholder_never_merges_people():
    base = {"rut_persona": "0-E", "nombre_original": "ANA", "rut_empresa": "70000001"}
    key = _person_internal_key(pd.Series(base))
    assert key.startswith("UNRESOLVED:")
    assert key != _person_internal_key(pd.Series({**base, "rut_empresa": "70000002"}))
    assert key != _person_internal_key(pd.Series({**base, "nombre_original": "OTRA PERSONA"}))
    assert key == _person_internal_key(pd.Series({**base, "rut_persona": "0-E (Extranjero)"}))


def test_actual_source_identity_and_no_rut_leak():
    source = ROOT / "private_data/corrida_20260911_v3_2/03_directores_con_sexo.csv"
    if not source.exists():
        pytest.skip("Auditoría cruzada local: fuente privada no disponible")
    raw = pd.read_csv(source, dtype=str, keep_default_na=False)
    registry = json.loads((ROOT / "private_data/person_ids.json").read_text())
    model = load_model(ROOT / "data/public")
    raw["key"] = raw.apply(_person_internal_key, axis=1)
    known = raw[raw.key.str.startswith("RUT:")]
    for key, rows in known.groupby("key"):
        public = model["current"].loc[model["current"].persona_id.eq(registry[key])]
        assert set(public.rut_empresa) == set(rows.rut_empresa)
    tokens = set(known.key.str.removeprefix("RUT:"))
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, tokens)) + r")(?!\w)")
    for name in PUBLIC_COLUMNS:
        for column in model[name]:
            assert not model[name][column].astype(str).str.contains(pattern).any(), (name, column)


def test_build_and_run_with_only_sanitized_data(tmp_path, monkeypatch):
    # Synthetic local inputs exercise the full boundary; no real private file required.
    source = tmp_path / "private/corrida_20260911_test"
    source.mkdir(parents=True)
    rows = [{"rut_persona": "12.345.678-5", "nombre_original": "María Muñoz", "rut_empresa": company,
             "razon_social": "Empresa A" if company.endswith("1") else "Empresa B", "cargo": "DIRECTORA", "fecha_nombramiento": "01/01/2026",
             "source_url": "", "sexo_estimado": "MUJER", "confianza_clasificacion_sexo": "ALTA"}
            for company in ("70000001", "70000002")]
    pd.DataFrame(rows).to_csv(source / "03_directores_con_sexo.csv", index=False)
    pd.DataFrame(rows)[["rut_empresa", "razon_social"]].to_csv(source / "05_resumen_final_v3.csv", index=False)
    bundle = tmp_path / "deployment"
    build(source, bundle / "data/public", tmp_path / "private/ids.json")
    shutil.rmtree(tmp_path / "private")
    for name in ("app.py", "data_model.py"):
        shutil.copy2(ROOT / name, bundle / name)
    monkeypatch.setattr(sys, "argv", [str(bundle / "app.py")])
    model = load_model(bundle / "data/public")
    assert len(model["people"]) == 1
    assert model["current"].persona_id.nunique() == 1
    import streamlit as st
    st.cache_data.clear()
    try:
        app = AppTest.from_file(str(bundle / "app.py"), default_timeout=30).run()
        pages = app.sidebar.radio[0].options
        assert len(pages) == 7
        for page in pages:
            app.sidebar.radio[0].set_value(page).run()
            assert not app.exception
            assert not app.error
    finally:
        st.cache_data.clear()
