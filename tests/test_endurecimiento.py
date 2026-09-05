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
    assert _clase_numerica("Promedio pobreza municipio") == "numero"


# ── El resumen automático se lee bien: es lo que sale cuando la IA no está ─


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
