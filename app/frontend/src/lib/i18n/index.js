import { browser } from '$app/environment';
import { init, register, locale, locales } from 'svelte-i18n';

const STORAGE_KEY = 'rc18_locale';
export const DEFAULT_LOCALE = 'pt';

// Supported languages. `label` is shown in the language switcher (each in its
// own language). Order here drives the switcher order.
export const SUPPORTED_LOCALES = [
  { code: 'pt', label: 'Português', flag: '🇧🇷' },
  { code: 'en', label: 'English', flag: '🇬🇧' },
  { code: 'es', label: 'Español', flag: '🇪🇸' },
  { code: 'it', label: 'Italiano', flag: '🇮🇹' }
];

register('pt', () => import('./locales/pt.json'));
register('en', () => import('./locales/en.json'));
register('es', () => import('./locales/es.json'));
register('it', () => import('./locales/it.json'));

// Só a escolha EXPLÍCITA do usuário (localStorage) tira o app do pt-BR.
// Deliberadamente NÃO olhamos `navigator.language`: o idioma da UI é
// Portuguese-BR (terminologia BCB/SCR), então um navegador em inglês abrindo um
// deployment novo tem de ver pt-BR, não en. A detecção por navegador fazia o
// DEFAULT_LOCALE nunca valer para quem não usa o navegador em português.
function readInitialLocale() {
  if (!browser) return DEFAULT_LOCALE;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && SUPPORTED_LOCALES.some((l) => l.code === stored)) return stored;
  } catch (_) {}
  return DEFAULT_LOCALE;
}

init({
  fallbackLocale: DEFAULT_LOCALE,
  initialLocale: readInitialLocale()
});

// Persist the chosen locale and keep <html lang> in sync.
if (browser) {
  locale.subscribe((value) => {
    if (!value) return;
    try { localStorage.setItem(STORAGE_KEY, value); } catch (_) {}
    document.documentElement.setAttribute('lang', value === 'pt' ? 'pt-BR' : value);
  });
}

export function setLocale(code) {
  if (SUPPORTED_LOCALES.some((l) => l.code === code)) locale.set(code);
}

export { locale, locales };
