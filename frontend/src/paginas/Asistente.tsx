/**
 * Página «Asistente» (/asistente).
 *
 * Permite preguntar en español sobre las 1,68 millones de empresas y obtener la
 * respuesta escrita, la tabla y —si se pide— la gráfica, con la consulta que las
 * respalda y la advertencia de que las generó una inteligencia artificial.
 *
 * El hilo tiene memoria: el servidor reconstruye el contexto de las últimas
 * preguntas a partir de sus `consulta_id`, así que se puede refinar hasta llegar
 * a un listado de empresas, que se muestra con la tabla estándar de la sección
 * de consulta y se descarga con el mismo formato.
 *
 * La página no habla nunca con un servicio de IA: sólo con este aplicativo, que
 * a su vez consulta Snowflake con el mismo rol de siempre. En el navegador se
 * conserva únicamente el esqueleto del hilo (pregunta, identificador, texto y
 * columnas): nunca las filas, que pueden traer datos de contacto.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ErrorApi, exportarIA, obtenerEstadoIA, obtenerSesionId, preguntarIA } from '../api';
import { Grafica } from '../componentes/Grafica';
import { Aviso, CabeceraPagina, Pastilla, Spinner } from '../componentes/Interfaz';
import { TablaEmpresas } from '../componentes/TablaEmpresas';
import { formatearEntero, formatearValor } from '../formato';
import type { EstadoIA, EventoIA, Fila, MetaIA, RespuestaIA } from '../tipos';

type Descarga = 'excel' | 'pptx' | 'empresas';

export type Turno = {
  id: number;
  pregunta: string;
  respuesta: RespuestaIA | null;
  error: string;
  detenido: boolean;
  descargando: Descarga | '';
  errorDescarga: string;
  /** Rehidratado desde la sesión del navegador: no conserva la tabla. */
  recordado: boolean;
};

/** Lo que se guarda por turno en el navegador (nunca filas). */
type TurnoGuardado = {
  pregunta: string;
  consulta_id: string;
  texto: string;
  sql: string;
  columnas: string[];
  n_filas: number;
  es_listado: boolean;
  meta: MetaIA;
};

const CLAVE_HILO = 'tejido.asistente.hilo';

/** Mientras se redacta, la respuesta viaja sin texto ni metadatos definitivos. */
const META_PENDIENTE: MetaIA = {
  modelo: '', degradado: false, motivo_degradacion: '', cifras_verificadas: true, forma_redaccion: '',
  ms_interpretacion: 0, ms_consulta: 0, ms_correccion: 0, ms_redaccion: 0, ms_total: 0,
  intentos_sql: 0, analyst_request_id: '', version: '', vista_semantica: '',
};

const ETAPAS: Array<{ clave: string; texto: string }> = [
  { clave: 'interpretando', texto: 'Interpretar la pregunta' },
  { clave: 'validando', texto: 'Revisar la consulta' },
  { clave: 'consultando', texto: 'Consultar la base' },
  { clave: 'datos', texto: 'Recibir los datos' },
  { clave: 'redactando', texto: 'Redactar la respuesta' },
];
const ORDEN_ETAPAS: Record<string, number> = { interpretando: 0, validando: 1, consultando: 2, corrigiendo: 2, datos: 3, redactando: 4 };

const MOTIVOS: Record<string, { sello: string; explicacion: string }> = {
  redaccion_fallo: {
    sello: 'Resumen automático de los datos: la redacción con IA no estuvo disponible',
    explicacion:
      'La función de redacción de Snowflake (Cortex COMPLETE) no respondió. La tabla y la consulta son exactas; sólo falta el texto escrito. Quien administra el despliegue puede ver la causa en la página /estado, paso «Cortex COMPLETE».',
  },
  respuesta_vacia: {
    sello: 'Resumen automático de los datos: la redacción con IA llegó vacía',
    explicacion: 'El modelo devolvió una respuesta vacía. La tabla y la consulta son exactas; se muestra un resumen construido con los datos.',
  },
  cifras_sin_respaldo: {
    sello: 'Se descartaron cifras sin respaldo en la tabla',
    explicacion:
      'El texto redactado citaba una cifra que no está en la tabla. Para no mostrar un dato sin respaldo, se reemplazó por un resumen construido con los datos reales.',
  },
};

/** Milisegundos como segundos con un decimal, en formato local. */
const segundos = (ms: number) => (ms / 1000).toFixed(1).replace('.', ',');

let contadorTurnos = 0;
const nuevoTurno = (pregunta: string): Turno => ({
  id: ++contadorTurnos, pregunta, respuesta: null, error: '', detenido: false, descargando: '', errorDescarga: '', recordado: false,
});

const conRespuesta = (turno: Turno): turno is Turno & { respuesta: RespuestaIA } => Boolean(turno.respuesta && turno.respuesta.sql && !turno.error);

function cargarHilo(): Turno[] {
  try {
    const crudo = window.sessionStorage.getItem(CLAVE_HILO);
    if (!crudo) return [];
    const guardados = JSON.parse(crudo) as TurnoGuardado[];
    return guardados.map((g) => ({
      ...nuevoTurno(g.pregunta),
      recordado: true,
      respuesta: {
        tipo: 'final', consulta_id: g.consulta_id, texto: g.texto, sql: g.sql, columnas: g.columnas, filas: [],
        n_filas: g.n_filas, truncado: false, grafica: null, mostrar_grafica: false, es_listado: g.es_listado, n_nits: 0,
        sugerencias: [], advertencia: '', meta: g.meta,
      },
    }));
  } catch {
    return [];
  }
}

function guardarHilo(turnos: Turno[]): void {
  try {
    // Sólo turnos ya terminados: uno con la tabla pero sin texto es un estado
    // transitorio que la rehidratación no sabría representar.
    const terminados = turnos.filter(
      (t): t is Turno & { respuesta: RespuestaIA } => conRespuesta(t) && Boolean(t.respuesta.texto),
    );
    const guardados: TurnoGuardado[] = terminados.slice(-6).map((t) => ({
      pregunta: t.pregunta, consulta_id: t.respuesta.consulta_id, texto: t.respuesta.texto, sql: t.respuesta.sql,
      columnas: t.respuesta.columnas, n_filas: t.respuesta.n_filas, es_listado: t.respuesta.es_listado, meta: t.respuesta.meta,
    }));
    if (guardados.length) window.sessionStorage.setItem(CLAVE_HILO, JSON.stringify(guardados));
    else window.sessionStorage.removeItem(CLAVE_HILO);
  } catch {
    /* sin almacenamiento no hay memoria entre recargas; el hilo sigue funcionando */
  }
}

/** Contexto que se envía con la pregunta: los últimos `n` turnos con respuesta. */
export function contexto(turnos: Turno[], n: number) {
  const previos = turnos.filter(conRespuesta).slice(-n);
  return {
    consulta_ids: previos.map((t) => t.respuesta.consulta_id),
    historial: previos.flatMap((t) => [
      { role: 'user', content: [{ type: 'text', text: t.pregunta }] },
      { role: 'analyst', content: [{ type: 'sql', statement: t.respuesta.sql }] },
    ]),
  };
}

export default function Asistente() {
  const [estado, setEstado] = useState<EstadoIA | null>(null);
  const [errorEstado, setErrorEstado] = useState('');
  const [pregunta, setPregunta] = useState('');
  const [turnos, setTurnos] = useState<Turno[]>(cargarHilo);
  const [etapa, setEtapa] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [transcurrido, setTranscurrido] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const finRef = useRef<HTMLDivElement>(null);
  const sesionId = useMemo(() => obtenerSesionId(), []);

  useEffect(() => {
    obtenerEstadoIA()
      .then(setEstado)
      .catch((error) =>
        setErrorEstado(
          error instanceof ErrorApi
            ? error.message
            : 'No fue posible contactar al aplicativo para preparar el asistente. Revise su conexión y recargue la página.',
        ),
      );
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => guardarHilo(turnos), [turnos]);

  useEffect(() => {
    if (turnos.length) finRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turnos.length, etapa]);

  useEffect(() => {
    if (!ocupado) {
      setTranscurrido(0);
      return;
    }
    const inicio = Date.now();
    const temporizador = window.setInterval(() => setTranscurrido(Date.now() - inicio), 250);
    return () => window.clearInterval(temporizador);
  }, [ocupado]);

  const actualizar = useCallback((id: number, cambios: Partial<Turno>) => {
    setTurnos((previos) => previos.map((t) => (t.id === id ? { ...t, ...cambios } : t)));
  }, []);

  const enviar = useCallback(
    async (texto: string) => {
      const limpia = texto.trim();
      if (!limpia || ocupado) return;
      setPregunta('');
      setOcupado(true);
      setEtapa('interpretando');
      const turno = nuevoTurno(limpia);
      const { consulta_ids, historial } = contexto(turnos, estado?.memoria_turnos ?? 2);
      setTurnos((previos) => [...previos, turno]);
      const controlador = new AbortController();
      abortRef.current = controlador;
      try {
        await preguntarIA(
          { pregunta: limpia, consulta_ids, historial, sesion_id: sesionId },
          (evento: EventoIA) => {
            if (evento.tipo === 'etapa') setEtapa(evento.etapa);
            if (evento.tipo === 'error') actualizar(turno.id, { error: evento.mensaje });
            if (evento.tipo === 'resultado') {
              // La tabla y la consulta ya se pueden leer y descargar; el texto
              // llega en el evento siguiente.
              actualizar(turno.id, { respuesta: { ...evento, tipo: 'final', texto: '', meta: META_PENDIENTE } });
            }
            if (evento.tipo === 'final') actualizar(turno.id, { respuesta: evento });
          },
          controlador.signal,
        );
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          actualizar(turno.id, { detenido: true });
        } else {
          actualizar(turno.id, { error: error instanceof ErrorApi ? error.message : 'El asistente no pudo responder.' });
        }
      } finally {
        setOcupado(false);
        setEtapa('');
        abortRef.current = null;
      }
    },
    [ocupado, turnos, estado, sesionId, actualizar],
  );

  const detener = () => abortRef.current?.abort();

  const reiniciar = () => {
    setTurnos([]);
    try {
      window.sessionStorage.removeItem(CLAVE_HILO);
    } catch {
      /* nada que limpiar */
    }
  };

  const descargar = async (formato: Descarga, turno: Turno) => {
    if (!turno.respuesta) return;
    actualizar(turno.id, { descargando: formato, errorDescarga: '' });
    try {
      await exportarIA(formato, turno.respuesta.consulta_id, sesionId);
    } catch (error) {
      actualizar(turno.id, { errorDescarga: error instanceof ErrorApi ? error.message : 'No fue posible preparar el archivo.' });
    } finally {
      actualizar(turno.id, { descargando: '' });
    }
  };

  const bloqueado = estado !== null && !estado.disponible;
  const maximo = estado?.max_caracteres ?? 800;

  return (
    <>
      <CabeceraPagina
        oscura
        kicker="Asistente de análisis"
        titulo="Pregunte en español y obtenga la respuesta, la tabla y el Excel."
        bajada="Escriba lo que necesita saber sobre las empresas colombianas: cuántas hay, dónde están, cuánto exportan, a qué mercados o cuáles son candidatas a exportar. El asistente arma la consulta, la ejecuta en Snowflake, le muestra el resultado con la consulta que lo respalda y recuerda sus últimas preguntas para que pueda refinarlas hasta llegar a un listado de empresas."
      />

      <div className="pagina asistente">
        {errorEstado ? (
          <Aviso tipo="error" rol="alert">
            {errorEstado}
          </Aviso>
        ) : estado === null ? (
          <div className="estado-carga" role="status">
            <Spinner oscuro /> Preparando el asistente…
          </div>
        ) : (
          <>
            {bloqueado && (
              <div className="mb-16">
                <Aviso tipo="advertencia">{estado.motivo}</Aviso>
              </div>
            )}

            <section className="tarjeta asistente__intro" aria-labelledby="t-como-funciona">
              <div>
                <h2 id="t-como-funciona">Cómo funciona</h2>
                <ol className="asistente__pasos">
                  <li>
                    <strong>Usted pregunta</strong> en español, como se lo diría a un colega. Y puede seguir preguntando sobre
                    lo mismo: «¿y cuántas de esas exportan?», «lístame esas empresas».
                  </li>
                  <li>
                    <strong>El asistente arma la consulta</strong> con el modelo de datos del tejido empresarial y la ejecuta en
                    Snowflake, sólo de lectura.
                  </li>
                  <li>
                    <strong>Usted recibe</strong> la respuesta escrita, la tabla, la consulta exacta que se ejecutó y los botones
                    de descarga; la gráfica, cuando la pida o el resultado sea una sola cifra.
                  </li>
                </ol>
              </div>
              <div className="asistente__aviso-fijo">
                <Aviso tipo="advertencia">{estado.advertencia}</Aviso>
              </div>
            </section>

            <details className="tarjeta mt-20 asistente__plegable" open={turnos.length === 0}>
              <summary>Preguntas para empezar</summary>
              <p className="texto-suave mt-8">Pulse una pregunta o escriba la suya abajo.</p>
              <div className="asistente__sugerencias">
                {estado.sugerencias.map((sugerencia) => (
                  <button
                    key={sugerencia.texto}
                    type="button"
                    className="asistente__sugerencia"
                    onClick={() => void enviar(sugerencia.texto)}
                    disabled={bloqueado || ocupado}
                  >
                    <span className="asistente__grupo">{sugerencia.grupo}</span>
                    {sugerencia.texto}
                  </button>
                ))}
              </div>
            </details>

            <div className="asistente__hilo">
              {turnos.map((turno, indice) => (
                <article key={turno.id} className="asistente__turno">
                  <p className="asistente__pregunta">
                    <span className="asistente__etiqueta">Usted preguntó</span>
                    {turno.pregunta}
                  </p>

                  {turno.error && (
                    <div className="mt-12">
                      <Aviso tipo="error">{turno.error}</Aviso>
                    </div>
                  )}

                  {turno.detenido && !turno.respuesta && (
                    <p className="asistente__nota">Consulta detenida antes de recibir el resultado.</p>
                  )}

                  {!turno.respuesta && !turno.error && ocupado && indice === turnos.length - 1 && (
                    <Progreso etapa={etapa} transcurrido={transcurrido} alDetener={detener} />
                  )}

                  {turno.respuesta && (
                    <Respuesta
                      turno={turno}
                      ocupado={ocupado}
                      enCurso={ocupado && indice === turnos.length - 1 && !turno.error}
                      etapa={indice === turnos.length - 1 ? etapa : ''}
                      transcurrido={indice === turnos.length - 1 ? transcurrido : 0}
                      minutos={estado.resultado_minutos}
                      alDescargar={descargar}
                      alDetener={detener}
                      alPreguntar={(texto) => void enviar(texto)}
                    />
                  )}
                </article>
              ))}
              <div ref={finRef} />
            </div>

            <form
              className="asistente__barra"
              onSubmit={(evento) => {
                evento.preventDefault();
                void enviar(pregunta);
              }}
            >
              <label className="sr-solo" htmlFor="pregunta-ia">
                Escriba su pregunta
              </label>
              <div className="asistente__campo-caja">
                <textarea
                  id="pregunta-ia"
                  className="asistente__campo"
                  value={pregunta}
                  maxLength={maximo}
                  onChange={(evento) => setPregunta(evento.target.value.slice(0, maximo))}
                  onKeyDown={(evento) => {
                    if (evento.key === 'Enter' && !evento.shiftKey) {
                      evento.preventDefault();
                      void enviar(pregunta);
                    }
                  }}
                  placeholder={
                    turnos.length
                      ? 'Siga preguntando sobre este resultado: «¿y cuántas de esas exportan?», «lístame esas empresas con NIT»…'
                      : 'Por ejemplo: ¿cuántas empresas medianas de Agroalimentos hay en Antioquia y cuántas exportan?'
                  }
                  rows={2}
                  disabled={bloqueado || ocupado}
                />
                <span className="asistente__contador" aria-live="off">
                  {pregunta.length} / {maximo}
                </span>
              </div>
              {ocupado ? (
                <button type="button" className="boton boton--fantasma" onClick={detener}>
                  Detener
                </button>
              ) : (
                <button type="submit" className="boton boton--cinta" disabled={bloqueado || !pregunta.trim()}>
                  Preguntar
                </button>
              )}
            </form>
            <div className="asistente__memoria">
              <span>
                El asistente recuerda sus últimas {estado.memoria_turnos} preguntas de este hilo para refinarlas. Los resultados se
                pueden descargar durante {estado.resultado_minutos} minutos.
              </span>
              {turnos.length > 0 && (
                <button type="button" className="enlace-boton" onClick={reiniciar} disabled={ocupado}>
                  Empezar un hilo nuevo
                </button>
              )}
            </div>
            <p className="asistente__pie-legal">{estado.advertencia}</p>
          </>
        )}
      </div>
    </>
  );
}

function Progreso({ etapa, transcurrido, alDetener }: { etapa: string; transcurrido: number; alDetener: () => void }) {
  const actual = ORDEN_ETAPAS[etapa] ?? 0;
  return (
    <div className="asistente__progreso-caja" role="status" aria-live="polite">
      <div className="asistente__progreso-cab">
        <span className="asistente__progreso">
          <Spinner oscuro />
          {etapa === 'corrigiendo' ? 'Corrigiendo la consulta…' : `${ETAPAS[actual]?.texto ?? 'Procesando'}…`}
        </span>
        {/* El cronómetro cambia cada 250 ms: queda fuera de lo que anuncia el lector de pantalla. */}
        <span className="asistente__cronometro" aria-hidden="true">
          {segundos(transcurrido)} s
        </span>
        <button type="button" className="boton boton--fantasma boton--chico" onClick={alDetener}>
          Detener
        </button>
      </div>
      <ol className="asistente__etapas" aria-label="Etapas de la consulta">
        {ETAPAS.map((paso, indice) => (
          <li key={paso.clave} className={indice < actual ? 'hecha' : indice === actual ? 'activa' : ''}>
            <span className="punto" aria-hidden="true" />
            {paso.texto}
          </li>
        ))}
      </ol>
      {transcurrido > 20000 && (
        <p className="asistente__nota">
          {actual <= 1
            ? 'Interpretar una pregunta nueva puede tardar hasta un minuto; las preguntas sugeridas responden más rápido.'
            : 'La redacción puede tardar unos segundos más; la tabla ya se muestra en cuanto llega.'}
        </p>
      )}
    </div>
  );
}

function Respuesta({
  turno,
  ocupado,
  enCurso,
  etapa,
  transcurrido,
  minutos,
  alDescargar,
  alDetener,
  alPreguntar,
}: {
  turno: Turno;
  ocupado: boolean;
  /** La petición de este turno sigue viva: sólo entonces tiene sentido esperar el texto. */
  enCurso: boolean;
  etapa: string;
  transcurrido: number;
  minutos: number;
  alDescargar: (formato: Descarga, turno: Turno) => void;
  alDetener: () => void;
  alPreguntar: (texto: string) => void;
}) {
  const [verGrafica, setVerGrafica] = useState<boolean | null>(null);
  const [copiado, setCopiado] = useState(false);
  const respuesta = turno.respuesta;
  const filasObjeto = useMemo<Fila[]>(
    () =>
      respuesta
        ? respuesta.filas.map((fila) => Object.fromEntries(respuesta.columnas.map((columna, i) => [columna, fila[i] ?? null])) as Fila)
        : [],
    [respuesta],
  );
  if (!respuesta) return null;
  const { columnas, filas, n_filas, truncado, grafica, meta, es_listado } = respuesta;
  const graficaAbierta = verGrafica ?? respuesta.mostrar_grafica;
  const motivo = MOTIVOS[meta.motivo_degradacion];
  const redactando = !respuesta.texto && enCurso;

  const copiarSql = async () => {
    try {
      await navigator.clipboard.writeText(respuesta.sql);
      setCopiado(true);
      window.setTimeout(() => setCopiado(false), 1800);
    } catch {
      /* sin portapapeles: el texto sigue seleccionable */
    }
  };

  return (
    <div className="asistente__respuesta">
      <div aria-live="polite">
        {respuesta.texto ? (
          <p className="asistente__texto">{respuesta.texto}</p>
        ) : turno.error ? null : redactando ? (
          <p className="asistente__redactando" role="status">
            <Spinner oscuro /> Redactando el resumen <span aria-hidden="true">({segundos(transcurrido)} s)</span>… la tabla ya
            está lista.
            {etapa === 'redactando' && (
              <button type="button" className="enlace-boton" onClick={alDetener}>
                Quedarme con la tabla
              </button>
            )}
          </p>
        ) : (
          // Sin texto y sin petición viva: detenida, o cortada antes de terminar.
          <p className="asistente__nota">
            {turno.detenido
              ? 'Consulta detenida: la tabla llegó, el texto no.'
              : 'El resumen escrito no llegó a completarse. La tabla y la consulta son las que se ejecutaron.'}
          </p>
        )}
      </div>

      <div className="asistente__sellos">
        {respuesta.texto && (
          <Pastilla tono={meta.degradado ? 'alerta' : 'ok'}>
            {meta.degradado ? motivo?.sello ?? 'Resumen automático de los datos' : 'Cifras verificadas contra la tabla'}
          </Pastilla>
        )}
        {n_filas > 0 && <Pastilla tono="azul">{formatearEntero(n_filas)} fila(s)</Pastilla>}
        {es_listado && <Pastilla tono="acento">Listado de empresas</Pastilla>}
        {respuesta.texto && !redactando && <Pastilla>{segundos(meta.ms_total)} s</Pastilla>}
      </div>

      {meta.degradado && motivo && (
        <details className="asistente__motivo">
          <summary>¿Por qué?</summary>
          <p>{motivo.explicacion}</p>
        </details>
      )}

      {respuesta.texto && (
        <p className="asistente__tiempos">
          Interpretar la pregunta {segundos(meta.ms_interpretacion)} s · consultar la base {segundos(meta.ms_consulta)} s
          {meta.ms_correccion > 0 ? ` · corregir la consulta ${segundos(meta.ms_correccion)} s` : ''}
          {meta.intentos_sql > 1 ? ` (${meta.intentos_sql} intentos)` : ''} · redactar {segundos(meta.ms_redaccion)} s
          {meta.modelo ? ` (${meta.modelo})` : ''}
        </p>
      )}

      {turno.recordado && (
        <p className="asistente__recordado">
          Pregunta anterior de esta sesión. La tabla no se guarda en el navegador: descárguela con los botones (disponible
          durante {minutos} minutos desde la consulta) o vuelva a preguntar para verla.
        </p>
      )}

      {grafica && !turno.recordado && (
        <div className="asistente__grafica-acciones">
          <button type="button" className="boton boton--fantasma boton--chico" onClick={() => setVerGrafica(!graficaAbierta)} aria-expanded={graficaAbierta}>
            {graficaAbierta ? 'Ocultar la gráfica' : 'Ver gráfica'}
          </button>
        </div>
      )}
      {grafica && graficaAbierta && !turno.recordado && (
        <div className="asistente__grafica">
          <Grafica espec={grafica} />
        </div>
      )}

      {columnas.length > 0 && filas.length > 0 && es_listado && (
        <TablaEmpresas
          columnas={columnas}
          filas={filasObjeto}
          identidad={respuesta.consulta_id}
          etiquetaBusqueda="Buscar en el listado…"
          textoVacio="La búsqueda revisa las empresas en pantalla. Pruebe otra palabra o borre el texto."
        />
      )}

      {columnas.length > 0 && filas.length > 0 && !es_listado && (
        <div className="asistente__tabla-caja">
          <table className="asistente__tabla">
            <caption className="sr-solo">Resultado de la consulta</caption>
            <thead>
              <tr>
                {columnas.map((columna) => (
                  <th key={columna} scope="col">
                    {columna}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filas.map((fila, indice) => (
                <tr key={indice}>
                  {fila.map((valor, columna) => (
                    <td key={columna} className={typeof valor === 'number' ? 'num' : undefined}>
                      {formatearValor(valor, columnas[columna] ?? '')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {truncado && (
        <p className="asistente__nota">
          Se muestran las primeras {formatearEntero(filas.length)} filas de {formatearEntero(n_filas)}. Las descargas traen todas
          las filas obtenidas.
        </p>
      )}

      <div className="asistente__acciones">
        {es_listado && (
          <button
            type="button"
            className="boton boton--cinta boton--chico"
            onClick={() => alDescargar('empresas', turno)}
            disabled={turno.descargando !== ''}
          >
            {turno.descargando === 'empresas' ? 'Preparando…' : 'Descargar listado con formato estándar'}
          </button>
        )}
        <button
          type="button"
          className={`boton ${es_listado ? 'boton--fantasma' : 'boton--primario'} boton--chico`}
          onClick={() => alDescargar('excel', turno)}
          disabled={turno.descargando !== '' || !columnas.length}
        >
          {turno.descargando === 'excel' ? 'Preparando…' : es_listado ? 'Descargar tabla del asistente' : 'Descargar Excel'}
        </button>
        <button
          type="button"
          className="boton boton--fantasma boton--chico"
          onClick={() => alDescargar('pptx', turno)}
          disabled={turno.descargando !== '' || !columnas.length}
        >
          {turno.descargando === 'pptx' ? 'Preparando…' : 'Descargar presentación'}
        </button>
      </div>
      {turno.errorDescarga && (
        <div className="asistente__descarga-error">
          <Aviso tipo="error" rol="alert">
            {turno.errorDescarga}
          </Aviso>
        </div>
      )}

      {respuesta.sql && (
        <details className="asistente__sql-caja">
          <summary>Ver la consulta ejecutada en Snowflake</summary>
          <pre className="asistente__sql">
            <code>{respuesta.sql}</code>
          </pre>
          <div className="asistente__sql-pie">
            <span>{meta.vista_semantica ? `Modelo semántico: ${meta.vista_semantica}` : ''}</span>
            <button type="button" className="enlace-boton" onClick={() => void copiarSql()}>
              {copiado ? 'Copiada' : 'Copiar la consulta'}
            </button>
          </div>
        </details>
      )}

      {respuesta.sugerencias.length > 0 && (
        <div className="asistente__relacionadas" aria-label="Consultas relacionadas">
          {respuesta.sugerencias.slice(0, 4).map((sugerencia) => (
            <button key={sugerencia} type="button" className="asistente__relacionada" onClick={() => alPreguntar(sugerencia)} disabled={ocupado}>
              {sugerencia}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
