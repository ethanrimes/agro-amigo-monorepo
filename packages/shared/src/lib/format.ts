export function formatCOP(value: number | null | undefined): string {
  if (value == null) return '\u2014';
  return new Intl.NumberFormat('es-CO', {
    style: 'currency',
    currency: 'COP',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatCOPCompact(value: number | null | undefined): string {
  if (value == null) return '\u2014';
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

export function formatPctChange(value: number | null | undefined): string {
  if (value == null) return '\u2014';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(1)}%`;
}

export function formatKg(value: number | null | undefined): string {
  if (value == null) return '\u2014';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M kg`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K kg`;
  return `${value.toFixed(0)} kg`;
}

export function formatDateShort(dateStr: string): string {
  const months = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const d = new Date(dateStr + 'T00:00:00');
  return `${d.getDate()} ${months[d.getMonth()]}`;
}

export function formatDateMedium(dateStr: string): string {
  const months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const d = new Date(dateStr + 'T00:00:00');
  return `${d.getDate()} de ${months[d.getMonth()]} ${d.getFullYear()}`;
}

export function formatPriceContext(presentation?: string | null, units?: string | null): string {
  const parts = [presentation, units].filter(Boolean);
  return parts.join(' \u00b7 ');
}

export function pctChange(oldVal: number, newVal: number): number {
  if (oldVal === 0) return 0;
  return ((newVal - oldVal) / oldVal) * 100;
}
