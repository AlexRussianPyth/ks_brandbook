# Бренд-кит «Каналсервис»

Машиночитаемый бренд компании: дизайн-токены (цвета, типографика) и векторные
ассеты (логотип, знак, графические элементы, узор), извлечённые из
`Kanalservice_guide.pdf`. Проекты подключают этот репозиторий как зависимость
и получают обновления бренда апдейтом пакета.

Полные смыслы и правила бренда (миссия, тональность, слоганы, примеры
применения) — в исходном `Kanalservice_guide.pdf`, это гайд по коду.

## Структура

```
tokens/tokens.json        Единый источник истины (W3C Design Tokens):
                          палитра с CMYK/Pantone/RAL, роли, шрифт Onest,
                          ограничения логотипа
dist/                     Генерируется из токенов (npm run build):
  tokens.css              CSS custom properties (--ks-*)
  tokens.scss             SCSS-переменные ($ks-*)
  index.js                ES-модуль с деревом токенов
  tailwind-preset.cjs/.mjs пресет для Tailwind
assets/svg/               Векторные ассеты (прозрачный фон)
assets/png/               Растровые фолбэки ×2
tools/build.mjs           Сборка dist/ из токенов (только Node, без зависимостей)
tools/extract_assets.py   Перегенерация SVG из PDF (pymupdf + numpy)
Kanalservice_guide.pdf    Исходный брендбук
```

## Подключение к проекту

Как git-зависимость (npm/pnpm/yarn — по аналогии):

```bash
npm install "git+ssh://git@github.com/AlexRussianPyth/ks_brandbook.git#v1.0.0"
# или просто за main: ...git#main
```

или скопировать `dist/` и `assets/` куда угодно — они самодостаточны.

## Использование

CSS:

```css
@import '@kanalservice/brand/css';

.button {
  background: var(--ks-role-accent);
  color: var(--ks-role-on-dark);
  font-family: var(--ks-font-family-base), sans-serif;
}
```

SCSS:

```scss
@use '@kanalservice/brand/scss' as ks;

.button {
  background: ks.$ks-role-accent;
}
```

JavaScript:

```js
import { tokens } from '@kanalservice/brand';

tokens.color['signal-blue']; // '#0041A0'
tokens.role.primary;         // '#0041A0' (ссылки разрешены)
```

Tailwind (`tailwind.config.js`):

```js
const brand = require('@kanalservice/brand/tailwind-preset');

module.exports = {
  presets: [brand],
  // colors.primary / colors.accent / colors['signal-blue'] / fontFamily.base ...
};
```

Шрифт **Onest** в пакет не входит — подключите сами (свободная лицензия OFL):
`https://fonts.google.com/specimen/Onest`.

## Ассеты (`assets/svg/`)

| Файл | Что это | Правила из брендбука |
|---|---|---|
| `logo-plate.svg` | Логотип: словесный знак на оранжевой плашке | Мин. высота 4 мм (`--ks-asset-logo-min-height`); плашка — неотъемлемая часть |
| `logo-with-descriptor.svg` | То же + дескриптор «Служба спасения канализации» | Дескриптор белый — размещать только на контрастном тёмном фоне |
| `sign.svg` | Знак «КС» | — |
| `element-plate.svg` | Графический элемент «Плашка» (голубой) | Подходит для акцентных кнопок |
| `element-oval.svg` | «Овал» (оранжевый) | — |
| `element-sparkle.svg` | «Блик» (две звёздочки) | — |
| `element-stream.svg` | «Ручеек» | — |
| `element-shield.svg` | «Щит» | Для патчей/нашивок |
| `pattern-waves.svg` | Фирменный узор (вода) | Цвета: `color.signal-blue` + `color.blue-bright` |

Знак ® — часть логотипа, его не отделяют и не перекрашивают.

В брендбуке есть ещё версии логотипа (в две строки, с люком, круглые,
монохром — стр. 22, 25); их можно извлечь тем же скриптом
`tools/extract_assets.py` при необходимости.

## Обновление бренда

1. Меняете значения в `tokens/tokens.json`.
2. `npm run build` — пересобирает `dist/`.
3. Поднимаете версию в `package.json`, тегируете, проекты обновляют зависимость.

Перегенерация ассетов из PDF (если брендбук обновился):

```bash
pip install -r tools/requirements.txt
npm run extract:assets   # пиксельная проверка результата встроена
```

## Лицензии

- Шрифт Onest — SIL Open Font License 1.1.
- Логотип, знак и фирменная графика — объекты прав «Каналсервис» (знак ®).
