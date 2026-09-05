/**
 * El asistente inventa los nombres de sus columnas: «Total expo 5 anos USD» no
 * sigue la convención «… (FOB USD)» de la sección de consulta. El formato de
 * moneda se decide por el nombre, no por una etiqueta exacta.
 */
import { describe, expect, it } from 'vitest';
import { claseDeCifra, esMonetaria, formatearCompacto, formatearValor } from './formato';

describe('formatearValor', () => {
  it('da formato de dólares a cualquier columna que los nombre', () => {
    expect(formatearValor(52158504845.93, 'Total expo 5 anos USD')).toBe('USD 52.158.504.845,93');
    expect(formatearValor(9442341148.16, 'Exportaciones totales de la empresa 2021 (FOB USD)')).toBe('USD 9.442.341.148,16');
    expect(formatearValor(1000, 'expo_2025_usd')).toBe('USD 1.000,00');
  });

  it('da formato de pesos a las columnas en COP', () => {
    expect(formatearValor(104792323000, 'Ingresos operacionales (COP)')).toBe('$ 104.792.323.000');
    expect(formatearValor(5000, 'INGRESOS_COP')).toBe('$ 5.000');
  });

  it('no confunde identificadores ni texto con dinero', () => {
    expect(formatearValor(899999068, 'NIT')).toBe('899999068');
    expect(formatearValor(12, 'Empleados')).toBe('12');
    expect(formatearValor(true, '¿La empresa ha exportado?')).toBe('Sí');
    expect(formatearValor(null, 'Sector estrella')).toBe('—');
    expect(esMonetaria('Sector estrella')).toBe(false);
    expect(esMonetaria('Total expo 5 anos USD')).toBe(true);
  });
});

describe('claseDeCifra — la misma regla que backend/ia/forma.clase_de_cifra', () => {
  it('clasifica identificador, dólares, pesos y número suelto', () => {
    expect(claseDeCifra('NIT')).toBe('identificador');
    expect(claseDeCifra('Código CIIU Rev 4 - Actividad principal')).toBe('identificador');
    expect(claseDeCifra('Total expo 5 anos USD')).toBe('usd');
    expect(claseDeCifra('Exportaciones totales de la empresa 2021 (FOB USD)')).toBe('usd');
    expect(claseDeCifra('Ingresos operacionales (COP)')).toBe('cop');
    expect(claseDeCifra('Empleados')).toBe('numero');
  });

  it('el NIT nunca se abrevia ni se separa en miles', () => {
    expect(formatearCompacto(899999068, 'NIT')).toBe('899999068');
    expect(formatearCompacto(52158504845.93, 'Total expo 5 anos USD')).toBe('USD 52,2 mil M');
  });
});

describe('porcentajes y conteos', () => {
  it('un conteo de empresas exportadoras no son dólares', () => {
    // En producción la gráfica dibujaba «USD 3 k» sobre 3.340 empresas.
    expect(claseDeCifra('Numero exportadoras')).toBe('numero');
    expect(formatearValor(3340, 'Numero exportadoras')).toBe('3.340');
    expect(claseDeCifra('EXPO_2025')).toBe('usd');
  });

  it('un porcentaje lleva su símbolo, igual que en la gráfica', () => {
    expect(claseDeCifra('Promedio pobreza municipio')).toBe('porcentaje');
    expect(formatearValor(19.891126, 'Promedio pobreza municipio')).toBe('19,89 %');
    expect(formatearValor(12.35, 'PCT exportadoras')).toBe('12,35 %');
    // Un porcentaje con «USD» en el nombre sigue siendo un porcentaje.
    expect(claseDeCifra('PARTICIPACION_USD_PCT')).toBe('porcentaje');
  });
});
