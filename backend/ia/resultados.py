"""
Resultados del asistente guardados en el servidor, por ``consulta_id``.

Resuelve de una vez varias cosas que antes dependían de lo que viajaba al
navegador: las descargas traen **todas** las filas (no sólo las 500 que se
muestran), el listado con formato estándar parte de los NIT reales, el
historial que se reenvía a Cortex Analyst es el contenido real que devolvió, y
una descarga queda ligada a la consulta que la originó.

Es una caché en memoria con vencimiento y tope de tamaño. Supone una sola
instancia del servicio (decisión D-05 en docs/DECISIONES.md); si el aplicativo
escalara a varias, la tabla de telemetría —que ya lleva el ``consulta_id``—
sería el lugar natural para reemplazarla.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ResultadoGuardado:
    """Todo lo que hace falta para descargar, refinar o auditar una respuesta."""

    consulta_id: str
    sesion_id: str
    pregunta: str
    sql: str
    columnas: list[str]
    columnas_tecnicas: list[str]
    filas: list[list[Any]]
    n_filas: int
    truncado: bool
    nits: list[str] = field(default_factory=list)
    contenido_crudo: list[dict[str, Any]] = field(default_factory=list)
    request_id: str = ""
    texto: str = ""
    degradado: bool = False
    motivo_degradacion: str = ""
    creado: float = 0.0

    @property
    def celdas(self) -> int:
        return len(self.filas) * max(1, len(self.columnas))


class AlmacenResultados:
    """LRU con vencimiento y presupuesto de celdas, seguro entre hilos."""

    def __init__(
        self,
        capacidad: int = 50,
        vigencia: float = 1800.0,
        max_celdas: int = 2_000_000,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._capacidad = max(1, capacidad)
        self._vigencia = max(1.0, float(vigencia))
        self._max_celdas = max(1, max_celdas)
        self._reloj = reloj
        self._datos: "OrderedDict[str, ResultadoGuardado]" = OrderedDict()
        self._lock = threading.Lock()

    def guardar(self, resultado: ResultadoGuardado) -> None:
        with self._lock:
            resultado.creado = self._reloj()
            self._datos.pop(resultado.consulta_id, None)
            self._datos[resultado.consulta_id] = resultado
            self._purgar()

    def obtener(self, consulta_id: str) -> ResultadoGuardado | None:
        with self._lock:
            self._purgar()
            resultado = self._datos.get(consulta_id)
            if resultado is None:
                return None
            self._datos.move_to_end(consulta_id)
            return resultado

    def actualizar(self, consulta_id: str, **campos: Any) -> None:
        """Completa un resultado ya guardado (p. ej. el texto cuando termina la redacción)."""
        with self._lock:
            resultado = self._datos.get(consulta_id)
            if resultado is None:
                return
            for nombre, valor in campos.items():
                setattr(resultado, nombre, valor)

    def __len__(self) -> int:
        with self._lock:
            return len(self._datos)

    def _purgar(self) -> None:
        ahora = self._reloj()
        vencidos = [clave for clave, valor in self._datos.items() if ahora - valor.creado > self._vigencia]
        for clave in vencidos:
            del self._datos[clave]
        while len(self._datos) > self._capacidad:
            self._datos.popitem(last=False)
        celdas = sum(valor.celdas for valor in self._datos.values())
        while celdas > self._max_celdas and len(self._datos) > 1:
            _, retirado = self._datos.popitem(last=False)
            celdas -= retirado.celdas
