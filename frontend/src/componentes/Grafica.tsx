/**
 * Gráfica del asistente, dibujada en SVG sobre el sistema de diseño del
 * aplicativo (sin librerías externas ni CDN).
 *
 * El servidor decide qué forma corresponde (`backend/ia/graficos.py`); aquí sólo
 * se dibuja. Las reglas que se respetan, en orden:
 *
 * - una sola medida se pinta de un solo tono: la longitud de la barra ya codifica
 *   la magnitud y teñirla por valor sería repetir la misma información;
 * - con dos o más series hay leyenda siempre, y hasta cuatro llevan además la
 *   cifra escrita: la identidad nunca depende sólo del color;
 * - los colores salen de una paleta validada para daltonismo y contraste;
 * - la rejilla y los ejes son discretos, y la tabla de abajo es la fuente exacta.
 */
import { useId, useState } from 'react';
import type { EspecGrafica } from '../tipos';
import { abreviar, formatearEntero } from '../formato';

const ALTURA_BARRA = 26;
const SEPARACION_GRUPO = 14;
const HUECO = 2; // separación entre rellenos contiguos, en píxeles de superficie
const RADIO = 4; // extremo redondeado del dato
const MARGEN = { arriba: 18, derecha: 78, abajo: 34, izquierda: 168 };
const MAX_ETIQUETA = 26;

type Punto = { x: number; y: number; texto: string };

function formatear(valor: number, formato: EspecGrafica['formato']): string {
  if (formato === 'porcentaje') return `${valor.toFixed(1).replace('.', ',')} %`;
  if (formato === 'usd') return `USD ${abreviar(valor)}`;
  if (formato === 'cop') return `$ ${abreviar(valor, 'millones')}`;
  return formatearEntero(valor);
}

function recortar(texto: string): string {
  return texto.length > MAX_ETIQUETA ? `${texto.slice(0, MAX_ETIQUETA - 1)}…` : texto;
}

/** Ticks «redondos» para el eje de valores. */
function escalaMaxima(maximo: number): number {
  if (maximo <= 0) return 1;
  const magnitud = 10 ** Math.floor(Math.log10(maximo));
  for (const paso of [1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10]) {
    if (magnitud * paso >= maximo) return magnitud * paso;
  }
  return magnitud * 10;
}

function Leyenda({ espec }: { espec: EspecGrafica }) {
  if (espec.series.length < 2) return null;
  return (
    <ul className="grafica__leyenda">
      {espec.series.map((serie) => (
        <li key={serie.nombre}>
          <span className="grafica__muestra" style={{ background: serie.color }} aria-hidden="true" />
          {serie.nombre}
        </li>
      ))}
    </ul>
  );
}

function Indicador({ espec }: { espec: EspecGrafica }) {
  const valor = espec.series[0]?.valores[0] ?? 0;
  return (
    <figure className="grafica grafica--indicador">
      <div className="grafica__cifra">{formatear(valor, espec.formato)}</div>
      <figcaption className="grafica__pie">{espec.titulo}</figcaption>
    </figure>
  );
}

/** Barras horizontales: una serie (un tono) o varias (apiladas o agrupadas). */
function Barras({ espec, apiladas }: { espec: EspecGrafica; apiladas: boolean }) {
  const id = useId();
  const [encima, setEncima] = useState<Punto | null>(null);
  const categorias = espec.categorias;
  const series = espec.series;
  const porGrupo = apiladas ? 1 : series.length;
  const altoBarra = porGrupo > 1 ? Math.max(12, ALTURA_BARRA / porGrupo + 2) : ALTURA_BARRA;
  const altoGrupo = altoBarra * porGrupo + SEPARACION_GRUPO;
  const alto = MARGEN.arriba + altoGrupo * categorias.length + MARGEN.abajo;
  const ancho = 760;
  const anchoUtil = ancho - MARGEN.izquierda - MARGEN.derecha;

  const totales = categorias.map((_, indice) =>
    apiladas ? series.reduce((suma, serie) => suma + (serie.valores[indice] ?? 0), 0) : Math.max(...series.map((serie) => serie.valores[indice] ?? 0)),
  );
  const tope = escalaMaxima(Math.max(...totales, 0));
  const escala = (valor: number) => (valor / tope) * anchoUtil;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((fraccion) => fraccion * tope);
  const etiquetarValor = series.length <= 4;

  return (
    <figure className="grafica">
      <svg
        viewBox={`0 0 ${ancho} ${alto}`}
        role="img"
        aria-labelledby={`${id}-titulo`}
        className="grafica__lienzo"
        onMouseLeave={() => setEncima(null)}
      >
        <title id={`${id}-titulo`}>{espec.titulo}</title>

        {/* Rejilla discreta y eje de valores */}
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={MARGEN.izquierda + escala(tick)}
              x2={MARGEN.izquierda + escala(tick)}
              y1={MARGEN.arriba - 6}
              y2={alto - MARGEN.abajo}
              className="grafica__rejilla"
            />
            <text x={MARGEN.izquierda + escala(tick)} y={alto - MARGEN.abajo + 16} className="grafica__tick" textAnchor="middle">
              {formatear(tick, espec.formato)}
            </text>
          </g>
        ))}

        {categorias.map((categoria, indice) => {
          const yGrupo = MARGEN.arriba + altoGrupo * indice;
          let acumulado = 0;
          return (
            <g key={categoria}>
              <text x={MARGEN.izquierda - 10} y={yGrupo + (altoBarra * porGrupo) / 2 + 4} className="grafica__categoria" textAnchor="end">
                {recortar(categoria)}
                <title>{categoria}</title>
              </text>
              {series.map((serie, orden) => {
                const valor = serie.valores[indice] ?? 0;
                const largo = Math.max(0, escala(valor));
                const x = apiladas ? MARGEN.izquierda + escala(acumulado) + (acumulado > 0 ? HUECO : 0) : MARGEN.izquierda;
                const y = apiladas ? yGrupo : yGrupo + altoBarra * orden;
                if (apiladas) acumulado += valor;
                const anchoBarra = Math.max(0, apiladas ? largo - (acumulado > valor ? HUECO : 0) : largo);
                return (
                  <rect
                    key={serie.nombre}
                    x={x}
                    y={y + HUECO / 2}
                    width={anchoBarra}
                    height={Math.max(1, altoBarra - HUECO)}
                    rx={Math.min(RADIO, anchoBarra / 2)}
                    fill={serie.color}
                    onMouseEnter={() =>
                      setEncima({
                        x: x + anchoBarra,
                        y: y + altoBarra / 2,
                        texto: `${categoria} · ${serie.nombre}: ${formatear(valor, espec.formato)}`,
                      })
                    }
                  />
                );
              })}
              {etiquetarValor && (
                <text
                  x={MARGEN.izquierda + escala(totales[indice]) + (apiladas ? HUECO * series.length : 0) + 8}
                  y={yGrupo + (altoBarra * porGrupo) / 2 + 4}
                  className="grafica__valor"
                >
                  {formatear(totales[indice], espec.formato)}
                </text>
              )}
            </g>
          );
        })}

        {/* Línea base */}
        <line x1={MARGEN.izquierda} x2={MARGEN.izquierda} y1={MARGEN.arriba - 6} y2={alto - MARGEN.abajo} className="grafica__eje" />
        {encima && (() => {
          const anchoGlobo = Math.min(360, 16 + encima.texto.length * 6.2);
          const x = Math.max(4, Math.min(encima.x + 8, ancho - anchoGlobo - 4));
          return (
            <g className="grafica__globo" pointerEvents="none">
              <rect x={x} y={encima.y - 26} width={anchoGlobo} height={22} rx={5} />
              <text x={x + 8} y={encima.y - 11}>
                {encima.texto}
              </text>
            </g>
          );
        })()}
      </svg>
      <Leyenda espec={espec} />
      {espec.nota && <figcaption className="grafica__pie">{espec.nota}</figcaption>}
    </figure>
  );
}

function Lineas({ espec }: { espec: EspecGrafica }) {
  const id = useId();
  const ancho = 760;
  const alto = 300;
  const margen = { arriba: 20, derecha: 24, abajo: 46, izquierda: 86 };
  const anchoUtil = ancho - margen.izquierda - margen.derecha;
  const altoUtil = alto - margen.arriba - margen.abajo;
  const maximo = escalaMaxima(Math.max(...espec.series.flatMap((serie) => serie.valores), 0));
  const paso = espec.categorias.length > 1 ? anchoUtil / (espec.categorias.length - 1) : 0;
  const x = (indice: number) => margen.izquierda + paso * indice;
  const y = (valor: number) => margen.arriba + altoUtil - (valor / maximo) * altoUtil;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((fraccion) => fraccion * maximo);

  return (
    <figure className="grafica">
      <svg viewBox={`0 0 ${ancho} ${alto}`} role="img" aria-labelledby={`${id}-titulo`} className="grafica__lienzo">
        <title id={`${id}-titulo`}>{espec.titulo}</title>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={margen.izquierda} x2={ancho - margen.derecha} y1={y(tick)} y2={y(tick)} className="grafica__rejilla" />
            <text x={margen.izquierda - 10} y={y(tick) + 4} className="grafica__tick" textAnchor="end">
              {formatear(tick, espec.formato)}
            </text>
          </g>
        ))}
        {espec.categorias.map((categoria, indice) => (
          <text key={categoria} x={x(indice)} y={alto - margen.abajo + 20} className="grafica__tick" textAnchor="middle">
            {recortar(categoria).slice(0, 14)}
          </text>
        ))}
        {espec.series.map((serie) => (
          <g key={serie.nombre}>
            <polyline
              points={serie.valores.map((valor, indice) => `${x(indice)},${y(valor)}`).join(' ')}
              fill="none"
              stroke={serie.color}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {serie.valores.map((valor, indice) => (
              <circle key={indice} cx={x(indice)} cy={y(valor)} r={4.5} fill={serie.color} stroke="var(--blanco, #fff)" strokeWidth={2}>
                <title>{`${espec.categorias[indice]} · ${serie.nombre}: ${formatear(valor, espec.formato)}`}</title>
              </circle>
            ))}
          </g>
        ))}
        <line x1={margen.izquierda} x2={ancho - margen.derecha} y1={y(0)} y2={y(0)} className="grafica__eje" />
      </svg>
      <Leyenda espec={espec} />
      {espec.nota && <figcaption className="grafica__pie">{espec.nota}</figcaption>}
    </figure>
  );
}

export function Grafica({ espec }: { espec: EspecGrafica }) {
  if (!espec.series.length || !espec.categorias.length) return null;
  if (espec.tipo === 'indicador') return <Indicador espec={espec} />;
  if (espec.tipo === 'lineas') return <Lineas espec={espec} />;
  return <Barras espec={espec} apiladas={espec.tipo === 'apiladas'} />;
}
