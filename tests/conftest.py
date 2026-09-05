"""
Condiciones que valen para TODA la batería de pruebas.

Dos garantías, y las dos son de portabilidad: lo que se comprueba aquí tiene que
comprobarse igual en el equipo de quien desarrolla, en la integración continua y
en el build de Colab que publica.

1. **Ninguna prueba puede abrir una conexión real con Snowflake.** El aplicativo
   lee un `.env` de la raíz cuando se ejecuta en local (así se desarrolla), y
   `SnowflakeService` lo carga al construirse. Sin esto, en un equipo con
   credenciales reales la batería intentaría conectarse —y hasta llamar a Cortex,
   gastando créditos— mientras que en Colab o en la nube pasaría de largo: el
   mismo código con dos comportamientos. Se anula la carga del `.env` **antes**
   de importar el backend y se vacían las variables `SF_*`.
2. **Modo demostración por defecto**, que es lo que la integración continua fija
   y lo que las pruebas asumen.

pytest importa este archivo antes que cualquier módulo de prueba, así que el
parche llega a tiempo.
"""
from __future__ import annotations

import os

import dotenv

# El backend hace `from dotenv import load_dotenv` al importarse: sustituir aquí
# la función del paquete hace que reciba ya la versión inerte.
dotenv.load_dotenv = lambda *args, **kwargs: False  # type: ignore[assignment]

#: Variables de conexión que se neutralizan (cadena vacía = «falta la variable»).
VARIABLES_SNOWFLAKE = (
    "SF_ACCOUNT", "SF_USER", "SF_DATABASE", "SF_SCHEMA", "SF_WAREHOUSE", "SF_ROLE",
    "SF_PRIVATE_KEY_B64_1", "SF_PRIVATE_KEY_B64_2",
    "SF_PRIVATE_KEY_PATH_1", "SF_PRIVATE_KEY_PATH_2",
    "SF_PRIVATE_KEY_PASSPHRASE_1", "SF_PRIVATE_KEY_PASSPHRASE_2",
    "SF_HOST",
)
for _variable in VARIABLES_SNOWFLAKE:
    os.environ[_variable] = ""

os.environ.setdefault("APP_DEMO_MODE", "true")
os.environ.setdefault("APP_ENV", "development")
