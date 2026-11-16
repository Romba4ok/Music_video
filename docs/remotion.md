# Remotion: рендер роликов (с 2026-11-09 основной и единственный)

HyperFrames и `render_widgets.py` удалены. Вся картинка рисуется в `remotion/` (React + Remotion 4.0.542), в mp4 только командой, Studio не нужна.

## Как идёт рендер
```
spec-N.json + analysis-N.json -> script_gen.build_scenes (сценарий) -> widgets_plan.resolve (props) -> work-N/props.json
   -> npx remotion render src/index.ts Widgets silent.mp4 --props=props.json -> ffmpeg: звук -14 LUFS -> final.mp4 -> qa.py
```
`pipeline/render.py` делает это внутри `python -m pipeline.build out/<дата>`. Звук Remotion не трогает. Рядом с `final.mp4` лежат `cover.png` (кадр на 1 с: хук и первая карточка) и `sheet.png` (8 кадров подряд) для быстрого просмотра.
Карточки меняются на ближайшем бите, если он ближе `config.json → beat_snap_sec` (0.18 с; 0 отключает): `widgets_plan.snap_to_beats`.

## Что где лежит
- `pipeline/widgets_plan.py` — выбор вида карточки, приложения, иконки, уведомления, тема, очистка рисунков `draw` (`svg_safe`). Чистая функция, тесты `tests/test_widgets_plan.py`.
- `remotion/src/widgets/Widgets.tsx` — раскладка: хук, остров, стопка карточек, шарики-связки, уведомления, смена темы, прогресс, финальная заставка.
- `remotion/src/widgets/Bodies.tsx` — единственный вид, картинка `draw` (SVG Claude + твины); строка без картинки получает простую панель. Старые шаблонные карточки (счётчик, поиск, чат, пара, пульс, маршрут, кольцо и т.д.) удалены 2026-11-09, а 8 готовых анимированных сцен (`weather`, `typing`, `bloom`, `duo`, `breath`, `deep`, `unlock`, `night`, файл `Scenes.tsx`) 2026-11-16, оба раза по решению владельца: готовые картинки не должны возвращаться.
- `remotion/src/widgets/shapes.tsx` — общие силуэты (нужны ручному ролику `Sansara.tsx`).
- Петля: последние 0.5 с растворяются в первый кадр (`LOOP_S` в `Widgets.tsx`); первая карточка стоит на месте уже на кадре 0, её картинка сдвинута на 0.9 с вперёд (кадр 0 годится как превью). Ярлык серии `config.json → series` под хуком и на финальной карте.
- `remotion/src/widgets/anim.ts` — изинги и «твины» (то же, что раньше у GSAP): всё считается из времени кадра.
- `remotion/src/widgets/types.ts` — контракт props с Python (меняя поле, менять с обеих сторон).
- `remotion/src/Sansara.tsx`, `T9.tsx` — ролики, собранные вручную как образцы (светлый и тёмный стили). В пайплайн не входят.
- `remotion/scripts/transcribe.py` — whisper-строки для ручных роликов.

## Новый вид карточки
Готовых видов нет и добавлять их не нужно (решение владельца 2026-11-16): картинку к строке рисует автор как `draw`. Если вид всё же понадобится, это решение владельца: `widgets_plan.KINDS`, `widget_kinds.DEFAULT_APP`, `Bodies.tsx`, `prompts/*.md`, `docs/widgets-template.md`.
Проверка рендера: `npx remotion still Widgets out.png --frame=N --props=work-N/props.json`, склеить кадры (`ffmpeg ... hstack`) и посмотреть; `npx tsc --noEmit`.

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

## Автоматическая проверка движения
`qa.cards_move`: на каждой карточке сравниваются два кадра с интервалом 0.5 с в области картинки; карточка «почти стоит», если среднее изменение < `STILL_DIFF` (3 из 255). FAIL, если таких больше четверти. Это ловит слайд-шоу из кадров и забытые анимации. Карточка короче 1 с не проверяется. Поверх любого вида кадр сам никогда не стоит: медленный наезд, лёгкий наклон и «хлопок» с искрами каждые 1.1 с (`pop` в `Widgets.tsx`), а у каждого вида есть цикл, который идёт до конца карточки.

## Темп
Промпт просит карточки по 1.5–3 с (11–14 на 26 с) и новое действие в картинке примерно раз в секунду. Ролик Т9 в пайплайне: 12 карточек, в среднем 2.2 с.

## Учёт результатов
`accounts/<acc>/cards.jsonl` пишет для каждого ролика хук, вид хука (вопрос), темы, виды карточек, долю анимированных (`anim_share`), `renderer`. Просмотры вносить в `accounts/<acc>/views.csv` (`song,views`), затем `python -m pipeline insights`: таблица по признакам, выводы только от 5 роликов.

## Что не автоматизировано
- Контраст и обрезка текста больше не проверяются автоматически (раньше `hyperframes check`): текст режется по длине в коде (`clip`), читаемость проверять по кадрам после правки шаблона.
- Звук ручных роликов: `qa.py` и нормализация −14 LUFS к ним не применяются, проверять на слух.
- Подписи и уведомления пишет Claude по смыслу, перечитывать.

## Уроки
- TikTok-ссылки `yt-dlp` не скачивает: референсы смотреть в Chrome (`claude-in-chrome`), 3–4 снимка через 3–4 с.
- Консоль Windows ломает кириллицу: результаты скриптов писать в UTF-8 файл и читать через Read; `-m pipeline.build` запускать без `-I`.
- `ThreeCanvas` ставить только внутри нужной карточки: 3D рендерится медленнее.
- Studio держит порт; закончив, остановить процесс.
