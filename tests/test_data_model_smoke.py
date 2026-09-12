from pathlib import Path
import sys
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_model import load_model


def test_network_and_missing_state():
    with tempfile.TemporaryDirectory() as td:
        run = Path(td) / "corrida_20260911_v3_2"
        run.mkdir()
        pd.DataFrame([
            {"rut_empresa":"111","razon_social":"EMPRESA A S.A.","rut_persona":"1-9","nombre_original":"ANA UNO","cargo":"Presidente","fecha_nombramiento":"01/01/2026","source_url":"https://cmf.cl/x?tipoentidad=RVEMI&mercado=V","identidad_director":"RUT:19","sexo_estimado":"MUJER","metodo_clasificacion_sexo":"AUTO","confianza_clasificacion_sexo":"ALTA","nota_clasificacion_sexo":""},
            {"rut_empresa":"222","razon_social":"EMPRESA B S.A.","rut_persona":"1-9","nombre_original":"ANA UNO","cargo":"Director","fecha_nombramiento":"02/01/2026","source_url":"https://cmf.cl/x?tipoentidad=RVEMI&mercado=V","identidad_director":"RUT:19","sexo_estimado":"MUJER","metodo_clasificacion_sexo":"AUTO","confianza_clasificacion_sexo":"ALTA","nota_clasificacion_sexo":""},
        ]).to_csv(run / "03_directores_con_sexo.csv", index=False)
        pd.DataFrame([
            {"rut_empresa":"111","razon_social":"EMPRESA A S.A.","n_titulares":"1","diagnostico_consistencia":"CONSISTENTE"},
            {"rut_empresa":"222","razon_social":"EMPRESA B S.A.","n_titulares":"1","diagnostico_consistencia":"CONSISTENTE"},
            {"rut_empresa":"333","razon_social":"EMPRESA C S.A.","n_titulares":"0","diagnostico_consistencia":"SIN_COMPOSICION_NOMINAL"},
        ]).to_csv(run / "05_resumen_final_v3.csv", index=False)
        pd.DataFrame([
            {"rut_empresa":"333","razon_social":"EMPRESA C S.A.","estado":"SIN_COMPOSICION_NOMINAL","error":"Sin Información"}
        ]).to_csv(run / "12_entidades_sin_composicion_nominal.csv", index=False)

        model = load_model(run)
        assert len(model["people"]) == 1
        assert len(model["interlocks"]) == 1
        assert int(model["interlocks"].iloc[0]["directores_compartidos"]) == 1
        state = model["companies"].loc[model["companies"]["rut_empresa"].eq("333"), "estado_datos"].iloc[0]
        assert state == "SIN_COMPOSICION_NOMINAL"
