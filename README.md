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

Streamlit lee exclusivamente `data/public/`. Para otra edición pública: `streamlit run app.py -- --public-dir RUTA`. No descubre ni importa fuentes privadas. Basta desplegar `app.py`, `data_model.py`, `requirements.txt` y `data/public/`.

## Arquitectura y UTF-8

Flujo: fuentes CMF → resolución privada local → tablas sanitizadas → Streamlit. `scripts/private_model.py` conserva mandatos y controles locales. `data_model.py` solo carga y valida el contrato público. No se añadieron métricas ni funcionalidades analíticas.

Las fuentes originales se conservan en `private_data/corrida_20260911_v3_2/`. El snapshot usa JSON tabular con tipos explícitos, UTF-8 y una lista cerrada de columnas; incluye empresas, personas, membresías, conexiones y agregados de diversidad y ley. No contiene RUT personales, correspondencias ni clasificación individual de sexo. Conserva el RUT público de las empresas y enlaces CMF construidos únicamente para ellas. La búsqueda ignora tildes al comparar y conserva los nombres mostrados.

## Generación local e identidad

```powershell
py scripts/build_public_snapshot.py --source private_data/corrida_20260911_v3_2
```

`private_data/person_ids.json` asigna UUID aleatorios persistentes; no son hashes ni cifras derivadas del RUT. Respalda esta correspondencia de forma privada y ejecuta un solo generador a la vez. No regenerarla: perderla rompe la estabilidad entre ediciones. El generador rechaza actualizar un snapshot existente si falta el registro. Nunca publicar `private_data/` ni sus copias. Los nombres y afiliaciones siguen siendo datos personales públicos: la separación elimina los identificadores privados, no vuelve anónimas a las personas nombradas.

La fuente contiene 1.841 filas con RUT individual y 321 con marcadores extranjeros `0-E`. Los RUT identifican 1.382 personas. Los extranjeros se conservan como 321 observaciones separadas; no se unen exclusivamente por nombre. El snapshot tiene 1.703 identidades públicas y 2.162 membresías. No debe interpretarse 1.703 como un censo de personas únicas verificado: puede sobreestimar personas y subestimar conexiones.

La revisión documental puede resolver esos casos en `private_data/identity_resolutions.json`: un objeto cuyas claves son las claves privadas `UNRESOLVED:…`, y cuyos valores contienen `identity` (`RUT:<identificador>` o `LOCAL:<uuid hexadecimal>`) y `evidence` (referencia de verificación). Esta tabla tampoco se publica. Una resolución posterior puede cambiar el ID de una observación antes no vinculada; debe revisarse como corrección de identidad.

## Git y publicación

La carpeta de fuentes se trasladó fuera del árbol público y está ignorada. Las eliminaciones de sus rutas anteriores están pendientes de commit. El índice y el historial aún contienen `corrida_20260911_v3_2/03_directores_con_sexo.csv`: mover el archivo y añadir `.gitignore` no los limpia. No se hizo push, commit ni reescritura.

Consulta [el informe de segunda fase](PHASE2_REPORT.md) para el inventario exacto, la estrategia de limpieza y las limitaciones de revisión visual. Publicar únicamente el paquete sanitizado no equivale a sanear un repositorio que conserva versiones privadas.

## SQLite local

```bash
python scripts/build_database.py --output private_data/directorios_cmf.sqlite
```

La base conserva las tablas e índices existentes e incluye una correspondencia privada de identidad. No debe publicarse. Los archivos SQLite se excluyen de Git.

## Validación

```bash
python -m pip install pytest
python -m pytest -q
python -m compileall -q app.py data_model.py scripts tests
```

Pruebas de las siete secciones, privacidad del contrato y contenidos, identidad estable, homónimos, extranjeros sin identificador, UTF-8, búsqueda literal, ausencia de directorio e invariantes. Incluyen un paquete temporal que funciona después de eliminar sus fuentes privadas. La auditoría contra fuentes reales y SQLite es local opcional; el resto funciona en un checkout sanitizado. No se añadieron dependencias de ejecución.
