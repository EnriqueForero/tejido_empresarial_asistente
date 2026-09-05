export type ModoBusqueda = 'filters' | 'business_name' | 'nit' | 'batch_nits';

export type DefinicionFiltro = {
  key: string;
  query_column?: string;
  label: string;
  group: string;
  help?: string;
  options?: string[];
  truncated?: boolean;
};

export type SolicitudBusqueda = {
  mode: ModoBusqueda;
  filters: Record<string, string[]>;
  term: string;
  nits: string[];
  page: number;
  page_size: number;
};

/** Una fila de resultados. Snowflake puede devolver booleanos además de texto y números. */
export type Fila = Record<string, string | number | boolean | null>;

export type RespuestaBusqueda = {
  total: number;
  page: number;
  page_size: number;
  page_count: number;
  preview_truncated: boolean;
  columns: string[];
  rows: Fila[];
  summary: string;
  demo: boolean;
};

export type Fuente = { name: string; detail: string; cut: string };

export type Metadatos = {
  title: string;
  version: string;
  demo: boolean;
  data_connection: 'demo' | 'configured' | 'missing_configuration' | 'connected' | 'error';
  preview_columns: string[];
  export_columns: string[];
  column_sections: Array<{ title: string; columns: string[] }>;
  sources: Fuente[];
  periods: Record<string, string>;
  notes: string[];
  filters: DefinicionFiltro[];
  filter_groups: string[];
  export_max_rows: number;
  preview_max_rows: number;
  batch_max_nits: number;
  contact_fields_included: boolean;
  /** NIT reales de ejemplo (chips, marcador del lote); sintéticos en modo demostración. */
  nit_examples: string[];
};

export type EntradaGlosario = {
  variable: string;
  description: string;
  description_paragraphs: string[];
  sources: string;
  category: string;
  in_export: boolean;
  in_preview: boolean;
  filter_key: string | null;
  filter_label: string | null;
  origin: 'glosario' | 'aplicativo';
};

export type RespuestaGlosario = {
  entries: EntradaGlosario[];
  count: number;
  institutional_count: number;
  supplementary_count: number;
  categories: string[];
  coverage: { export_columns: number; defined_export_columns: number; missing: string[] };
  updated_at: string;
  file_name: string;
};

export type Ficha = {
  nit: string;
  record: Fila;
  sections: Array<{ title: string; fields: Array<{ name: string; value: string | number | null }> }>;
  matches: number;
  demo: boolean;
};

export type Salud = {
  status: string;
  version: string;
  data_connection: Metadatos['data_connection'];
  access_control: 'basic' | 'open';
  frontend_built: boolean;
  demo_mode: boolean;
  snowflake: {
    connector_installed: boolean;
    connector_version: string | null;
    pandas_arrow: boolean;
    missing_variables: string[];
    key_sources: string[];
    connection_error: boolean;
    verified: boolean;
    verified_at: string | null;
  };
};

export type PasoDiagnostico = {
  paso: string;
  descripcion: string;
  ok: boolean;
  detalle?: unknown;
  error?: string;
  tipo_error?: string;
  segundos: number;
};

export type Diagnostico = {
  modo: 'demo' | 'snowflake';
  version?: string;
  todo_ok?: boolean;
  resumen: string;
  siguiente_paso: string;
  pasos: PasoDiagnostico[];
};

// ── Asistente de análisis (Snowflake Cortex) ───────────────────────────────

export type SugerenciaIA = { grupo: string; texto: string };

export type EstadoIA = {
  disponible: boolean;
  motivo: string;
  vista_semantica: string;
  modelo: string;
  advertencia: string;
  sugerencias: SugerenciaIA[];
  max_caracteres: number;
  /** NIT reales de ejemplo para la pregunta sugerida de ficha. */
  nit_ejemplo: string[];
  /** Cuántas preguntas anteriores recuerda el servidor al refinar. */
  memoria_turnos: number;
  /** Minutos que el servidor conserva un resultado para descargarlo. */
  resultado_minutos: number;
};

export type SerieGrafica = { nombre: string; color: string; valores: number[] };

export type EspecGrafica = {
  tipo: 'barras' | 'agrupadas' | 'apiladas' | 'lineas' | 'indicador';
  titulo: string;
  categorias: string[];
  series: SerieGrafica[];
  formato: 'entero' | 'decimal' | 'usd' | 'cop' | 'porcentaje';
  eje: string;
  nota: string;
};

export type MetaIA = {
  modelo: string;
  /** El texto es el resumen automático de los datos, no la redacción con IA. */
  degradado: boolean;
  /** 'redaccion_fallo' · 'respuesta_vacia' · 'cifras_sin_respaldo' · 'redaccion_pausada' · ''. */
  motivo_degradacion: string;
  /** Causa real, ya sin secretos, para no tener que abrir /estado ni los registros. */
  detalle_degradacion: string;
  cifras_verificadas: boolean;
  /** Con qué firma de COMPLETE se redactó ('opciones' | 'simple' | ''). */
  forma_redaccion: string;
  ms_interpretacion: number;
  ms_consulta: number;
  /** Segunda llamada a Analyst para corregir la consulta (0 si no hizo falta). */
  ms_correccion: number;
  ms_redaccion: number;
  ms_total: number;
  intentos_sql: number;
  analyst_request_id: string;
  version: string;
  vista_semantica: string;
};

/**
 * Tabla, gráfica y consulta de una respuesta. Viajan en el evento `resultado`
 * (en cuanto Snowflake responde) y se repiten en el `final` (con el texto).
 */
export type CuerpoResultadoIA = {
  consulta_id: string;
  sql: string;
  columnas: string[];
  /** Como máximo las primeras 500 filas; el servidor conserva todas para descargar. */
  filas: Array<Array<string | number | boolean | null>>;
  n_filas: number;
  truncado: boolean;
  grafica: EspecGrafica | null;
  /** La gráfica se abre sola: la pregunta la pidió o el resultado es un indicador. */
  mostrar_grafica: boolean;
  /** El resultado es un listado de empresas (columna NIT): tabla y descarga estándar. */
  es_listado: boolean;
  n_nits: number;
  sugerencias: string[];
  advertencia: string;
};

/** Evento del flujo SSE: avance por etapas, resultado, error o texto final. */
export type EventoIA =
  | { tipo: 'etapa'; consulta_id: string; etapa: string; detalle: string; ms?: number; sql?: string }
  | { tipo: 'error'; consulta_id?: string; mensaje: string }
  /**
   * Llega antes que el texto porque redactar es la parte lenta y no hay razón
   * para hacer esperar lo que ya está calculado.
   */
  | ({ tipo: 'resultado' } & CuerpoResultadoIA)
  | ({ tipo: 'final'; texto: string; meta: MetaIA } & CuerpoResultadoIA);

export type RespuestaIA = Extract<EventoIA, { tipo: 'final' }>;
