/**
 * El lector SSE recibe el flujo en trozos arbitrarios: un evento puede llegar
 * partido en dos lecturas, y el servidor intercala comentarios (`: latido`)
 * para mantener viva la conexión. Nada de eso puede perder ni duplicar eventos.
 */
import { describe, expect, it } from 'vitest';
import { extraerEventosSse } from './api';

const RESULTADO =
  '{"tipo":"resultado","consulta_id":"abc123abc123","sql":"SELECT 1","columnas":["A"],"filas":[[1]],"n_filas":1,' +
  '"truncado":false,"grafica":null,"mostrar_grafica":false,"es_listado":false,"n_nits":0,"sugerencias":[],"advertencia":""}';

describe('extraerEventosSse', () => {
  it('entrega los eventos completos y conserva el trozo sin cerrar', () => {
    const primero = extraerEventosSse(
      'data: {"tipo":"etapa","consulta_id":"abc123abc123","etapa":"interpretando","detalle":"x"}\n\n: latido\n\ndata: ' +
        RESULTADO.slice(0, 40),
    );
    expect(primero.eventos).toHaveLength(1);
    expect(primero.eventos[0].tipo).toBe('etapa');
    expect(primero.resto).toBe('data: ' + RESULTADO.slice(0, 40));

    const segundo = extraerEventosSse(primero.resto + RESULTADO.slice(40) + '\n\n');
    expect(segundo.eventos).toHaveLength(1);
    expect(segundo.eventos[0].tipo).toBe('resultado');
    expect(segundo.resto).toBe('');
  });

  it('ignora los latidos y los bloques malformados sin perder los siguientes', () => {
    const { eventos, resto } = extraerEventosSse(': latido\n\ndata: {no es json}\n\ndata: {"tipo":"error","mensaje":"x"}\n\n');
    expect(eventos).toEqual([{ tipo: 'error', mensaje: 'x' }]);
    expect(resto).toBe('');
  });
});
