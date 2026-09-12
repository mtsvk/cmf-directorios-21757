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
py scripts/build_database.py --output data/directorios_cmf.sqlite
```

Mantén los archivos en UTF-8. Si la consola muestra caracteres incorrectos, ejecuta Python con `py -X utf8`.

La base SQLite contiene correspondencias privadas y no debe publicarse. Revisa la advertencia del README sobre identificadores personales presentes en el CSV versionado antes de distribuir los insumos.

El inicio local no publica cambios. Para desplegar, utiliza el flujo habitual del repositorio después de validar y resolver el tratamiento de los insumos personales.
