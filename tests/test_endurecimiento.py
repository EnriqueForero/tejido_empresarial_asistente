"""
Pruebas de endurecimiento: cada una fija una vía cerrada tras una revisión adversaria.

Cada una fija una vía por la que la SQL propuesta por un modelo escapaba de las
guardas, un falso positivo que degradaba una respuesta correcta, o un detalle
del registro y de las descargas que no coincidía con lo que el archivo declara.
"""
from __future__ import annotations

import os

os.environ["APP_DEMO_MODE"] = "true"
os.environ["APP_ENV"] = "development"

from pathlib import Path  # noqa: E402

#: Raíz del proyecto, para las pruebas que leen archivos del repositorio.
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

import io  # noqa: E402
import threading  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.config import ALLOWED_SCHEMAS  # noqa: E402
from backend.ia.guardas import ErrorDeLectura, leer_fichas, validar_sql, verificar_cifras  # noqa: E402
from dobles import AnalystFalso, ServicioFalso, correr  # noqa: E402

TABLA = "APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_COMPLETO_BASE_MUNICIPIOS_P"
VISTA = "APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_SEGMENTACION"
AJENA = "APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.EVENTOS"


def _rechaza(sql: str, fragmento: str = "") -> str:
    veredicto = validar_sql(sql, ALLOWED_SCHEMAS, 5000)
    assert veredicto.ok is False, f"se aceptó: {sql}"
    assert fragmento.lower() in veredicto.motivo.lower(), veredicto.motivo
    return veredicto.motivo


def _acepta(sql: str) -> str:
    veredicto = validar_sql(sql, ALLOWED_SCHEMAS, 5000)
    assert veredicto.ok is True, veredicto.motivo
    return veredicto.sql


# ── El lector de fichas conoce las tres formas de comentario y las dos de cadena ──


def test_un_comentario_de_dos_barras_no_puede_esconder_otra_tabla() -> None:
    """`//` es comentario en Snowflake: si el validador no lo sabe, una comilla dentro
    desplaza los límites del literal y el segundo FROM queda invisible."""
    _rechaza(
        f"SELECT NIT FROM {TABLA} WHERE NIT = '1' // '\nUNION ALL SELECT SESION FROM {AJENA} WHERE SESION = '1' // '",
        "no autorizado",
    )


def test_un_comentario_de_dos_barras_no_puede_fingir_el_tope_de_filas() -> None:
    sql = _acepta(f"SELECT NIT FROM {TABLA} // LIMIT 5")
    assert sql.rstrip().endswith("LIMIT 5000")  # el LIMIT comentado no cuenta


def test_una_cadena_entre_dobles_dolares_no_puede_esconder_otra_tabla() -> None:
    _rechaza(
        f"SELECT NIT FROM {TABLA} WHERE NIT = $$ ' $$ UNION ALL SELECT SESION FROM {AJENA} WHERE SESION = $$ ' $$",
        "no autorizado",
    )


def test_una_cadena_o_un_comentario_sin_cerrar_se_rechazan() -> None:
    with pytest.raises(ErrorDeLectura):
        leer_fichas("SELECT 'abierta FROM T")
    _rechaza("SELECT 'abierta FROM T", "sin cerrar")
    _rechaza(f"SELECT NIT FROM {TABLA} /* sin cerrar", "sin cerrar")


# ── Orígenes de datos: nada fuera de los esquemas permitidos ──────────────


def test_un_stage_no_es_un_origen_de_datos_valido() -> None:
    _rechaza("SELECT $1 FROM @~", "stages")
    _rechaza("SELECT $1 FROM @MI_STAGE", "stages")


def test_un_join_entre_parentesis_no_esconde_una_tabla_ajena() -> None:
    """`FROM t1 JOIN (t2 JOIN t3 ON …) ON …` es sintaxis documentada: t2 también es un origen."""
    _rechaza(
        f"SELECT * FROM {TABLA} A LEFT OUTER JOIN (SEGUIMIENTO.EVENTOS E RIGHT OUTER JOIN {TABLA} B ON B.NIT = E.SESION)"
        " ON A.NIT = E.SESION",
        "no autorizado",
    )


def test_una_coma_despues_de_on_sigue_introduciendo_tablas() -> None:
    _rechaza(f"SELECT * FROM {TABLA} A JOIN {TABLA} B ON A.NIT = B.NIT, SEGUIMIENTO.EVENTOS E", "no autorizado")


def test_un_literal_no_puede_dar_de_alta_una_cte_falsa() -> None:
    _rechaza("SELECT * FROM EVENTOS WHERE X = 'WITH EVENTOS AS ('", "sin calificar")


def test_una_cte_con_lista_de_columnas_se_reconoce() -> None:
    _acepta(f"WITH t (a) AS (SELECT NIT FROM {TABLA}) SELECT * FROM t")


# ── El tope de filas se impone también con FETCH ──────────────────────────


def test_fetch_first_tambien_se_acota() -> None:
    sql = _acepta(f"SELECT NIT FROM {TABLA} ORDER BY NIT FETCH FIRST 999999 ROWS ONLY")
    assert "999999" not in sql and "5000" in sql
    # Un FETCH razonable se respeta tal cual.
    assert "FETCH FIRST 50 ROWS ONLY" in _acepta(f"SELECT NIT FROM {TABLA} ORDER BY NIT FETCH FIRST 50 ROWS ONLY")


# ── Cifras: ni falsos positivos por el guion ni años inventados ───────────


def test_un_rango_de_anos_o_una_raya_no_inventan_una_cifra_huerfana() -> None:
    filas = [["Antioquia", 231544], ["Bogotá, D.C.", 402118]]
    assert verificar_cifras("Durante 2021-2025 Bogotá encabeza con 402.118 empresas.", filas, 2).ok is True
    assert verificar_cifras("Antioquia -231.544 empresas- lidera.", filas, 2).ok is True


def test_una_cifra_con_separador_de_miles_no_pasa_por_ano() -> None:
    """«1.950 empresas» no es un año: en español un año se escribe sin punto."""
    filas = [["Caldas", 45912]]
    assert verificar_cifras("Caldas tiene 1.950 empresas.", filas, 1).ok is False
    assert verificar_cifras("Caldas registra 2.024 exportadoras.", filas, 1).ok is False
    assert verificar_cifras("En 2024 Caldas sumó 45.912 empresas.", filas, 1).ok is True


# ── Orquestador: contexto de la corrección y registro de la detención ─────


def test_la_correccion_recibe_la_pregunta_antes_de_la_sql_que_fallo() -> None:
    analyst = AnalystFalso(sql=f"SELECT MAL FROM {TABLA}")
    correr(ServicioFalso(error="invalid identifier"), analyst)
    assert len(analyst.historiales) == 2
    papeles = [turno["role"] for turno in analyst.historiales[1]]
    assert papeles == ["user", "analyst"], papeles  # preguntar() añade el 'user' de la corrección
    assert analyst.historiales[1][0]["content"][0]["text"].startswith("¿Cuántas empresas")


def test_una_detencion_tras_fallo_de_sql_conserva_el_tiempo_y_el_intento() -> None:
    cancelado = threading.Event()
    cancelado.set()
    _, telemetria, _ = correr(
        ServicioFalso(error="invalid identifier"), AnalystFalso(sql=f"SELECT MAL FROM {TABLA}"), cancelado=cancelado
    )
    registro = telemetria.registros[0]
    assert registro["estado"] == "detenida" and registro["etapa_fallo"] == "consultando"
    assert registro["intentos_sql"] == 1  # la consulta sí se ejecutó una vez
    assert 0 <= registro["ms_consulta"] <= registro["ms_total"]


def test_un_resumen_de_respaldo_conserva_su_causa_y_no_se_revisa_dos_veces() -> None:
    """Verificar las cifras del resumen determinista sólo podría borrar la causa real."""
    servicio = ServicioFalso(redaccion=RuntimeError("Insufficient privileges to use model"))
    eventos, telemetria, _ = correr(servicio, AnalystFalso(sql=f"SELECT DEPARTAMENTO_EMP FROM {TABLA}"))
    meta = eventos[-1]["meta"]
    assert meta["degradado"] is True
    assert meta["motivo_degradacion"] == "redaccion_fallo"  # no lo pisa «cifras_sin_respaldo»
    assert meta["cifras_verificadas"] is True
    assert telemetria.registros[-1]["motivo_degradacion"] == "redaccion_fallo"


# ── La redacción no hace esperar cuando lleva rato fallando ───────────────


def test_tras_varios_fallos_seguidos_la_redaccion_deja_de_llamarse() -> None:
    """Un fallo cuesta el tiempo completo de la llamada (~20 s en producción) y su
    causa casi nunca es pasajera: tras tres seguidos se deja de llamar."""
    from backend.ia.redactor import Interruptor, redactar

    reloj = [1000.0]
    interruptor = Interruptor(fallos_para_pausa=3, pausa=600, reloj=lambda: reloj[0])
    llamadas: list[str] = []

    def sesion(consulta: str, parametros: list) -> list:
        llamadas.append(consulta)
        raise RuntimeError("100357 (P0000): Insufficient privileges to use model")

    def pedir():
        return redactar(sesion, "¿Cuántas?", ["A"], [["x"]], 1, False, "m", "id", interruptor)

    for _ in range(3):
        assert pedir().motivo == "redaccion_fallo"
    assert len(llamadas) == 3

    # La cuarta no llega a Snowflake: responde de inmediato y explica por qué.
    pausada = pedir()
    assert len(llamadas) == 3
    assert pausada.motivo == "redaccion_pausada"
    assert "privileges" in pausada.error and "pausa" in pausada.error
    assert "x" in pausada.texto  # el resumen con los datos sigue saliendo

    # Pasada la pausa se vuelve a intentar; un acierto reinicia la cuenta.
    reloj[0] += 601
    llamadas.clear()

    def sesion_buena(consulta: str, parametros: list) -> list:
        llamadas.append(consulta)
        return [["Antioquia concentra 5 empresas."]]

    buena = redactar(sesion_buena, "¿Cuántas?", ["A"], [["x"]], 1, False, "m", "id", interruptor)
    assert buena.degradado is False and len(llamadas) == 1
    assert interruptor.fallos_seguidos == 0


def test_la_causa_del_fallo_llega_a_la_pantalla() -> None:
    """Quien mira la respuesta no debería tener que abrir /estado para saber qué pasó."""
    servicio = ServicioFalso(redaccion=RuntimeError("100357 (P0000): Insufficient privileges to use model 'x'"))
    from backend.ia.redactor import INTERRUPTOR

    INTERRUPTOR.reiniciar()
    eventos, _, _ = correr(servicio, AnalystFalso(sql=f"SELECT DEPARTAMENTO_EMP FROM {TABLA}"))
    INTERRUPTOR.reiniciar()
    meta = eventos[-1]["meta"]
    assert meta["motivo_degradacion"] == "redaccion_fallo"
    assert "Insufficient privileges" in meta["detalle_degradacion"]
    assert len(meta["detalle_degradacion"]) <= 300


# ── Un servicio publicado no puede estar en modo desarrollo sin avisar ────


def _peticion(anfitrion: str):
    """Petición mínima con la cabecera Host, que es lo único que mira el paso."""

    class _Peticion:
        headers = {"host": anfitrion}

    return _Peticion()


def test_el_diagnostico_avisa_si_el_servicio_publicado_corre_en_modo_desarrollo(monkeypatch) -> None:
    """Comprobado en producción: /api/docs respondía 200 en el dominio de Railway."""
    from backend.routers import salud

    monkeypatch.setattr(salud, "APP_ENV", "development")
    monkeypatch.setattr(salud, "ACCESS_CONTROL_ACTIVE", False)
    monkeypatch.setattr(salud, "DIAG_TOKEN", "")

    paso = salud.paso_exposicion(_peticion("tejidoempresarialasistente-production.up.railway.app"))
    assert paso["ok"] is False
    assert "/api/docs" in paso["detalle"]["que_queda_publico"]
    assert "APP_ENV" in paso["error"]
    assert "APP_ENV" in salud.sugerencia(paso)

    # En un portátil, correr en modo desarrollo es lo normal: no hay nada que avisar.
    assert salud.paso_exposicion(_peticion("localhost:8000"))["ok"] is True
    assert salud.paso_exposicion(None)["ok"] is True


def test_el_diagnostico_no_se_queja_de_un_servicio_bien_configurado(monkeypatch) -> None:
    from backend.routers import salud

    monkeypatch.setattr(salud, "APP_ENV", "production")
    monkeypatch.setattr(salud, "ACCESS_CONTROL_ACTIVE", False)
    assert salud.paso_exposicion(_peticion("tejido.up.railway.app"))["ok"] is True

    monkeypatch.setattr(salud, "APP_ENV", "development")
    monkeypatch.setattr(salud, "ACCESS_CONTROL_ACTIVE", True)
    assert salud.paso_exposicion(_peticion("tejido.up.railway.app"))["ok"] is True


def test_en_un_dominio_publico_el_diagnostico_exige_credencial(monkeypatch) -> None:
    """Un aviso no basta: mientras nadie lo lea, el diagnóstico sigue abierto.

    Comprobado en producción: con `APP_ENV` distinto de «production», un GET
    anónimo abría once consultas al warehouse, cerraba la sesión compartida y,
    con `?cortex=1`, gastaba créditos de IA.
    """
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.routers import salud

    monkeypatch.setattr(salud, "APP_ENV", "development")
    monkeypatch.setattr(salud, "ACCESS_CONTROL_ACTIVE", False)
    monkeypatch.setattr(salud, "DIAG_TOKEN", "")

    with TestClient(app) as cliente:
        # Desde el dominio publicado: cerrado, con instrucciones.
        respuesta = cliente.get("/api/diagnostico", headers={"host": "tejido.up.railway.app"})
        assert respuesta.status_code == 403
        detalle = respuesta.json()["detail"]
        assert "APP_BASIC_USER" in detalle and "APP_DIAG_TOKEN" in detalle
        # Y también la prueba que gasta créditos.
        assert cliente.get("/api/diagnostico?cortex=1", headers={"host": "tejido.up.railway.app"}).status_code == 403
        # Desde el equipo de desarrollo, todo sigue igual que siempre.
        assert cliente.get("/api/diagnostico").status_code == 200

    monkeypatch.setattr(salud, "DIAG_TOKEN", "un-token-largo")
    with TestClient(app) as cliente:
        abierto = cliente.get("/api/diagnostico", headers={"host": "tejido.up.railway.app", "X-Diag-Token": "un-token-largo"})
        assert abierto.status_code == 200


def test_la_prueba_de_cortex_no_se_puede_pedir_en_bucle() -> None:
    """Es el único camino del código que gasta créditos de IA sin preguntar nada."""
    from backend.routers import salud

    salud._ultima_prueba_cortex.update({"cuando": 0.0, "paso": None})
    paso = {"paso": "cortex_complete", "ok": True, "detalle": {"modelo": "claude-haiku-4-5"}, "segundos": 1.0}

    assert salud._prueba_cortex_reciente(1000.0) is None  # nada guardado todavía
    salud._guardar_prueba_cortex(paso, 1000.0)

    reciente = salud._prueba_cortex_reciente(1060.0)
    assert reciente is not None and reciente["detalle"]["reutilizado"] is True
    assert "hace 60 s" in reciente["detalle"]["nota"]
    assert reciente["detalle"]["modelo"] == "claude-haiku-4-5"

    # Pasado el plazo vuelve a probarse de verdad.
    assert salud._prueba_cortex_reciente(1000.0 + salud.PAUSA_ENTRE_PRUEBAS_CORTEX + 1) is None
    salud._ultima_prueba_cortex.update({"cuando": 0.0, "paso": None})


# ── La respuesta no espera al párrafo ─────────────────────────────────────


def test_el_resultado_ya_trae_una_respuesta_completa_sin_esperar_a_la_ia() -> None:
    """Medido en producción: la tabla a los 7,8 s y el texto a los 29,1 s."""
    from dobles import TABLA, AnalystFalso, ServicioFalso, correr

    servicio = ServicioFalso(redaccion=RuntimeError("unknown model 'claude-3-5-sonnet'"))
    eventos, _, _ = correr(servicio, AnalystFalso(sql=f"SELECT departamento_emp, empresas FROM {TABLA} LIMIT 10"))

    resultado = next(e for e in eventos if e["tipo"] == "resultado")
    final = next(e for e in eventos if e["tipo"] == "final")
    # El resultado ya trae un texto legible construido con la tabla…
    assert resultado["texto_provisional"].startswith("La consulta devolvió")
    assert "231.544" in resultado["texto_provisional"]
    # …y llega antes que el final, que es donde estaba el texto hasta ahora.
    assert eventos.index(resultado) < eventos.index(final)
    # Cuando la IA falla, el texto definitivo es ese mismo: nada cambia en pantalla.
    assert final["texto"] == resultado["texto_provisional"]


def test_cuando_la_ia_responde_su_texto_sustituye_al_provisional() -> None:
    from dobles import TABLA, AnalystFalso, ServicioFalso, correr

    servicio = ServicioFalso(redaccion="Antioquia concentra 231.544 empresas registradas.")
    eventos, _, _ = correr(servicio, AnalystFalso(sql=f"SELECT departamento_emp, empresas FROM {TABLA} LIMIT 10"))
    resultado = next(e for e in eventos if e["tipo"] == "resultado")
    final = next(e for e in eventos if e["tipo"] == "final")
    assert final["texto"] == "Antioquia concentra 231.544 empresas registradas."
    assert final["texto"] != resultado["texto_provisional"]
    assert final["meta"]["degradado"] is False


# ── El gasto del aplicativo se puede separar del resto de la cuenta ──────


def test_cada_consulta_del_aplicativo_va_etiquetada_en_snowflake(monkeypatch) -> None:
    """Sin QUERY_TAG como parámetro de sesión, el costo sólo se puede adivinar."""
    from backend.database import ETIQUETA_CONSULTAS, SnowflakeService

    for variable in ("SF_ACCOUNT", "SF_USER", "SF_DATABASE", "SF_SCHEMA", "SF_WAREHOUSE", "SF_ROLE"):
        monkeypatch.setenv(variable, "valor-de-prueba")
    servicio = SnowflakeService()
    monkeypatch.setattr(servicio, "_private_key", lambda numero: (b"llave-de-prueba", "SF_PRIVATE_KEY_B64_1"))
    configuracion = servicio._session_config(1)
    assert configuracion["session_parameters"]["QUERY_TAG"] == ETIQUETA_CONSULTAS
    assert configuracion["query_tag"] == ETIQUETA_CONSULTAS
    # Y las consultas de costo la usan, o el propietario no puede separarlo.
    metricas = (RAIZ_PROYECTO / "docs" / "METRICAS.md").read_text(encoding="utf-8")
    assert "QUERY_TAG" in metricas


def test_una_peticion_sin_declarar_su_tamano_no_esquiva_el_tope() -> None:
    """El tope miraba sólo la cabecera: una petición troceada pasaba de largo."""
    from backend.main import app

    def por_trozos():
        yield b'{"pregunta": '
        yield b'"hola"}'

    with TestClient(app) as cliente:
        # Un cuerpo por trozos no lleva Content-Length: httpx usa chunked.
        respuesta = cliente.post(
            "/api/ia/preguntar", content=por_trozos(), headers={"content-type": "application/json"}
        )
        assert respuesta.status_code == 411, respuesta.status_code
        assert "Content-Length" in respuesta.json()["detail"]


# ── Contratos que se rompen en silencio si nadie los sujeta ──────────────


def test_cada_motivo_de_degradacion_esta_explicado_donde_alguien_lo_va_a_leer() -> None:
    """Un motivo sin explicación deja el «¿Por qué?» en blanco y la métrica sin leyenda.

    Pasó con `respuesta_ilegible`, que se añadió en 3.5.1 y no llegó ni a la
    interfaz ni al contrato ni a la documentación.
    """
    from backend.ia.redactor import MOTIVOS_DEGRADACION

    lugares = {
        "frontend/src/paginas/Asistente.tsx": "la explicación que se abre en «¿Por qué?»",
        "frontend/src/tipos.ts": "el contrato del navegador",
        "CLAUDE.md": "el contrato SSE",
        "docs/METRICAS.md": "la leyenda de la tabla de métricas",
        "snowflake/03_telemetria_asistente.sql": "el comentario de la columna MOTIVO_DEGRADACION",
    }
    faltan = [
        f"«{motivo}» falta en {ruta} ({para_que})"
        for ruta, para_que in lugares.items()
        for motivo in MOTIVOS_DEGRADACION
        if motivo not in (RAIZ_PROYECTO / ruta).read_text(encoding="utf-8")
    ]
    assert not faltan, "Motivos sin explicar:\n  " + "\n  ".join(faltan)


def test_la_telemetria_escribe_exactamente_las_columnas_que_declara_el_ddl() -> None:
    """Si divergen, el INSERT falla y la telemetría se descarta sin avisar a nadie."""
    import re

    from backend.ia.orquestador import Orquestador
    from backend.ia.telemetria import COLUMNAS_CONSULTA, COLUMNAS_DESCARGA, _TOPES

    ddl = (RAIZ_PROYECTO / "snowflake" / "03_telemetria_asistente.sql").read_text(encoding="utf-8")

    def columnas_del_ddl(tabla: str) -> dict[str, int | None]:
        cuerpo = re.search(rf"CREATE TABLE IF NOT EXISTS {tabla} \((.*?)\n\)", ddl, re.S).group(1)
        declaradas: dict[str, int | None] = {}
        for nombre, tipo in re.findall(r"^\s{4}([A-Z_]+)\s+(\S+)", cuerpo, re.M):
            largo = re.match(r"VARCHAR\((\d+)\)", tipo)
            declaradas[nombre] = int(largo.group(1)) if largo else None
        for nombre, largo in re.findall(rf"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS ([A-Z_]+) VARCHAR\((\d+)\)", ddl):
            declaradas[nombre] = int(largo)
        return declaradas

    consultas = columnas_del_ddl("ASISTENTE_CONSULTAS")
    descargas = columnas_del_ddl("ASISTENTE_DESCARGAS")

    assert not set(COLUMNAS_CONSULTA) - set(consultas), (
        "El aplicativo inserta columnas que el DDL no declara: "
        f"{sorted(set(COLUMNAS_CONSULTA) - set(consultas))}. Añádalas a snowflake/03_telemetria_asistente.sql "
        "y con un ALTER TABLE … ADD COLUMN IF NOT EXISTS, porque CREATE TABLE IF NOT EXISTS no las añade."
    )
    assert not set(COLUMNAS_DESCARGA) - set(descargas)

    # Los topes de longitud no pueden pasarse del VARCHAR: un texto más largo
    # aborta el INSERT y el registro se pierde.
    excesos = {
        columna: (tope, consultas[columna])
        for columna, tope in _TOPES.items()
        if columna in consultas and consultas[columna] is not None and tope > consultas[columna]
    }
    assert not excesos, f"Topes por encima del VARCHAR del DDL: {excesos}"

    # Y lo que el orquestador prepara es exactamente lo que se inserta.
    registro = Orquestador._registro_base("abc123abc123", "sesion", "¿Cuántas empresas hay?")
    assert {c.lower() for c in COLUMNAS_CONSULTA} == set(registro), (
        "El registro del orquestador y las columnas de la telemetría se han desincronizado: "
        f"sobran {set(registro) - {c.lower() for c in COLUMNAS_CONSULTA}}, "
        f"faltan {{c.lower() for c in COLUMNAS_CONSULTA}} - set(registro)"
    )


# ── El contacto sale sólo si la pregunta lo pide (D-03) ───────────────────


def _marco_con_contacto():
    import pandas as pd

    return pd.DataFrame(
        {
            "NIT": ["890926766", "800021308"],
            "RAZON_SOCIAL": ["BANACOL DE COLOMBIA S.A.S", "DRUMMOND LTD"],
            "EMAIL": ["a@banacol.com", "b@drummond.com"],
            "TELEFONO": ["3396262", "3444444"],
        }
    )


def test_un_listado_no_publica_correo_ni_telefono_si_nadie_los_pidio() -> None:
    """Visto en producción: cien empresas reales con correo y teléfono sin haberlos pedido."""
    from dobles import TABLA, AnalystFalso, ServicioFalso, correr

    sql = f"SELECT nit, razon_social, email, telefono FROM {TABLA} LIMIT 100"
    eventos, _, _ = correr(
        ServicioFalso(marco=_marco_con_contacto()),
        AnalystFalso(sql=sql),
        pregunta="Lístame las pymes de Agroalimentos en Antioquia que exportan, con NIT",
    )
    resultado = next(e for e in eventos if e["tipo"] == "resultado")
    assert resultado["columnas"] == ["NIT", "Razón social"]
    assert all(len(fila) == 2 for fila in resultado["filas"])
    # Y se dice, en vez de retirarlas en silencio: la SQL a la vista sí las nombra.
    assert "no pidió" in resultado["nota"] and "correo" in resultado["nota"].lower()


def test_un_listado_sí_trae_el_correo_cuando_la_pregunta_lo_pide() -> None:
    from dobles import TABLA, AnalystFalso, ServicioFalso, correr

    sql = f"SELECT nit, razon_social, email, telefono FROM {TABLA} LIMIT 100"
    for pregunta in (
        "Empresas medianas de Sistema Moda en Bogotá que aún no exportan, con NIT y correo",
        "Dame los datos para contactarlas",
        "Ficha de la empresa 890926766",
    ):
        eventos, _, _ = correr(ServicioFalso(marco=_marco_con_contacto()), AnalystFalso(sql=sql), pregunta=pregunta)
        resultado = next(e for e in eventos if e["tipo"] == "resultado")
        assert "Correo electrónico" in resultado["columnas"], pregunta
        assert resultado["nota"] == "", pregunta


def test_la_pregunta_que_pide_contacto_se_reconoce_con_y_sin_tildes() -> None:
    from backend.ia.forma import pide_contacto

    assert pide_contacto("con NIT y teléfono")
    assert pide_contacto("con NIT y telefono")
    assert pide_contacto("incluye la dirección y el representante legal")
    assert not pide_contacto("¿Cuántas empresas hay por departamento y tamaño?")
    assert not pide_contacto("Top 10 exportadoras de Antioquia por valor exportado")


# ── El diagnóstico de la redacción: decir cuál poner, no sólo «falla» ─────


def _sesion_que_falla(mensaje: str, exitos: tuple[str, ...] = ()) -> tuple[object, list[str]]:
    """Sesión falsa que sólo responde a los modelos de `exitos`; anota cada llamada."""
    llamadas: list[str] = []

    def sesion(sql: str, parametros: list[object] | None = None) -> list[list[object]]:
        modelo = str((parametros or [""])[0])
        forma = "opciones" if "PARSE_JSON" in sql else "simple"
        llamadas.append(f"{modelo}:{forma}")
        if modelo in exitos:
            return [["OK"]]
        raise RuntimeError(mensaje)

    return sesion, llamadas


def test_el_sondeo_dice_que_modelo_poner_cuando_el_configurado_no_existe() -> None:
    import pytest

    from backend.ia.redactor import sondear_complete

    sesion, llamadas = _sesion_que_falla(
        "100357 (P0000): unknown model 'claude-3-5-sonnet'", exitos=("llama3.1-8b",)
    )
    with pytest.raises(RuntimeError) as fallo:
        sondear_complete(sesion, "claude-3-5-sonnet", candidatos=("claude-haiku-4-5", "llama3.1-8b"))
    assert "SF_CORTEX_MODEL = llama3.1-8b" in str(fallo.value)
    # Un modelo que no existe no es un error de firma: cuesta UNA llamada, no dos.
    assert llamadas == ["claude-3-5-sonnet:opciones", "claude-haiku-4-5:opciones", "llama3.1-8b:opciones"]


def test_el_sondeo_nombra_las_tres_causas_cuando_ningun_modelo_responde() -> None:
    import pytest

    from backend.ia.redactor import sondear_complete

    sesion, _ = _sesion_que_falla("Insufficient privileges to operate on model")
    with pytest.raises(RuntimeError) as fallo:
        sondear_complete(sesion, "claude-haiku-4-5", candidatos=("llama3.1-8b",))
    texto = str(fallo.value)
    assert "CORTEX_USER" in texto and "CORTEX_ENABLED_CROSS_REGION" in texto
    assert "El asistente sigue funcionando" in texto


def test_el_sondeo_no_deja_al_usuario_esperando_minutos() -> None:
    """Cada llamada muerta cuesta ~20 s: el paso se corta y dice qué quedó sin probar."""
    import pytest

    from backend.ia.redactor import sondear_complete

    reloj = [0.0]
    sesion_base, llamadas = _sesion_que_falla("unknown model")

    def sesion(sql: str, parametros: list[object] | None = None) -> list[list[object]]:
        reloj[0] += 20.5
        return sesion_base(sql, parametros)

    with pytest.raises(RuntimeError) as fallo:
        sondear_complete(
            sesion,
            "claude-3-5-sonnet",
            candidatos=("a", "b", "c", "d", "e"),
            reloj=lambda: reloj[0],
            presupuesto=45.0,
        )
    assert "No dio tiempo a probar c, d, e" in str(fallo.value)
    assert len(llamadas) == 3  # el configurado y dos candidatos, no seis


# ── La gráfica y el Excel no pueden contradecir a la tabla ────────────────


def test_un_promedio_no_se_dibuja_redondeado_a_entero() -> None:
    """En producción la tabla decía 19,89 y la gráfica dibujaba «20»."""
    from backend.ia import graficos

    espec = graficos.sugerir(
        ["Promedio pobreza municipio", "¿La empresa ha exportado?"], [[19.891126311511194, "No"], [12.52, "Sí"]]
    )
    assert espec is not None and espec["formato"] in {"porcentaje", "decimal"}
    assert espec["series"][0]["valores"] == [19.891126311511194, 12.52]
    # Un conteo sigue siendo entero, y una cifra de exportaciones sigue en dólares.
    assert graficos.sugerir(["DEPARTAMENTO", "EMPRESAS"], [["Antioquia", 231544], ["Caldas", 45912]])["formato"] == "entero"
    assert graficos.sugerir(["SECTOR", "EXPO_2025"], [["Café", 1234.5], ["Banano", 987.6]])["formato"] == "usd"


def test_el_excel_del_asistente_distingue_dolares_de_pesos() -> None:
    from backend.ia.exportadores import _clase_numerica

    assert _clase_numerica("Total expo 5 anos USD") == "usd"
    assert _clase_numerica("Exportaciones totales de la empresa 2021 (FOB USD)") == "usd"
    assert _clase_numerica("total_expo_5_anos_usd") == "usd"
    assert _clase_numerica("Ingresos operacionales (COP)") == "cop"
    assert _clase_numerica("Empleados") == "numero"
    assert _clase_numerica("Promedio pobreza municipio") == "porcentaje"


def test_un_conteo_de_empresas_exportadoras_no_se_escribe_en_dolares() -> None:
    """Visto en producción: la gráfica decía «USD 3 k» sobre 3.340 empresas."""
    from backend.ia import graficos
    from backend.ia.forma import clase_de_cifra

    # «expo» dentro de «exportadoras» no son dólares: es un conteo de empresas.
    for conteo in ("NUMERO_EXPORTADORAS", "Numero exportadoras", "NUMERO_EXPORTADORAS_NME", "NUMERO_EMPRESAS"):
        assert clase_de_cifra(conteo) == "numero", conteo
        assert graficos._formato(conteo) == "entero", conteo
    espec = graficos.sugerir(["País destino estrella", "Numero exportadoras"], [["Estados Unidos", 3340], ["Ecuador", 1500]])
    assert espec["formato"] == "entero"

    # Y lo que sí son dólares lo sigue siendo, con o sin la palabra USD.
    for dolares in ("EXPO_2025", "TOTAL_EXPO_2021_2025", "Total expo 5 anos USD", "EXPO_ENE_MAY_2026"):
        assert clase_de_cifra(dolares) == "usd", dolares


def test_un_porcentaje_lleva_su_simbolo_en_la_tabla_y_en_el_texto() -> None:
    """La gráfica decía «19,9 %» y la tabla «19,89»: la misma cifra con dos unidades."""
    from backend.ia.forma import clase_de_cifra
    from backend.ia.redactor import resumen_determinista

    for porcentaje in ("PCT_EXPORTADORAS", "PROMEDIO_POBREZA_MUNICIPIO_PCT", "Promedio pobreza municipio",
                       "PARTICIPACION_USD_PCT", "Tasa de informalidad"):
        assert clase_de_cifra(porcentaje) == "porcentaje", porcentaje

    texto = resumen_determinista(
        ["¿La empresa ha exportado?", "Promedio pobreza municipio"], [["Sí", 19.891126], ["No", 24.5]], 2, False
    )
    assert "19,89 %" in texto and "24,50 %" in texto


# ── El resumen automático se lee bien: es lo que sale cuando la IA no está ─


def test_el_resumen_automatico_nombra_la_fila_por_la_columna_que_la_distingue() -> None:
    """Visto en producción: «el valor más alto … en Antioquia» con las 7 filas de Antioquia."""
    from backend.ia.redactor import resumen_determinista

    texto = resumen_determinista(
        ["Departamento", "Periodo", "Total exportaciones USD"],
        [
            ["Antioquia", "2021", 5694419025.39],
            ["Antioquia", "2022", 7100000000.0],
            ["Antioquia", "2024", 9838631919.12],
        ],
        3,
        False,
    )
    assert "en 2024." in texto
    assert "en Antioquia." not in texto


def test_el_resumen_automatico_no_pega_dos_puntos_seguidos() -> None:
    """«Bogotá, D.C.» ya termina en punto."""
    from backend.ia.redactor import resumen_determinista

    texto = resumen_determinista(
        ["Departamento de la empresa", "Tamaño de la empresa", "Numero empresas"],
        [["Amazonas", "Micro", 2162], ["Bogotá, D.C.", "Micro", 346037]],
        135,
        False,
    )
    assert "Bogotá, D.C. La tabla" in texto
    assert ".." not in texto


def test_el_resumen_automatico_no_afirma_un_maximo_sobre_un_resultado_recortado() -> None:
    """La misma regla que se le exige al modelo: sin resultado completo, no hay superlativo."""
    from backend.ia.redactor import resumen_determinista

    columnas = ["NIT", "Razón social", "Total expo 5 anos USD"]
    filas = [["899999068", "ECOPETROL S A", 52158504845.93], ["800021308", "DRUMMOND LTD", 15222314753.65]]

    completo = resumen_determinista(columnas, filas, 2, False)
    assert "El valor más alto" in completo

    recortado = resumen_determinista(columnas, filas, 5000, True)
    assert "El valor más alto" not in recortado
    assert "se recortó" in recortado


def test_el_resumen_automatico_mide_por_la_cifra_y_no_por_el_identificador() -> None:
    """El «valor más alto» de una tabla de empresas es la exportación, nunca el NIT."""
    from backend.ia.redactor import resumen_determinista

    texto = resumen_determinista(
        ["NIT", "Razón social", "Total expo 5 anos USD"],
        [[899999068, "ECOPETROL S A", 52158504845.93], [800021308, "DRUMMOND LTD", 15222314753.65]],
        2,
        False,
    )
    assert "El valor más alto de «Total expo 5 anos USD»" in texto
    # El NIT se escribe como identificador: sin separador de miles y sin unidad.
    assert "899999068" in texto and "899.999.068" not in texto
    # Y la cifra sí lleva su unidad, igual que se le exige al modelo.
    assert "USD 52.158.504.845,93" in texto


def test_el_resumen_automatico_no_promete_una_tabla_que_no_esta_completa() -> None:
    from backend.ia.redactor import resumen_determinista

    corto = resumen_determinista(["DEPARTAMENTO", "EMPRESAS"], [["Antioquia", 231544]], 1, False)
    assert "La tabla de abajo tiene el detalle completo." in corto
    assert corto.startswith("La consulta devolvió 1 fila.")

    largo = resumen_determinista(["NIT", "Razón social"], [["8999", "ECOPETROL S A"]], 4200, False)
    assert "La tabla de abajo tiene el detalle completo." not in largo
    assert "primeras 500 filas" in largo and "descarga" in largo


def test_el_resumen_automatico_da_formato_a_las_cifras_y_enumera_un_cruce_corto() -> None:
    from backend.ia.redactor import resumen_determinista

    texto = resumen_determinista(
        ["Promedio pobreza municipio", "¿La empresa ha exportado?"], [[19.891126311511194, "No"], [12.52, "Sí"]], 2, False
    )
    assert "19,89" in texto and "12,52" in texto and "(No)" in texto and "(Sí)" in texto
    assert "19.891126311511194" not in texto  # nunca el número crudo

    listado = resumen_determinista(
        ["NIT", "Razón social", "Total expo 5 anos USD"],
        [["899999068", "ECOPETROL S A", 52158504845.93], ["800021308", "DRUMMOND LTD", 15222314753.65]],
        100,
        False,
    )
    assert "52.158.504.845,93" in listado
    # La empresa se nombra por su razón social, no por su NIT.
    assert "en ECOPETROL S A" in listado


# ── Descargas y diagnóstico ───────────────────────────────────────────────


def test_una_descarga_viaja_en_trozos_y_no_linea_por_linea() -> None:
    """Un .xlsx es binario: recorrerlo «por líneas» produce miles de trozos diminutos."""
    from backend.comun import TROZO_DESCARGA, _trozos

    datos = b"\x00\n\x01\n" * 50_000
    assert len(list(_trozos(datos))) == -(-len(datos) // TROZO_DESCARGA)
    assert b"".join(_trozos(io.BytesIO(datos))) == datos
    assert b"".join(_trozos(iter([b"a", b"b"]))) == b"ab"


def test_un_token_de_diagnostico_con_acentos_responde_403_y_no_un_error() -> None:
    """`compare_digest` sobre texto exige ASCII: sin convertir a bytes, un token
    con acentos produce un error interno en vez de un 403.

    Se ejecuta en modo demostración a propósito: la puerta de acceso se decide
    antes de tocar Snowflake, así que la prueba no necesita —ni debe— abrir una
    conexión real.
    """
    import importlib

    import backend.comun
    import backend.main
    import backend.middleware
    import backend.routers.asistente
    import backend.routers.empresas
    import backend.routers.recursos
    import backend.routers.salud

    modulos = (
        backend.comun, backend.middleware, backend.routers.asistente,
        backend.routers.salud, backend.routers.empresas, backend.routers.recursos,
    )
    anterior = dict(os.environ)
    os.environ.update({"APP_DEMO_MODE": "true", "APP_ENV": "production", "APP_DIAG_TOKEN": "token-de-prueba"})
    try:
        for modulo in modulos:
            importlib.reload(modulo)
        cliente = TestClient(importlib.reload(backend.main).app)
        assert cliente.get("/api/diagnostico?token=cañón").status_code == 403
        assert cliente.get("/api/diagnostico?token=otro").status_code == 403
        # El token correcto entra, tanto por la URL como por la cabecera.
        assert cliente.get("/api/diagnostico?token=token-de-prueba").json()["modo"] == "demo"
        assert cliente.get("/api/diagnostico", headers={"X-Diag-Token": "token-de-prueba"}).json()["modo"] == "demo"
    finally:
        os.environ.clear()
        os.environ.update(anterior)
        for modulo in modulos:
            importlib.reload(modulo)
        importlib.reload(backend.main)
