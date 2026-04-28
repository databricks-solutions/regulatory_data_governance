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
  dataBase: '2026-03',
  sidebarCollapsed: false,
  theme: readInitialTheme(),
  user: {
    email: '',
    username: '',
    displayName: ''
  },
  alertCount: 0
});

export function setDataBase(value) {
  appState.dataBase = value;
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
