# Observatorio de gobierno corporativo — Directorios CMF

Dashboard público en Streamlit para explorar entidades fiscalizadas por la CMF, personas y conexiones entre directorios.

## Exploración

Inicio presenta entidades con directorio identificable, personas, participación en varios directorios y rankings de conexiones y cargos. Le siguen Empresas, Directores, Red de directorios, Diversidad, Ley 21.757 y Metodología.

Las fichas incluyen cargos, nombramientos y enlaces disponibles a la CMF. Las entidades sin información de directorio siguen siendo consultables. La fecha de edición procede de la carpeta de datos y no representa una consulta en tiempo real.

Compartir directores demuestra una relación de directorio; no demuestra propiedad común, control, coordinación ni pertenencia a un grupo económico. La diversidad es agregada: su clasificación es una estimación derivada de los datos, no necesariamente declarada por la persona. Cada persona cuenta una vez por entidad. Ley 21.757 reproduce la evaluación de los datos sin formular nuevas conclusiones legales.

## Ejecución

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Se descubre la carpeta `corrida_*` más reciente junto a la aplicación que contenga `03_directores_con_sexo.csv` y `05_resumen_final_v3.csv`. Se admite seleccionar otra con `streamlit run app.py -- --run-dir RUTA`.

## Arquitectura y UTF-8

Se conserva el modelo de empresas, personas, mandatos, membresías actuales, conexiones, diversidad y evaluación regulatoria en `data_model.py`. Las observaciones originales permanecen en mandatos; las métricas utilizan una membresía por persona y entidad y el nombramiento más reciente. Los controles internos de calidad permanecen fuera de las vistas públicas.

Los CSV conservan nombres, columnas y contenido. La lectura exige UTF-8 con o sin BOM y rechaza bytes inválidos. Código y documentación usan UTF-8; `.editorconfig` fija esa codificación. La búsqueda ignora tildes solamente al comparar y conserva los nombres mostrados.

## Privacidad pendiente en las fuentes versionadas

La interfaz no muestra RUT personales, claves privadas ni clasificación individual de sexo. El repositorio, sin embargo, no está anonimizado.

`corrida_20260911_v3_2/03_directores_con_sexo.csv` contiene RUT personales en sus 2.162 filas y una columna `identidad_director`. Los otros cinco CSV revisados no incluyen columnas de identificación personal. No se modificaron ni eliminaron fuentes.

Antes de distribuir los insumos debe resolverse su separación de identificadores privados conservando las relaciones. Si ya se publicaron, también debe revisarse el historial de Git: retirar un archivo de la versión actual no elimina versiones anteriores.

## SQLite local

```bash
python scripts/build_database.py --output data/directorios_cmf.sqlite
```

La base conserva las tablas e índices existentes e incluye una correspondencia privada de identidad. No debe publicarse. Los archivos SQLite se excluyen de Git.

## Validación

```bash
python -m pip install pytest
python -m pytest -q
python -m compileall -q app.py data_model.py scripts tests
```

Pruebas de navegación, privacidad, mensajes públicos, UTF-8 estricto, búsqueda literal, entidades sin directorio e invariantes relacionales. No se añadieron dependencias de ejecución. Streamlit instalado: 1.63.0. Se mantiene una alternativa para parámetros de ancho anteriores; no se ejecutó una matriz completa de versiones.
