/**
 * Tabla estándar de empresas: búsqueda local, selección de columnas, orden por
 * columna, encabezado y dos columnas fijas (escritorio), tarjetas (móvil) y
 * enlace a la ficha por NIT.
 *
 * La usan la sección de consulta (Resultados) y el asistente cuando la
 * respuesta es un listado de empresas: así un listado se ve igual venga de
 * donde venga. La paginación y la descarga quedan fuera: son de quien la usa.
 */
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { esNumericaVisual, etiquetaCorta, formatearValor } from '../formato';
import { useCerrarAlExterior, useDebounce } from '../hooks';
import type { Fila } from '../tipos';
import { EstadoVacio } from './Interfaz';

type Props = {
  /** Todas las columnas disponibles, en el orden del servidor. */
  columnas: string[];
  filas: Fila[];
  /** Cambia cuando cambia la consulta: reinicia búsqueda, orden y columnas. */
  identidad: string;
  /** Controles adicionales para la barra (p. ej. el tamaño de página). */
  herramientas?: ReactNode;
  etiquetaBusqueda?: string;
  textoVacio?: string;
};

const ESENCIALES = ['NIT', 'Razón social'];
const SI_NO = new Set(['¿La empresa ha exportado?', 'Inversión extranjera', 'Empresa exportadora NME según actividad económica']);

function celda(valor: unknown, columna: string) {
  if (SI_NO.has(columna) && (valor === 'Sí' || valor === 'No')) {
    return <span className={`si-no si-no--${valor === 'Sí' ? 'si' : 'no'}`}>{valor}</span>;
  }
  return formatearValor(valor, columna);
}

export function TablaEmpresas({
  columnas: disponibles,
  filas: filasCrudas,
  identidad,
  herramientas,
  etiquetaBusqueda = 'Buscar en esta página…',
  textoVacio = 'La búsqueda local sólo revisa las empresas en pantalla. Pruebe otra palabra o borre el texto.',
}: Props) {
  const [columnas, setColumnas] = useState<string[]>(disponibles);
  const [busqueda, setBusqueda] = useState('');
  const busquedaLenta = useDebounce(busqueda, 160);
  const [orden, setOrden] = useState<{ columna: string; direccion: 'asc' | 'desc' } | null>(null);
  const [menuColumnas, setMenuColumnas] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const identidadPrevia = useRef(identidad);
  // Identificador único por instancia: en el asistente puede haber varias tablas
  // en el mismo hilo, y `aria-controls` debe apuntar al menú de la suya.
  const idMenu = `menu-columnas-${useId().replace(/:/g, '')}`;

  useEffect(() => {
    if (identidadPrevia.current !== identidad) {
      identidadPrevia.current = identidad;
      setColumnas(disponibles);
      setBusqueda('');
      setOrden(null);
      setMenuColumnas(false);
    } else {
      setColumnas((actuales) => {
        const conservadas = actuales.filter((columna) => disponibles.includes(columna));
        const esenciales = ESENCIALES.filter((columna) => disponibles.includes(columna) && !conservadas.includes(columna));
        return [...esenciales, ...conservadas];
      });
    }
  }, [disponibles, identidad]);
  useCerrarAlExterior(menuColumnas, menuRef, () => setMenuColumnas(false));

  const filas = useMemo(() => {
    const termino = busquedaLenta.trim().toLocaleLowerCase('es-CO');
    let lista: Fila[] = filasCrudas;
    if (termino) lista = lista.filter((fila) => columnas.some((columna) => String(fila[columna] ?? '').toLocaleLowerCase('es-CO').includes(termino)));
    if (orden) {
      const { columna, direccion } = orden;
      const factor = direccion === 'asc' ? 1 : -1;
      lista = [...lista].sort((a, b) => {
        const va = a[columna];
        const vb = b[columna];
        if (va === null || va === undefined || va === '') return 1;
        if (vb === null || vb === undefined || vb === '') return -1;
        if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * factor;
        return String(va).localeCompare(String(vb), 'es-CO', { numeric: true, sensitivity: 'base' }) * factor;
      });
    }
    return lista;
  }, [filasCrudas, busquedaLenta, columnas, orden]);

  const columnasTarjeta = columnas.filter((columna) => !ESENCIALES.includes(columna));
  const ordenarPor = (columna: string) =>
    setOrden((actual) => (actual?.columna === columna ? (actual.direccion === 'asc' ? { columna, direccion: 'desc' } : null) : { columna, direccion: 'asc' }));

  return (
    <>
      <div className="barra-tabla">
        <label className="campo-con-icono barra-tabla__buscar">
          <span className="sr-solo">Buscar dentro de la tabla</span>
          <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true">
            <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <path d="m10.5 10.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <input className="campo" value={busqueda} onChange={(evento) => setBusqueda(evento.target.value)} placeholder={etiquetaBusqueda} />
        </label>
        <div className="barra-tabla__acciones">
          {herramientas}
          <div className="columnas" ref={menuRef}>
            <button type="button" className="boton boton--fantasma boton--chico" aria-expanded={menuColumnas} aria-controls={idMenu} onClick={() => setMenuColumnas((valor) => !valor)}>
              Columnas · {columnas.length}
            </button>
            {menuColumnas && (
              <div id={idMenu} className="columnas__menu">
                <header>
                  <strong>Columnas visibles</strong>
                  <small>NIT y razón social siempre se muestran</small>
                </header>
                <div style={{ display: 'flex', gap: 10, marginBottom: 6 }}>
                  <button type="button" className="enlace-boton" onClick={() => setColumnas(disponibles)}>
                    Todas
                  </button>
                  <button type="button" className="enlace-boton" onClick={() => setColumnas(ESENCIALES.filter((c) => disponibles.includes(c)))}>
                    Sólo esenciales
                  </button>
                </div>
                {disponibles.map((columna) => {
                  const esencial = ESENCIALES.includes(columna);
                  return (
                    <label key={columna} className={esencial ? 'esencial' : ''}>
                      <input
                        className="casilla"
                        type="checkbox"
                        checked={esencial || columnas.includes(columna)}
                        disabled={esencial}
                        onChange={() => setColumnas((actuales) => (actuales.includes(columna) ? actuales.filter((item) => item !== columna) : disponibles.filter((c) => c === columna || actuales.includes(c))))}
                      />
                      <span>
                        {columna}
                        {esencial && <small> · esencial</small>}
                      </span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="tabla-resultados" tabIndex={0} aria-label="Tabla de empresas; desplácese horizontalmente para ver más columnas">
        <table>
          <thead>
            <tr>
              {columnas.map((columna, indice) => {
                const numerica = filasCrudas.some((fila) => esNumericaVisual(columna, fila[columna]));
                const activo = orden?.columna === columna;
                return (
                  <th key={columna} scope="col" className={`${numerica ? 'num' : ''} ${indice === 0 ? 'fijo-1' : indice === 1 ? 'fijo-2' : ''}`} aria-sort={activo ? (orden?.direccion === 'asc' ? 'ascending' : 'descending') : 'none'}>
                    <button type="button" onClick={() => ordenarPor(columna)} title={`Ordenar por ${columna}`}>
                      <span>{etiquetaCorta(columna)}</span>
                      <span className="orden" aria-hidden="true">
                        {activo ? (orden?.direccion === 'asc' ? '▲' : '▼') : '↕'}
                      </span>
                    </button>
                  </th>
                );
              })}
              <th scope="col" className="acciones-fila">
                <span style={{ display: 'block', padding: '11px' }}>Ficha</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {filas.map((fila, indiceFila) => {
              const nit = String(fila.NIT ?? '');
              return (
                <tr key={`${nit}-${indiceFila}`}>
                  {columnas.map((columna, indice) => {
                    const numerica = esNumericaVisual(columna, fila[columna]);
                    const clase = `${numerica ? 'num dato' : ''} ${indice === 0 ? 'fijo-1 dato' : indice === 1 ? 'fijo-2' : ''}`.trim();
                    if (columna === 'Razón social' && nit) {
                      return (
                        <td key={columna} className={clase}>
                          <Link className="enlace-empresa" to={`/empresa/${nit}`}>
                            {String(fila[columna] ?? '—')}
                          </Link>
                        </td>
                      );
                    }
                    return (
                      <td key={columna} className={clase}>
                        {celda(fila[columna], columna)}
                      </td>
                    );
                  })}
                  <td className="acciones-fila">
                    {nit ? (
                      <Link className="boton boton--fantasma boton--chico" to={`/empresa/${nit}`}>
                        Ver ficha
                      </Link>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="tarjetas-resultados">
        {filas.map((fila, indiceFila) => {
          const nit = String(fila.NIT ?? '');
          return (
            <article key={`${nit}-t-${indiceFila}`} className="tarjeta-empresa">
              <div className="tarjeta-empresa__cab">
                <span className="dato">NIT {nit || '—'}</span>
                {fila['Tamaño de la empresa'] && <span className="etiqueta-mini etiqueta-mini--azul">{String(fila['Tamaño de la empresa'])}</span>}
              </div>
              <h3>{nit ? <Link to={`/empresa/${nit}`}>{String(fila['Razón social'] ?? '—')}</Link> : String(fila['Razón social'] ?? '—')}</h3>
              {columnasTarjeta.length > 0 && (
                <dl>
                  {columnasTarjeta.map((columna) => (
                    <div key={columna}>
                      <dt>{etiquetaCorta(columna)}</dt>
                      <dd className={esNumericaVisual(columna, fila[columna]) ? 'dato' : ''}>{celda(fila[columna], columna)}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {nit && (
                <div className="tarjeta-empresa__pie">
                  <Link className="boton boton--fantasma boton--chico" to={`/empresa/${nit}`}>
                    Ver ficha completa →
                  </Link>
                </div>
              )}
            </article>
          );
        })}
      </div>

      {!filas.length && busqueda && <EstadoVacio titulo="No hay coincidencias" texto={textoVacio} />}
    </>
  );
}
