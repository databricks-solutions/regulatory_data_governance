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

export function formatDataBase(db) {
  if (!db) return '-';
  const [y, m] = db.split('-');
  const months = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
  return `${months[parseInt(m) - 1]}/${y}`;
}
