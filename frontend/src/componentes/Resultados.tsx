/**
 * Resultados de la consulta: conteo, descarga, avisos, la tabla estándar de
 * empresas (TablaEmpresas) y la paginación con tamaño de página.
 */
import { useEffect, useMemo, useState } from 'react';
import type { RespuestaBusqueda, SolicitudBusqueda } from '../tipos';
import { DescargaExcel } from './DescargaExcel';
import { Aviso, EstadoVacio, Spinner } from './Interfaz';
import { TablaEmpresas } from './TablaEmpresas';

type Props = {
  datos: RespuestaBusqueda;
  solicitud: SolicitudBusqueda;
  sucio: boolean;
  cargando: boolean;
  limiteExportacion: number;
  maxVistaPrevia: number;
  alPaginar: (pagina: number) => void;
  alCambiarTamano: (tamano: number) => void;
};

const TAMANOS = [25, 50, 100];

export function Resultados({ datos, solicitud, sucio, cargando, limiteExportacion, maxVistaPrevia, alPaginar, alCambiarTamano }: Props) {
  const [paginaEditada, setPaginaEditada] = useState(String(datos.page));
  const identidad = useMemo(() => JSON.stringify({ m: solicitud.mode, f: solicitud.filters, t: solicitud.term, n: solicitud.nits }), [solicitud]);

  useEffect(() => setPaginaEditada(String(datos.page)), [datos.page]);

  const demasiadoGrande = datos.total > limiteExportacion;
  const motivoDescarga = sucio ? 'Cambió los criterios: actualice la búsqueda antes de descargar.' : demasiadoGrande ? `Supera las ${limiteExportacion.toLocaleString('es-CO')} empresas por archivo. Agregue filtros para habilitar la descarga.` : undefined;
  const desde = (datos.page - 1) * datos.page_size + 1;
  const hasta = Math.min(datos.total, datos.page * datos.page_size);

  if (!datos.total) {
    return (
      <section className="resultados" id="resultados" aria-labelledby="titulo-resultados">
        <EstadoVacio titulo="No encontramos empresas con este criterio" texto="Pruebe con una razón social más corta, revise el NIT o retire alguno de los filtros. Los filtros se cruzan entre sí: cuanto más agregue, más pequeño será el segmento." />
      </section>
    );
  }

  return (
    <section className="resultados" id="resultados" aria-labelledby="titulo-resultados">
      <div className="resultados__cabecera">
        <div className="resultados__titulo">
          <p className="kicker">Paso 3 · Resultados</p>
          <h2 id="titulo-resultados" tabIndex={-1}>
            <span className="dato">{datos.total.toLocaleString('es-CO')}</span> {datos.total === 1 ? 'empresa encontrada' : 'empresas encontradas'}
          </h2>
          <p className="resultados__resumen">
            Criterio: <strong>{datos.summary}</strong> · mostrando {desde.toLocaleString('es-CO')}–{hasta.toLocaleString('es-CO')} · ordenadas por ingresos operacionales
          </p>
        </div>
        <DescargaExcel solicitud={solicitud} total={datos.total} deshabilitado={Boolean(motivoDescarga) || cargando} motivo={motivoDescarga} unaEmpresa={datos.total === 1} />
      </div>

      <div className="resultados__avisos">
        {sucio && <Aviso tipo="advertencia">Cambió los criterios de búsqueda. Los resultados en pantalla corresponden a la consulta anterior; pulse «Buscar» para actualizarlos.</Aviso>}
        {datos.preview_truncated && (
          <Aviso tipo="info">
            En pantalla se navegan las primeras {maxVistaPrevia.toLocaleString('es-CO')} empresas para mantener la respuesta ágil. Refine los filtros o descargue el archivo para trabajar el segmento completo.
          </Aviso>
        )}
        {datos.demo && <Aviso tipo="info">Modo de demostración: los registros son sintéticos y no corresponden a empresas reales.</Aviso>}
      </div>

      <TablaEmpresas
        columnas={datos.columns}
        filas={datos.rows}
        identidad={identidad}
        herramientas={
          <label className="selector-tamano">
            Por página
            <select value={datos.page_size} onChange={(evento) => alCambiarTamano(Number(evento.target.value))} disabled={cargando}>
              {TAMANOS.map((tamano) => (
                <option key={tamano} value={tamano}>
                  {tamano}
                </option>
              ))}
            </select>
          </label>
        }
        textoVacio="La búsqueda local sólo revisa las empresas de la página actual. Pruebe otra palabra o borre el texto."
      />

      {datos.page_count > 1 && (
        <nav className="paginacion" aria-label="Paginación de resultados">
          <button type="button" className="boton boton--fantasma boton--chico" disabled={cargando || datos.page <= 1} onClick={() => alPaginar(datos.page - 1)}>
            ← Anterior
          </button>
          <form
            className="paginacion__pagina"
            onSubmit={(evento) => {
              evento.preventDefault();
              const objetivo = Math.min(Math.max(1, Number(paginaEditada) || 1), datos.page_count);
              if (objetivo !== datos.page) alPaginar(objetivo);
              else setPaginaEditada(String(datos.page));
            }}
          >
            <span>Página</span>
            <input className="campo dato" inputMode="numeric" aria-label="Ir a la página" value={paginaEditada} onChange={(evento) => setPaginaEditada(evento.target.value.replace(/\D/g, ''))} onBlur={(evento) => evento.currentTarget.form?.requestSubmit()} />
            <span className="dato">/ {datos.page_count.toLocaleString('es-CO')}</span>
          </form>
          <button type="button" className="boton boton--fantasma boton--chico" disabled={cargando || datos.page >= datos.page_count} onClick={() => alPaginar(datos.page + 1)}>
            Siguiente →
          </button>
          {cargando && (
            <span className="paginacion__estado">
              <Spinner oscuro /> Cargando…
            </span>
          )}
        </nav>
      )}
    </section>
  );
}
