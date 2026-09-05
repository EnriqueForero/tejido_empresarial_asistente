/**
 * Formato de valores para pantalla (es-CO): separador de miles con punto,
 * decimales con coma, identificadores sin formato numérico.
 */
const entero = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 });
const decimal2 = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const decimal1 = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const PALABRAS_IDENTIFICADOR = ['NIT', 'Código', 'Dígito', 'ID del', 'posición arancelaria estrella'];

/**
 * Moneda por el nombre de la columna, no por una etiqueta exacta. El asistente
 * inventa alias («Total expo 5 anos USD», «expo_2025_usd») que no siguen la
 * convención de la sección de consulta («… (FOB USD)»), y sin esto se veían como
 * números sueltos junto a columnas hermanas ya formateadas.
 */
// El orden importa, y está escogido con nombres reales del modelo semántico:
// «PARTICIPACION_USD_PCT» es un porcentaje y no dólares; «Numero exportadoras»
// es un conteo de empresas y no dólares, aunque contenga «expo»; «EXPO_2025» sí
// son dólares. Gemela de `backend/ia/forma.clase_de_cifra`.
const PORCENTAJE = /\bPCT\b|PORCENTAJE|POBREZA|INFORMALIDAD|%/i;
const CONTEO = /^(NUMERO|CANTIDAD|CONTEO|TOTAL EMPRESAS)\b|EXPORTADOR[A-Z]*/i;
const DOLARES = /\b(USD|FOB|EXPO)\b|EXPORTACION[A-Z]*/i;
const PESOS = /\bCOP\b/i;
// El guion bajo cuenta como letra para \b, así que un alias crudo como
// «expo_2025_usd» no se reconocería sin separarlo primero.
const enPalabras = (columna: string) => columna.replace(/_/g, ' ');

export type ClaseDeCifra = 'identificador' | 'porcentaje' | 'usd' | 'cop' | 'numero';

/**
 * Con qué formato se escribe un número de esa columna. Es la regla gemela de
 * `backend/ia/forma.clase_de_cifra`: la tabla, el Excel y el resumen automático
 * tienen que decir la misma unidad sobre el mismo número.
 */
export function claseDeCifra(columna: string): ClaseDeCifra {
  if (PALABRAS_IDENTIFICADOR.some((palabra) => columna.includes(palabra))) return 'identificador';
  const palabras = enPalabras(columna).trim();
  if (PORCENTAJE.test(palabras)) return 'porcentaje';
  if (CONTEO.test(palabras)) return 'numero';
  if (DOLARES.test(palabras)) return 'usd';
  if (PESOS.test(palabras)) return 'cop';
  return 'numero';
}

export const esIdentificador = (columna: string) => claseDeCifra(columna) === 'identificador';
export const esMonetaria = (columna: string) => claseDeCifra(columna) === 'usd' || claseDeCifra(columna) === 'cop';
export const esNumericaVisual = (columna: string, valor: unknown) => typeof valor === 'number' && !esIdentificador(columna);

export function formatearValor(valor: unknown, columna: string): string {
  if (valor === null || valor === undefined || valor === '') return '—';
  // Una columna booleana de Snowflake se lee como el resto de las de sí/no.
  if (typeof valor === 'boolean') return valor ? 'Sí' : 'No';
  if (typeof valor === 'number') {
    const clase = claseDeCifra(columna);
    if (clase === 'identificador') return String(valor);
    if (clase === 'porcentaje') return `${decimal2.format(valor)} %`;
    if (clase === 'usd') return `USD ${decimal2.format(valor)}`;
    if (clase === 'cop') return `$ ${entero.format(valor)}`;
    if (columna === 'Antigüedad de la empresa (años)') return decimal1.format(valor);
    if (columna.includes('Índice')) return decimal2.format(valor);
    if (columna.includes('Distancia')) return valor.toFixed(4).replace('.', ',');
    return Number.isInteger(valor) ? entero.format(valor) : decimal2.format(valor);
  }
  return String(valor);
}

/** Cifra abreviada legible en español: 8,4 M · 998 k · 257.716 millones. */
export function abreviar(valor: number, estilo: 'M' | 'millones' = 'M'): string {
  const abs = Math.abs(valor);
  if (estilo === 'millones') {
    if (abs >= 1e12) return `${decimal1.format(valor / 1e12)} billones`;
    if (abs >= 1e9) return `${entero.format(Math.round(valor / 1e6))} millones`;
    if (abs >= 1e7) return `${decimal1.format(valor / 1e6)} millones`;
    if (abs >= 1e6) return `${decimal2.format(valor / 1e6)} millones`;
    return entero.format(valor);
  }
  if (abs >= 1e9) return `${decimal1.format(valor / 1e9)} mil M`;
  if (abs >= 1e6) return `${decimal1.format(valor / 1e6)} M`;
  if (abs >= 1e3) return `${entero.format(Math.round(valor / 1e3))} k`;
  return entero.format(valor);
}

/** Versión corta para tarjetas y cifras destacadas. */
export function formatearCompacto(valor: unknown, columna: string): string {
  if (typeof valor !== 'number') return formatearValor(valor, columna);
  const clase = claseDeCifra(columna);
  if (clase === 'usd') return valor === 0 ? 'USD 0' : `USD ${abreviar(valor)}`;
  if (clase === 'cop') return `$ ${abreviar(valor, 'millones')}`;
  return formatearValor(valor, columna);
}

export const formatearEntero = (valor: number) => entero.format(valor);

/** Etiqueta corta de columna para encabezados de tabla y tarjetas. */
export function etiquetaCorta(columna: string): string {
  return columna
    .replace('Exportaciones totales de la empresa ', 'Exportaciones ')
    .replace(' - Actividad principal', ' · act. principal')
    .replace('Rev 4', 'Rev. 4')
    .replace('Descripción CIIU', 'Actividad CIIU');
}

export function limpiarNit(valor: string): string {
  return valor.replace(/\D/g, '');
}

/** Fecha y hora local legible a partir de un ISO 8601 (para la página de estado). */
export function fechaHora(iso: string): string {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return fecha.toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' });
}
