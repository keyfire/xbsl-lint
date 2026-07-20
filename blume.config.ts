// Конфигурация сайта документации (Blume, движок на Astro + Vite). Публикация на
// GitHub Pages из .github/workflows/docs.yml. Контент лежит в docs/ парами
// Имя.md + Имя.ru.md (суффиксный режим i18n parser: "dot" — та же раскладка файлов,
// что была при mkdocs). Локальная проверка сборки: npx blume build.
import { defineConfig } from "blume";

export default defineConfig({
  title: "XBSL (1C:Element)",
  description:
    "A linter with autofixes, an LSP server, documentation search and metadata " +
    "scaffolding for 1C:Element (XBSL) sources, plus a VS Code extension built on " +
    "the same engine.",

  // Весь контент сайта — в docs/. Страница расширения (docs/vscode.md + .ru.md) —
  // зеркало editors/vscode/README.md (README маркетплейса); синхронизируется скриптом
  // scripts/sync-vscode-doc.mjs (npm run sync:docs).
  content: {
    root: "docs",
  },

  // GitHub Pages проекта отдаётся с подпути /xbsl/: base переносит туда весь сайт и
  // переписывает внутренние ссылки и ассеты; site — origin для sitemap/canonical/OG.
  deployment: {
    base: "/xbsl",
    site: "https://keyfire.github.io",
  },

  // Репозиторий: ссылки «Edit on GitHub» под каждой страницей и иконка репозитория в шапке.
  github: {
    owner: "keyfire",
    repo: "xbsl",
  },

  // Дата «последнее изменение» из истории git (в CI нужен fetch-depth: 0).
  lastModified: true,

  // Двуязычие: английский по умолчанию (файлы Имя.md в корне docs/), русский — суффикс
  // .ru (файлы Имя.ru.md). parser: "dot" сохраняет исходную раскладку пар без переноса
  // файлов. Русский UI-пакет (поиск, «На этой странице», «Изменить на GitHub» и прочее)
  // встроен в Blume — переводим только контент.
  i18n: {
    defaultLocale: "en",
    locales: [
      { code: "en", label: "English" },
      { code: "ru", label: "Русский" },
    ],
    parser: "dot",
  },

  // Гайд для контрибьюторов живёт на GitHub (не страница сайта) — закрепляем над
  // сайдбаром. Расширение VS Code теперь отдельная страница сайта (docs/vscode.md),
  // поэтому его в featured не дублируем — оно появляется в сайдбаре само.
  navigation: {
    featured: [
      {
        label: "Contributing",
        href: "https://github.com/keyfire/xbsl/blob/main/CONTRIBUTING.md",
        icon: "git-pull-request",
      },
    ],
  },

  // Индиго — как в теме Material у прежнего сайта.
  theme: {
    accent: "indigo",
  },
});
