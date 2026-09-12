# Segunda fase: privacidad y publicación

## Arquitectura resultante

```text
Fuentes CMF
  → private_data/corrida_20260911_v3_2/ (originales locales)
  → scripts/private_model.py (resolución privada)
  ↔ private_data/person_ids.json (correspondencia UUID persistente)
  → scripts/build_public_snapshot.py (selección explícita y validación)
  → data/public/ (siete tablas JSON y manifiesto)
  → data_model.py → app.py / Streamlit
```

El despliegue solo necesita `app.py`, `data_model.py`, `requirements.txt` y `data/public/`. No necesita scripts locales, RUT personales, SQLite, secretos ni tablas de correspondencia. El parámetro `--public-dir` selecciona otra edición sanitizada; `--run-dir` permanece como alias público, sin activar el lector privado.

Tablas publicadas: `companies.json`, `people.json`, `current.json`, `interlocks.json`, `network_metrics.json`, `diversity.json`, `law.json`; `manifest.json` identifica la edición y versión del contrato. Solo se exportan columnas enumeradas en `PUBLIC_COLUMNS`. Se conservan los agregados existentes, sin nuevas métricas ni análisis. Sexo y confianza individuales, notas de clasificación, mandatos históricos y controles internos no se publican.

Los identificadores de empresa y los parámetros empresariales de los enlaces CMF son públicos. Las URLs se reconstruyen para el listado de directorios, descartando parámetros libres. El validador rechaza columnas adicionales, patrones de RUT en campos de texto e identificadores privados en URLs. No se publica el directorio fuente ni metadatos de rutas locales.

## Identidad y límite de la fuente

Los UUID aleatorios no derivan del RUT. Se guardan localmente y se reutilizan aunque cambie el orden, el nombre o se incorporen personas. No se usa un hash enumerable. La correspondencia debe respaldarse privadamente; una actualización falla si existe un snapshot pero falta ese registro. Generación de snapshots: un único proceso a la vez.

La fuente tiene 2.162 filas: 1.841 con RUT individual, correspondientes a 1.382 identidades, y 321 con `0-E` o `0-E (Extranjero)`. El marcador extranjero no identifica una persona. Tampoco sus antiguas claves `NAME:` prueban identidad entre entidades.

Se preserva una identidad única entre empresas para todos los RUT conocidos. Las 321 observaciones extranjeras quedan separadas por su contexto de origen, sin fusionarse por nombre. Resultado: 1.703 identidades públicas, 2.162 membresías, 357 entidades y 459 pares conectados. El conteo puede sobreestimar personas únicas y subestimar conexiones; la metodología lo explica. Resolver completamente esas personas exige evidencia adicional que los archivos actuales no aportan. No se inventaron correspondencias.

Se admite una tabla privada `identity_resolutions.json`, con identidad verificada y evidencia, para resolver posteriormente esos casos. No forma parte del snapshot. Una corrección de identidad puede sustituir IDs antes no vinculados. Los datos publicados siguen incluyendo nombres y afiliaciones: son datos sanitizados de identificadores privados, no personas anónimas.

## Archivos creados y modificados

- Creados: ocho archivos en `data/public/`, `scripts/private_model.py`, `scripts/build_public_snapshot.py`, `scripts/audit_tracked_privacy.py`, `tests/test_public_privacy.py` y este informe.
- Modificados: `app.py`, `data_model.py`, `scripts/build_database.py`, `.gitignore`, `README.md`, `DEPLOY_WINDOWS.md` y los dos archivos de tests existentes para usar el lector correspondiente.
- Trasladados intactos: los seis CSV de `corrida_20260911_v3_2/` a `private_data/corrida_20260911_v3_2/`. Git muestra eliminaciones pendientes en sus rutas antiguas. Las copias privadas y el registro de IDs están ignorados.

## Inventario sensible en Git

Auditoría del índice actual, sin imprimir identificadores: `scripts/audit_tracked_privacy.py`. Único archivo con RUT personales reales:

`corrida_20260911_v3_2/03_directores_con_sexo.csv`

Incluye `rut_persona` y `identidad_director`, además de nombres y clasificación estimada individual. Contiene 3.682 apariciones de RUT reales entre ambas columnas y las 321 filas con marcadores extranjeros. Las claves antiguas resuelven 1.660 identidades, utilizando nombres para los extranjeros, criterio que esta fase deja de asumir.

Los otros cinco CSV rastreados no tienen columnas de RUT personal ni coincidencias con los RUT individuales de la fuente: `05_resumen_final_v3.csv`, `09_discordancias_registro_vs_reporte.csv`, `10_discordancias_prioritarias.csv`, `12_entidades_sin_composicion_nominal.csv` y `AUDITORIA_checks.csv`. Sus RUT de empresa se distinguen expresamente. Los tests contienen identificadores ficticios de prueba; el código menciona nombres de columnas privadas, sin contener registros personales reales.

El archivo sensible sigue en el índice y el historial: esta fase no modifica ninguno. Mover archivos e ignorarlos no elimina los blobs existentes. La auditoría no constituye una revisión de todos los commits, ramas, etiquetas o copias externas.

## Limpieza recomendada, no ejecutada

1. Respaldar fuentes y correspondencias fuera de cualquier repositorio público; revisar y confirmar primero el cambio sanitizado.
2. En una copia nueva y aislada, inventariar todas las referencias y nombres históricos del CSV, buscando también exportaciones o correspondencias privadas.
3. Usar `git filter-repo --sensitive-data-removal --invert-paths` con rutas explícitas para eliminar el CSV sensible y cualquier copia histórica identificada. No limitarse a borrar la última versión. No ejecutar el ejemplo sin completar el inventario.
4. Auditar los objetos y referencias resultantes, ejecutar las pruebas y revisar un checkout limpio. Coordinar después la sustitución del remoto y la renovación de clones; revisar forks, artefactos y referencias de PR/cachés según el alojamiento.

Procedimiento basado en la [documentación de git-filter-repo](https://github.com/newren/git-filter-repo/blob/main/Documentation/git-filter-repo.txt) y la [guía de GitHub para datos sensibles](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository). No se ha hecho commit, push, force-push ni reescritura del historial.

## Revisión de aplicación y validación

- Tests existentes y nuevos: **36 aprobados**. Incluyen siete secciones, UTF-8 estricto, filtros/búsqueda literal, entidades sin directorio, invariantes, SQLite local, rechazo de columnas privadas, RUT con/sin puntos y guion, URLs contaminadas, estabilidad de IDs, homónimos y marcadores extranjeros.
- Prueba de paquete aislado: genera el snapshot, elimina sus fuentes y correspondencias temporales y recorre las siete secciones con AppTest, sin errores.
- Auditoría cruzada real: cada RUT conocido mantiene todas sus empresas bajo un ID; no se detectan esos RUT en los valores del snapshot.
- Compilación Python y `git diff --check`: correctos; Git solo informa de su conversión habitual LF/CRLF.
- Streamlit inicia en `http://localhost:8501`; `/_stcore/health` responde `ok`.
- Ajustes puntuales de interfaz: altura de tablas adaptada a sus filas, etiquetas de métricas con salto de línea, explicación de entidades conectadas y opciones de homónimos distinguibles mediante una referencia opaca corta; sus afiliaciones se consultan en la ficha. No se rediseñó la aplicación.

**Límite visual:** se intentó conectar Browser y la lista de navegadores disponibles estaba vacía. Las siete secciones se verificaron funcionalmente, pero no se inspeccionaron capturas de escritorio. Quedan por confirmar visualmente anchos, truncamientos, solapamientos y espaciado real; las pruebas de interacción no sustituyen esa inspección.
