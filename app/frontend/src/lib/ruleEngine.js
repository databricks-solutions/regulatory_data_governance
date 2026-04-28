/**
 * Rule Engine client-side utilities.
 * Converts structured definitions to PySpark expressions and handles parameter resolution.
 */

const OPERATOR_MAP = {
  IS_NOT_NULL: (col) => `${col} IS NOT NULL`,
  IS_NULL: (col) => `${col} IS NULL`,
  EQUALS: (col, val, isCol) => isCol ? `${col} = ${val}` : `${col} = '${val}'`,
  NOT_EQUALS: (col, val, isCol) => isCol ? `${col} != ${val}` : `${col} != '${val}'`,
  GREATER_THAN: (col, val, isCol) => `${col} > ${isCol ? val : val}`,
  GREATER_THAN_OR_EQUALS: (col, val, isCol) => `${col} >= ${isCol ? val : val}`,
  LESS_THAN: (col, val, isCol) => `${col} < ${isCol ? val : val}`,
  LESS_THAN_OR_EQUALS: (col, val, isCol) => `${col} <= ${isCol ? val : val}`,
  BETWEEN: (col, val) => `${col} BETWEEN ${val[0]} AND ${val[1]}`,
  IN: (col, val) => `${col} IN (${val.map(v => `'${v}'`).join(', ')})`,
  NOT_IN: (col, val) => `${col} NOT IN (${val.map(v => `'${v}'`).join(', ')})`,
  MATCHES_REGEX: (col, val) => `${col} RLIKE '${val}'`,
  LENGTH_EQUALS: (col, val) => `LENGTH(${col}) = ${val}`,
  LENGTH_BETWEEN: (col, val) => `LENGTH(${col}) BETWEEN ${val[0]} AND ${val[1]}`,
  IS_UNIQUE: (col) => `/* UNIQUE check on ${col} */`
};

/**
 * Convert a structured definition JSON to a human-readable expression string.
 */
export function structuredToExpression(definition) {
  if (!definition?.conditions?.length) return '';

  const parts = definition.conditions.map(cond => {
    const col = cond.column;
    const op = cond.operator;
    const val = cond.value;
    const isCol = cond.value_is_column;
    const fn = OPERATOR_MAP[op];
    if (!fn) return `/* unknown operator: ${op} */`;
    return fn(col, val, isCol);
  });

  const joiner = definition.operator === 'OR' ? ' OR ' : ' AND ';
  return parts.join(joiner);
}

/**
 * Replace {placeholder} tokens with actual column names from bindings.
 */
export function resolveExpression(expression, columnBindings) {
  if (!expression || !columnBindings) return expression || '';
  let resolved = expression;
  for (const [placeholder, columnName] of Object.entries(columnBindings)) {
    resolved = resolved.replaceAll(`{${placeholder}}`, columnName);
  }
  return resolved;
}

/**
 * Detect {placeholder} tokens in an expression string.
 * Returns array of placeholder names (without braces).
 */
export function detectParameters(expression) {
  if (!expression) return [];
  const matches = expression.match(/\{([^}]+)\}/g);
  if (!matches) return [];
  const unique = [...new Set(matches.map(m => m.slice(1, -1)))];
  return unique;
}

/** All supported operators with metadata for the UI builder. */
export const OPERATORS = [
  { value: 'IS_NOT_NULL', label: 'Nao e nulo', needsValue: false },
  { value: 'IS_NULL', label: 'E nulo', needsValue: false },
  { value: 'EQUALS', label: 'Igual a', needsValue: true, supportsColumn: true },
  { value: 'NOT_EQUALS', label: 'Diferente de', needsValue: true, supportsColumn: true },
  { value: 'GREATER_THAN', label: 'Maior que', needsValue: true, supportsColumn: true },
  { value: 'GREATER_THAN_OR_EQUALS', label: 'Maior ou igual a', needsValue: true, supportsColumn: true },
  { value: 'LESS_THAN', label: 'Menor que', needsValue: true, supportsColumn: true },
  { value: 'LESS_THAN_OR_EQUALS', label: 'Menor ou igual a', needsValue: true, supportsColumn: true },
  { value: 'BETWEEN', label: 'Entre', needsValue: true, valueCount: 2 },
  { value: 'IN', label: 'Esta em (lista)', needsValue: true, isList: true },
  { value: 'NOT_IN', label: 'Nao esta em (lista)', needsValue: true, isList: true },
  { value: 'MATCHES_REGEX', label: 'Corresponde a regex', needsValue: true },
  { value: 'LENGTH_EQUALS', label: 'Tamanho igual a', needsValue: true },
  { value: 'LENGTH_BETWEEN', label: 'Tamanho entre', needsValue: true, valueCount: 2 },
  { value: 'IS_UNIQUE', label: 'Valores unicos', needsValue: false }
];

export const NIVELS = [
  { value: 1, label: 'N1 — Verificações básicas' },
  { value: 2, label: 'N2 — Coerência temporal' },
  { value: 3, label: 'N3 — Regras negociais' }
];

export const RULE_TYPES = [
  { value: 'syntactic', label: 'Sintática' },
  { value: 'semantic', label: 'Semântica' },
  { value: 'inter_document', label: 'Inter-documento' },
  { value: 'business', label: 'Regra Negocial' }
];

export const SEVERITIES = [
  { value: 'error', label: 'Error' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' }
];

export const DIMENSION_NAMES = [
  'Acessibilidade','Acuracia','Adaptabilidade','Clareza','Comparabilidade',
  'Completude','Confiabilidade','Consistencia','Integridade','Rastreabilidade',
  'Relevancia','Tempestividade'
];
