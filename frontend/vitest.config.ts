// Pruebas de la interfaz (vitest): parser SSE, contexto del hilo y tabla estándar.
// Reutiliza la configuración de Vite; se mantiene aparte para que `tsc -b` no
// tenga que conciliar los tipos de Vite 8 con los que empaqueta vitest.
import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config';

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.{ts,tsx}'],
      css: false,
    },
  }),
);
