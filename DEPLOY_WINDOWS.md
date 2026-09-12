# Ejecución y validación en Windows

Desde PowerShell, en la carpeta del proyecto:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

Pruebas:

```powershell
py -m pip install pytest
py -m pytest -q
py -m compileall -q app.py data_model.py scripts tests
```

Base local opcional:

```powershell
py scripts/build_database.py --output private_data/directorios_cmf.sqlite
```

Mantén los archivos en UTF-8. Si la consola muestra caracteres incorrectos, ejecuta Python con `py -X utf8`.

La base SQLite contiene correspondencias privadas y no debe publicarse. Streamlit solo necesita `app.py`, `data_model.py`, `requirements.txt` y `data/public/`. Para actualizar datos, ejecuta localmente `py scripts/build_public_snapshot.py --source private_data/corrida_20260911_v3_2` y conserva una copia privada de `private_data/person_ids.json`.

El inicio local no publica cambios. Para desplegar, utiliza el flujo habitual del repositorio después de validar y resolver el tratamiento de los insumos personales.
