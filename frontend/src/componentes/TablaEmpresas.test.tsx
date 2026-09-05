/**
 * La tabla estándar de empresas la comparten la sección de consulta y el
 * asistente: cada fila enlaza a la ficha por NIT, el NIT se muestra como texto
 * y el selector de columnas cuenta las disponibles.
 */
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { TablaEmpresas } from './TablaEmpresas';

describe('TablaEmpresas', () => {
  it('enlaza cada empresa a su ficha y conserva el NIT como texto', () => {
    render(
      <MemoryRouter>
        <TablaEmpresas
          columnas={['NIT', 'Razón social', 'Empleados']}
          filas={[
            { NIT: '900000001', 'Razón social': 'ACME S.A.S.', Empleados: 12 },
            { NIT: '900000002', 'Razón social': 'BETA LTDA', Empleados: 3 },
          ]}
          identidad="prueba"
        />
      </MemoryRouter>,
    );
    // La tabla (escritorio) y las tarjetas (móvil) se renderizan a la vez; ambas enlazan a la ficha.
    const enlaces = screen.getAllByRole('link', { name: 'ACME S.A.S.' });
    expect(enlaces.length).toBeGreaterThan(0);
    expect(enlaces[0].getAttribute('href')).toBe('/empresa/900000001');
    expect(screen.getAllByText('900000001').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Columnas · 3/ })).toBeTruthy();
  });
});
