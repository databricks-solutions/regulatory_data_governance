const THEME_KEY = 'rc18_theme';

function readInitialTheme() {
  if (typeof window === 'undefined') return 'light';
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch (_) {}
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark';
  return 'light';
}

export const appState = $state({
  // dataBase e dataBaseOptions são preenchidos em runtime a partir de
  // /dashboard/data-bases (último CADOC processado). Inicia vazio; o layout
  // resolve no onMount. Nada de meses hardcoded.
  dataBase: '',
  dataBaseOptions: [],
  sidebarCollapsed: false,
  theme: readInitialTheme(),
  user: {
    email: '',
    username: '',
    displayName: ''
  },
  alertCount: 0,
  // Optional per-page action button rendered in the global header. Pages
  // register it via setHeaderAction() onMount and clear it on destroy.
  // Shape: { label: string, onClick: () => void, title?: string } | null
  headerAction: null
});

export function setDataBase(value) {
  appState.dataBase = value;
}

// Preenche o seletor de Data-Base a partir do backend. `current` é o último
// CADOC processado (de gold.processing_state); `available` são as data-bases
// distintas observadas nas posições. Só sobrescreve a seleção atual se ela
// ainda não foi definida pelo usuário.
export function setDataBaseOptions({ current, available } = {}) {
  appState.dataBaseOptions = Array.isArray(available) ? available : [];
  if (!appState.dataBase && current) appState.dataBase = current;
}

export function toggleSidebar() {
  appState.sidebarCollapsed = !appState.sidebarCollapsed;
}

export function applyTheme(theme) {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-theme', theme);
  try { localStorage.setItem(THEME_KEY, theme); } catch (_) {}
}

export function toggleTheme() {
  appState.theme = appState.theme === 'light' ? 'dark' : 'light';
  applyTheme(appState.theme);
}

export function setUser(user) {
  appState.user = user;
}

export function setAlertCount(count) {
  appState.alertCount = count;
}

export function setHeaderAction(action) {
  appState.headerAction = action;
}
