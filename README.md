# Music Video Factory

Автоматический конвейер: песня → анализ текста и битов → вертикальное видео (HyperFrames) → QA → очередь TikTok через Buffer (официальный GraphQL API), 3 ролика в день.
Правила для Claude: `CLAUDE.md`. Права и источники: `docs/rights.md`.

## Шаблон
`config.json: style` = `widgets` (по умолчанию), формат «widget edit»: квадрат 1:1 с интерфейсом телефона посреди кадра 9:16, хук-вопрос в верхнем чёрном поле, заставка с обложкой и `автор: vybex` (`handle` в config), остров-плеер с эквалайзером, на каждую строку анимированная карточка (пара, пульс, маршрут, кольцо, прицел, поиск, чат и др.), уведомление в острове с каждой карточкой, плеер/прогресс внизу, финальная заставка. Движение: карточка качается на битах, стопка карточек, шарик-связка, вибрация, блики, ничто не стоит. `cards` — старый текстовый стиль. Подробно и как подбирать картинки под смысл: `docs/widgets-template.md`. Код: `pipeline/render_widgets.py`, `pipeline/widget_kinds.py`.

## Два режима
- **AUTO** (`with_audio`): звук из разрешённого источника (CC0/CC-BY или ваш файл) вшивается в mp4. `python -m pipeline batch --mode auto --count 3`
- **TIKTOK** (`tiktok`): mp4 без звука, тайминг под песню + `sync-N.txt` («поставьте звук с 1:02.40»); официальный звук добавляете в приложении TikTok. `python -m pipeline batch --mode tiktok --count 3`

Этапы независимы: `python -m pipeline fetch "…"` → `analyze <audio>` → `render out/<дата>`. Любой полученный легально mp4/mov/webm автоматически конвертируется в аудио через ffmpeg. Сбой одной песни или источника не останавливает пакет (`out/<дата>/report.json`). Расписание: `.github/workflows/generate.yml`, ежедневно в 03:00 UTC (08:00 Алматы) + ручной запуск; на push не запускается.

## Без терминала: Google Drive
Песни кладёте в `VYBEX/audio` на Диске, workflow по расписанию забирает их, делает ролики и кладёт в `VYBEX/ready/<дата>/` (mp4 + caption.txt + sync.txt). Настройка: `docs/drive-setup.md`.
Имя файла: `Исполнитель - Название.mp3`. Всё до первого дефиса (`-`, `–`, `—`) это исполнитель, всё после это название песни, каким бы оно ни было (`Баста - 8800`). Нужно минимум 3 новые песни в день: обработанные переезжают в `done/`.

## Публикация в TikTok (Buffer)
Утром собираются 3 ролика, `pipeline/buffer_publisher.py` ставит их в Buffer на 12:00, 17:00 и 21:00 по Asia/Almaty (ближайшие свободные слоты, занятые дни пропускаются). Видео временно лежит в Cloudinary (Buffer не принимает ссылки Drive). Режимы: `off | plan | draft | queue`, переключаются repo variable `VYBEX_BUFFER` (по умолчанию `draft`, без неё публикации нет), также `VYBEX_POSTS_PER_DAY`, `VYBEX_TIMEZONE`. Перед отправкой проверяются MP4/H.264/1080×1920, звук, длительность, целостность, декларация прав; повтор одного файла исключён (состояние в `Drive/state/buffer.json`); ролик без звука идёт уведомлением, не автопубликацией; ошибки красят шаг и не удаляют видео. Секреты: `BUFFER_API_KEY`, `CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET`. Включение, проверка без публикации и пределы: `docs/buffer.md`.

## Модули (`pipeline/`, каждый запускается отдельно)
| Модуль | Команда | Что делает | Что нужно |
|---|---|---|---|
| `sources` | `python -m pipeline.sources "запрос"` | поиск музыки: local → Openverse → Jamendo, только CC0/PD/CC-BY | Jamendo: бесплатный `JAMENDO_CLIENT_ID` |
| `download` | `python -m pipeline.download url <URL>` / `video <файл> --i-have-rights` | yt-dlp только на разрешённых доменах и только если страница заявляет CC-BY/CC0; ffmpeg-извлечение звука из ВАШЕГО локального видео | флаг прав обязателен |
| `tiktok_trends` | `python -m pipeline.tiktok_trends` | хэштеги, длительность, звуки из официального Research API; запасной вариант `data/trends.json` | доступ к Research API (одобряет TikTok, не всем) |
| `analyze` | `python -m pipeline.analyze out/<дата>` | whisper (слова с таймкодами), биты, припев, фрагмент 20–40 с, заканчивается на конце фразы | `songs.json` |
| `script_gen` | (внутри build) | строки → карточки без наложений, слова по таймкодам | — |
| `render` | (внутри build) | HTML → HyperFrames → mp4, микс звука (-14 LUFS, fade out) | Node 22, ffmpeg, Chrome для HyperFrames |
| `qa` | (внутри build) | PASS/FAIL/SKIP проверки | — |
| `build` | `python -m pipeline.build out/<дата> [--only N]` | spec → видео → QA → `meta-N.json` | `spec-N.json`, `analysis-N.json` |

Статусы источников: `ok | empty | needs_auth | unavailable | refused` — недоступный источник пропускается, следующий пробуется автоматически.

## Установка
```
python -m venv .venv  &&  .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest -q tests
```

## Статус
Проверено: whisper на реальных песнях, рендер, Claude-шаг локально, полный запуск на Actions и создание черновиков в Buffer на реальном аккаунте. Не подтверждено, что на Actions карточки пишет именно Claude, а не автоподбор (смотрите `cards=` в Summary). Не проверено вживую: режим `queue` (автопубликация TikTok через Buffer на бесплатном тарифе, проверка статусов постов), время полного запуска на 3 песни и расход минут Actions. Не реализовано: пополнение очереди песен, сбор метрик своего аккаунта в цикл. Уведомление/публикация Buffer не проверяет права на музыку: ответственность за файлы в `audio` на вас (`docs/rights.md`). Предупреждение: качество распознавания слов (`lyrics_confidence`) может отбраковать невнятный вокал, такой ролик не попадёт в `ready/` и Buffer. Карточки под смысл песни пишет шаг Claude (`pipeline/author.py`, секрет `CLAUDE_CODE_OAUTH_TOKEN`, `docs/claude-author.md`); без него работает автоподбор по ключевым словам (`render_widgets.AUTO`). Папку `audio/` и любые mp3 в git не кладём (`.gitignore`).
