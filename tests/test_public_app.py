from pathlib import Path
import re
import sys
import sqlite3

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_model import load_model, read_csv

PAGES = ["Inicio", "Empresas", "Directores", "Red de directorios", "Diversidad", "Ley 21.757", "Metodología"]


@pytest.fixture(scope="module")
def model():
    return load_model(ROOT / "data/public")


def test_utf8_repository():
    for path in ROOT.rglob("*"):
        if path.suffix in {".py", ".md", ".csv", ".txt"} and ".git" not in path.parts:
            text = path.read_text(encoding="utf-8-sig")
            assert not re.search(r"\u00c3[\u0080-\u00bf]|\u00e2\u20ac|\u00c2\u00b0|\ufffd", text), path


def test_csv_accents_and_strict_decoding(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text("nombre\nMaría Muñoz — Ñuñoa\n", encoding="utf-8-sig")
    assert read_csv(path).iloc[0, 0] == "María Muñoz — Ñuñoa"
    path.write_bytes(b"nombre\n\xff\n")
    with pytest.raises(UnicodeDecodeError):
        read_csv(path)


@pytest.mark.parametrize("page", PAGES)
def test_public_pages(page, model):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert app.sidebar.radio[0].options == PAGES
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception
    visible = " ".join(str(el.value) for kind in ("markdown", "caption", "info", "warning", "error", "subheader", "metric") for el in app.get(kind))
    visible += " ".join(str(el.value.to_json(force_ascii=False)) for el in app.dataframe)
    visible += " ".join(str(el.options) for kind in ("selectbox", "multiselect") for el in app.get(kind))
    visible += " ".join(str(el.proto) for el in app.get("plotly_chart"))
    assert not re.search(r"snapshot|quality.flags|private.identity|\bCSV\b|SQLite|pipeline|SIN_COMPOSICION|POST_LEY|debug", visible, re.I)
    private = []
    source = ROOT / "private_data/corrida_20260911_v3_2/03_directores_con_sexo.csv"
    if source.exists():
        private = read_csv(source)["identidad_director"]
    for key in private:
        if key.startswith("RUT:"):
            rut = key[4:]
            assert key not in visible
            assert not re.search(r"(?<!\d)" + re.escape(rut) + r"(?!\d)", visible)
    for table in app.dataframe:
        assert not {"rut_persona", "identidad_director", "_person_key", "persona_id", "sexo_estimado"}.intersection(table.value.columns)


def test_missing_company_and_literal_search(model):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.sidebar.radio[0].set_value("Empresas").run()
    missing = model["companies"].query("directores_reconstruidos == 0").iloc[0]
    app.selectbox[0].set_value(missing.rut_empresa).run()
    assert not app.exception
    assert app.info[0].value == "Información de directorio no disponible en la fuente consultada"
    assert app.metric[0].value == "—"
    app.sidebar.radio[0].set_value("Directores").run()
    app.text_input[0].set_value("[").run()
    assert not app.exception


def test_model_invariants(model):
    current = model["current"]
    assert not current.duplicated(["persona_id", "rut_empresa"]).any()
    assert model["people"].empresas.sum() == len(current)
    assert model["diversity"].total.sum() == len(current)
    assert not {"rut_persona", "identidad_director", "_person_key"}.intersection(current.columns)
    for row in model["interlocks"].itertuples():
        a = set(current.loc[current.rut_empresa.eq(row.empresa_a), "persona_id"])
        b = set(current.loc[current.rut_empresa.eq(row.empresa_b), "persona_id"])
        assert len(a & b) == row.directores_compartidos


@pytest.mark.parametrize("shared", [0, 1])
def test_network_small_ranges(shared, model, monkeypatch):
    import data_model
    import streamlit as st

    sample = dict(model)
    sample["interlocks"] = model["interlocks"].head(shared).copy()
    if shared:
        sample["interlocks"]["directores_compartidos"] = 1
    monkeypatch.setattr(data_model, "load_model", lambda _: sample)
    st.cache_data.clear()
    try:
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        app.sidebar.radio[0].set_value("Red de directorios").run()
        assert not app.exception
        assert not app.slider
    finally:
        st.cache_data.clear()


def test_sqlite_builder(tmp_path, model):
    from scripts.build_database import build

    output = tmp_path / "directorios.sqlite"
    source = ROOT / "private_data/corrida_20260911_v3_2"
    if not source.exists():
        pytest.skip("Validación local opcional: fuentes privadas no disponibles")
    build(source, output)
    with sqlite3.connect(output) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM personas").fetchone()[0] == len(model["people"])
        assert conn.execute("SELECT COUNT(*) FROM membresias_actuales").fetchone()[0] == len(model["current"])
        assert conn.execute("SELECT nombre FROM personas ORDER BY persona_id LIMIT 1").fetchone()[0] in set(model["people"].nombre)
