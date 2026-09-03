/**
 * Página «Asistente» (/asistente).
 *
 * Permite preguntar en español sobre las 1,68 millones de empresas y obtener una
 * respuesta con tres partes que se leen juntas: el texto, la gráfica y la tabla.
 * Cada respuesta lleva la advertencia de que la generó una inteligencia
 * artificial y muestra la consulta que la respalda, para poder verificarla.
 *
 * La página no habla nunca con un servicio de IA: sólo con este aplicativo, que
 * a su vez consulta Snowflake con el mismo rol de solo lectura de siempre.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ErrorApi, exportarIA, obtenerEstadoIA, preguntarIA } from '../api';
import { Aviso, CabeceraPagina, Pastilla, Spinner } from '../componentes/Interfaz';
import { Grafica } from '../componentes/Grafica';
import { formatearEntero, formatearValor } from '../formato';
import type { EstadoIA, EventoIA, RespuestaIA } from '../tipos';

type Turno = { pregunta: string; respuesta: RespuestaIA | null; error: string };

const ETAPAS: Record<string, string> = {
  interpretando: 'Interpretando la pregunta',
  validando: 'Revisando la consulta',
  consultando: 'Consultando la base',
  corrigiendo: 'Corrigiendo la consulta',
  datos: 'Datos obtenidos',
  redactando: 'Redactando la respuesta',
};

/** Historial en el formato que espera Cortex Analyst, para dar continuidad. */
function historialDe(turnos: Turno[]): Array<Record<string, unknown>> {
  const mensajes: Array<Record<string, unknown>> = [];
  for (const turno of turnos.slice(-3)) {
    if (!turno.respuesta) continue;
    mensajes.push({ role: 'user', content: [{ type: 'text', text: turno.pregunta }] });
    mensajes.push({ role: 'analyst', content: [{ type: 'sql', statement: turno.respuesta.sql }] });
  }
  return mensajes;
}

export default function Asistente() {
  const [estado, setEstado] = useState<EstadoIA | null>(null);
  const [pregunta, setPregunta] = useState('');
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [etapa, setEtapa] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [descargando, setDescargando] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const finRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    obtenerEstadoIA()
      .then(setEstado)
      .catch(() => setEstado(null));
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    if (turnos.length) finRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turnos.length, etapa]);

  const enviar = useCallback(
    async (texto: string) => {
      const limpia = texto.trim();
      if (!limpia || ocupado) return;
      setPregunta('');
      setOcupado(true);
      setEtapa('interpretando');
      const indice = turnos.length;
      setTurnos((previos) => [...previos, { pregunta: limpia, respuesta: null, error: '' }]);
      const controlador = new AbortController();
      abortRef.current = controlador;
      try {
        await preguntarIA(
          limpia,
          historialDe(turnos),
          (evento: EventoIA) => {
            if (evento.tipo === 'etapa') setEtapa(evento.etapa);
            if (evento.tipo === 'error') {
              setTurnos((previos) => previos.map((t, i) => (i === indice ? { ...t, error: evento.mensaje } : t)));
            }
            if (evento.tipo === 'final') {
              setTurnos((previos) => previos.map((t, i) => (i === indice ? { ...t, respuesta: evento } : t)));
            }
          },
          controlador.signal,
        );
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        const mensaje = error instanceof ErrorApi ? error.message : 'El asistente no pudo responder.';
        setTurnos((previos) => previos.map((t, i) => (i === indice ? { ...t, error: mensaje } : t)));
      } finally {
        setOcupado(false);
        setEtapa('');
        abortRef.current = null;
      }
    },
    [ocupado, turnos],
  );

  const descargar = async (formato: 'excel' | 'pptx', turno: Turno) => {
    if (!turno.respuesta) return;
    setDescargando(`${formato}-${turno.respuesta.consulta_id}`);
    try {
      await exportarIA(formato, {
        pregunta: turno.pregunta,
        respuesta: turno.respuesta.texto,
        sql: turno.respuesta.sql,
        columnas: turno.respuesta.columnas,
        filas: turno.respuesta.filas,
        n_filas: turno.respuesta.n_filas,
      });
    } catch (error) {
      const mensaje = error instanceof ErrorApi ? error.message : 'No fue posible preparar el archivo.';
      setTurnos((previos) => previos.map((t) => (t === turno ? { ...t, error: mensaje } : t)));
    } finally {
      setDescargando('');
    }
  };

  const bloqueado = estado !== null && !estado.disponible;

  return (
    <>
      <CabeceraPagina
        oscura
        kicker="Asistente de análisis"
        titulo="Pregunte en español y obtenga la tabla, la gráfica y el Excel."
        bajada="Escriba lo que necesita saber sobre las empresas colombianas: cuántas hay, dónde están, cuánto exportan, a qué mercados o cuáles son candidatas a exportar. El asistente arma la consulta, la ejecuta en Snowflake y le muestra el resultado con la consulta que lo respalda."
      />

      <div className="pagina asistente">
        {estado === null ? (
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
                    <strong>Usted pregunta</strong> en español, como se lo diría a un colega.
                  </li>
                  <li>
                    <strong>El asistente arma la consulta</strong> con el modelo de datos del tejido empresarial y la
                    ejecuta en Snowflake, sólo de lectura.
                  </li>
                  <li>
                    <strong>Usted recibe</strong> la respuesta escrita, la tabla, una gráfica cuando corresponde y la
                    consulta exacta que se ejecutó.
                  </li>
                </ol>
              </div>
              <div className="asistente__aviso-fijo">
                <Aviso tipo="advertencia">{estado.advertencia}</Aviso>
              </div>
            </section>

            {turnos.length === 0 && (
              <section className="tarjeta mt-20" aria-labelledby="t-sugerencias">
                <h2 id="t-sugerencias">Para empezar</h2>
                <p className="texto-suave">Pulse una pregunta o escriba la suya abajo.</p>
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
              </section>
            )}

            <div className="asistente__hilo">
              {turnos.map((turno, indice) => (
                <article key={`${indice}-${turno.pregunta}`} className="asistente__turno">
                  <p className="asistente__pregunta">
                    <span className="asistente__etiqueta">Usted preguntó</span>
                    {turno.pregunta}
                  </p>

                  {turno.error && (
                    <div className="mt-12">
                      <Aviso tipo="error">{turno.error}</Aviso>
                    </div>
                  )}

                  {!turno.respuesta && !turno.error && ocupado && indice === turnos.length - 1 && (
                    <div className="asistente__progreso" role="status">
                      <Spinner oscuro />
                      <span>{ETAPAS[etapa] ?? 'Procesando'}…</span>
                    </div>
                  )}

                  {turno.respuesta && <Respuesta turno={turno} descargando={descargando} alDescargar={descargar} />}
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
              <textarea
                id="pregunta-ia"
                className="asistente__campo"
                value={pregunta}
                onChange={(evento) => setPregunta(evento.target.value.slice(0, estado.max_caracteres))}
                onKeyDown={(evento) => {
                  if (evento.key === 'Enter' && !evento.shiftKey) {
                    evento.preventDefault();
                    void enviar(pregunta);
                  }
                }}
                placeholder="Por ejemplo: ¿cuántas empresas medianas de Agroalimentos hay en Antioquia y cuántas exportan?"
                rows={2}
                disabled={bloqueado || ocupado}
              />
              <button type="submit" className="boton boton--cinta" disabled={bloqueado || ocupado || !pregunta.trim()}>
                {ocupado ? (
                  <>
                    <Spinner oscuro /> Consultando…
                  </>
                ) : (
                  'Preguntar'
                )}
              </button>
            </form>
            <p className="asistente__pie-legal">{estado.advertencia}</p>
          </>
        )}
      </div>
    </>
  );
}

function Respuesta({
  turno,
  descargando,
  alDescargar,
}: {
  turno: Turno;
  descargando: string;
  alDescargar: (formato: 'excel' | 'pptx', turno: Turno) => void;
}) {
  const [verSql, setVerSql] = useState(false);
  const respuesta = turno.respuesta;
  if (!respuesta) return null;
  const { columnas, filas, n_filas, truncado, grafica, meta } = respuesta;

  return (
    <div className="asistente__respuesta">
      <p className="asistente__texto">{respuesta.texto}</p>

      <div className="asistente__sellos">
        <Pastilla tono={meta.cifras_verificadas ? 'ok' : 'alerta'}>
          {meta.cifras_verificadas ? 'Cifras verificadas contra la tabla' : 'Resumen construido con los datos'}
        </Pastilla>
        {n_filas > 0 && <Pastilla tono="azul">{formatearEntero(n_filas)} fila(s)</Pastilla>}
        <Pastilla>{(meta.ms_total / 1000).toFixed(1).replace('.', ',')} s</Pastilla>
      </div>

      {grafica && (
        <div className="asistente__grafica">
          <Grafica espec={grafica} />
        </div>
      )}

      {columnas.length > 0 && filas.length > 0 && (
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
          Se muestran las primeras {formatearEntero(filas.length)} filas de {formatearEntero(n_filas)}. El Excel trae
          todas las que se descargaron.
        </p>
      )}

      <div className="asistente__acciones">
        <button
          type="button"
          className="boton boton--primario boton--chico"
          onClick={() => alDescargar('excel', turno)}
          disabled={descargando !== '' || !columnas.length}
        >
          {descargando.startsWith('excel') ? 'Preparando…' : 'Descargar Excel'}
        </button>
        <button
          type="button"
          className="boton boton--fantasma boton--chico"
          onClick={() => alDescargar('pptx', turno)}
          disabled={descargando !== '' || !columnas.length}
        >
          {descargando.startsWith('pptx') ? 'Preparando…' : 'Descargar presentación'}
        </button>
        {respuesta.sql && (
          <button type="button" className="boton boton--fantasma boton--chico" onClick={() => setVerSql((v) => !v)}>
            {verSql ? 'Ocultar la consulta' : 'Ver la consulta'}
          </button>
        )}
      </div>

      {verSql && respuesta.sql && (
        <pre className="asistente__sql">
          <code>{respuesta.sql}</code>
        </pre>
      )}
    </div>
  );
}
