# Remotion: рендер роликов (с 2026-11-09 основной и единственный)

HyperFrames и `render_widgets.py` удалены. Вся картинка рисуется в `remotion/` (React + Remotion 4.0.542), в mp4 только командой, Studio не нужна.

## Как идёт рендер
```
spec-N.json + analysis-N.json -> script_gen.build_scenes (сценарий) -> widgets_plan.resolve (props) -> work-N/props.json
   -> npx remotion render src/index.ts Widgets silent.mp4 --props=props.json -> ffmpeg: звук -14 LUFS -> final.mp4 -> qa.py
```
`pipeline/render.py` делает это внутри `python -m pipeline.build out/<дата>`. Звук Remotion не трогает.

## Что где лежит
- `pipeline/widgets_plan.py` — выбор вида карточки, приложения, иконки, уведомления, тема, очистка рисунков `draw` (`svg_safe`). Чистая функция, тесты `tests/test_widgets_plan.py`.
- `remotion/src/widgets/Widgets.tsx` — раскладка: хук, остров, стопка карточек, шарики-связки, уведомления, смена темы, прогресс, финальная заставка.
- `remotion/src/widgets/Bodies.tsx` — картинка каждого вида (17: scene, counter, search, camera, chat, dots, versus, draw, pair, pulse, route, venn, ring, thermo, alert, target, polaroid) + анимация 15 заготовок `arts.generated.ts`.
- `remotion/src/widgets/anim.ts` — изинги и «твины» (то же, что раньше у GSAP): всё считается из времени кадра.
- `remotion/src/widgets/types.ts` — контракт props с Python (меняя поле, менять с обеих сторон).
- `remotion/src/Sansara.tsx`, `T9.tsx` — ролики, собранные вручную как образцы (светлый и тёмный стили). В пайплайн не входят.
- `remotion/scripts/transcribe.py` — whisper-строки для ручных роликов.

## Новый вид карточки
1. Python: добавить имя в `widget_kinds.NEW_KINDS` и таблицы `DEFAULT_APP` / `DEFAULT_NOTIFY` / `DEFAULT_TOAST`, поля описать в `docs/widgets-template.md`.
2. React: компонент в `Bodies.tsx` (820x340, время `u` — секунды от начала карточки, `d` — её длина), строка в `KINDS`.
3. Проверить: `npx remotion still Widgets out.png --frame=N --props=work-N/props.json`, склеить кадры (`ffmpeg ... hstack`) и посмотреть; `npx tsc --noEmit`.

## Установка с нуля
```bash
cd remotion && npm ci                     # node 22, ffmpeg в PATH; Chrome Headless Shell скачается при первом рендере
npx skills add remotion-dev/skills -y     # навыки Remotion (список в skills-lock.json, папка .agents/ не в git)
```
Версии закреплены: `remotion`, `@remotion/*` = 4.0.542, `@react-three/fiber@9` + `three@0.170.0` (React 19 не работает с fiber 8; `npx remotion add` падает, ставить через `npm i пакет@4.0.542`). В Actions: `npm ci` и `npx remotion browser ensure` в `remotion/` + системные библиотеки Chrome (см. `.github/workflows/generate.yml`; на Actions пока не запускалось).

## Ручной ролик (вне пайплайна)
1. Аудио из `audio/`, в `remotion/public/<name>.mp3` (mp3 в git не идёт); сам не скачивать.
2. Расшифровка: `.venv/Scripts/python.exe -I remotion/scripts/transcribe.py "audio/A - B.mp3" remotion/public/b-lyrics.json`, затем окно фрагмента моделью `large-v3` (`... b-refined.json large-v3 <от> <до>`). Читать только `*.txt` рядом (Read). Текст только из whisper.
3. Фрагмент 20–35 с, припев и законченная мысль. Карточки 6–10 по 2–4 с, один вид один раз, текста песни на экране нет, силуэты без лиц, без выдуманных цифр, концовка = титульная карта. Первый кадр = готовое превью.
4. Кадры: `npx remotion still <Comp> out.png --frame=N`; рендер: `npx remotion render <Comp> ../out/<дата>-<имя>/<name>.mp4 --codec=h264`.

## Что не автоматизировано
- Контраст и обрезка текста больше не проверяются автоматически (раньше `hyperframes check`): текст режется по длине в коде (`clip`), читаемость проверять по кадрам после правки шаблона.
- Звук ручных роликов: `qa.py` и нормализация −14 LUFS к ним не применяются, проверять на слух.
- Подписи и уведомления пишет Claude по смыслу, перечитывать.

## Уроки
- TikTok-ссылки `yt-dlp` не скачивает: референсы смотреть в Chrome (`claude-in-chrome`), 3–4 снимка через 3–4 с.
- Консоль Windows ломает кириллицу: результаты скриптов писать в UTF-8 файл и читать через Read; `-m pipeline.build` запускать без `-I`.
- `ThreeCanvas` ставить только внутри нужной карточки: 3D рендерится медленнее.
- Studio держит порт; закончив, остановить процесс.
