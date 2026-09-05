/**
 * El contexto que viaja con cada pregunta decide qué recuerda el asistente:
 * sólo los últimos turnos con respuesta útil, nunca los fallidos ni los que
 * quedaron sin SQL, y siempre en pares usuario → analista.
 */
import { describe, expect, it } from 'vitest';
import type { MetaIA } from '../tipos';
import { contexto, type Turno } from './Asistente';

const META: MetaIA = {
  modelo: '', degradado: false, motivo_degradacion: '', cifras_verificadas: true, forma_redaccion: '',
  ms_interpretacion: 0, ms_consulta: 0, ms_correccion: 0, ms_redaccion: 0, ms_total: 0,
  intentos_sql: 0, analyst_request_id: '', version: '', vista_semantica: '',
};

function turno(id: number, pregunta: string, sql: string, error = ''): Turno {
  return {
    id, pregunta, error, detenido: false, descargando: '', errorDescarga: '', recordado: false,
    respuesta: sql
      ? {
          tipo: 'final', consulta_id: `id${id}`.padEnd(12, '0'), texto: 'ok', sql, columnas: [], filas: [], n_filas: 0,
          truncado: false, grafica: null, mostrar_grafica: false, es_listado: false, n_nits: 0, sugerencias: [], advertencia: '', meta: META,
        }
      : null,
  };
}

describe('contexto', () => {
  it('usa sólo los últimos n turnos con respuesta y omite los fallidos', () => {
    const turnos = [
      turno(1, 'a', 'SELECT 1'),
      turno(2, 'b', ''),
      turno(3, 'c', 'SELECT 3', 'Snowflake no pudo ejecutar la consulta'),
      turno(4, 'd', 'SELECT 4'),
      turno(5, 'e', 'SELECT 5'),
    ];
    const { consulta_ids, historial } = contexto(turnos, 2);
    expect(consulta_ids).toEqual(['id4000000000', 'id5000000000']);
    expect(historial).toEqual([
      { role: 'user', content: [{ type: 'text', text: 'd' }] },
      { role: 'analyst', content: [{ type: 'sql', statement: 'SELECT 4' }] },
      { role: 'user', content: [{ type: 'text', text: 'e' }] },
      { role: 'analyst', content: [{ type: 'sql', statement: 'SELECT 5' }] },
    ]);
  });

  it('sin turnos previos no envía nada', () => {
    expect(contexto([], 2)).toEqual({ consulta_ids: [], historial: [] });
  });
});
