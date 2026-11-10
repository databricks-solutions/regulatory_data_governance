const numberFmt = new Intl.NumberFormat('pt-BR');
const percentFmt = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const currencyFmt = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const dateFmt = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
const dateTimeFmt = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });

export function formatNumber(n) {
  if (n == null) return '-';
  return numberFmt.format(n);
}

export function formatPercent(n) {
  if (n == null) return '-';
  return percentFmt.format(n) + '%';
}

export function formatCurrency(n) {
  if (n == null) return '-';
  if (Math.abs(n) >= 1_000_000_000) return `R$ ${percentFmt.format(n / 1_000_000_000)}B`;
  if (Math.abs(n) >= 1_000_000) return `R$ ${percentFmt.format(n / 1_000_000)}M`;
  return currencyFmt.format(n);
}

export function formatDate(d) {
  if (!d) return '-';
  return dateFmt.format(new Date(d));
}

export function formatDateTime(d) {
  if (!d) return '-';
  return dateTimeFmt.format(new Date(d));
}

// Mês de referência `AAAA-MM` → "Abr 2026". `monthNames` vem do i18n
// (`$_('header.months').split(',')`).
export function formatMonth(ym, monthNames) {
  const [y, m] = String(ym || '').split('-');
  const name = monthNames?.[parseInt(m) - 1];
  return name ? `${name} ${y}` : ym || '';
}

// Data-base ISO (`AAAA-MM-DD`, já no fim do período) em `DD/MM/AAAA`. Por texto,
// não por Date: `new Date('2026-04-30')` é meia-noite UTC e vira 29/04 no Brasil.
export function formatDataBase(iso) {
  if (!iso) return '—';
  const [y, m, d] = String(iso).slice(0, 10).split('-');
  return d ? `${d}/${m}/${y}` : iso;
}
