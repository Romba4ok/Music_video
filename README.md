# Music Video Factory

Автоматический конвейер: песня → анализ текста и битов → вертикальное видео (HyperFrames) → QA → очередь TikTok через Buffer (официальный GraphQL API), 3 ролика в день.
Правила для Claude: `CLAUDE.md`. Права и источники: `docs/rights.md`.

## Шаблон
`config.json: style` = `widgets` (по умолчанию), формат «widget edit»: квадрат 1:1 с интерфейсом телефона посреди кадра 9:16, хук-вопрос в верхнем чёрном поле, заставка с обложкой и `автор: vybex` (`handle` в config), остров-плеер с эквалайзером, на каждую строку анимированная карточка (пара, пульс, маршрут, кольцо, прицел, поиск, чат и др.), уведомление в острове с каждой карточкой, плеер/прогресс внизу, финальная заставка. Движение: карточка качается на битах, стопка карточек, шарик-связка, вибрация, блики, ничто не стоит. `cards` — старый текстовый стиль. Подробно и как подбирать картинки под смысл: `docs/widgets-template.md`. Код: `pipeline/render_widgets.py`, `pipeline/widget_kinds.py`.

## Два режима
- **AUTO** (`with_audio`): звук из разрешённого источника (CC0/CC-BY или ваш файл) вшивается в mp4. `python -m pipeline batch --mode auto --count 3`
- **TIKTOK** (`tiktok`): mp4 без звука, тайминг под песню + `sync-N.txt` («поставьте звук с 1:02.40»); официальный звук добавляете в приложении TikTok. `python -m pipeline batch --mode tiktok --count 3`

Этапы независимы: `python -m pipeline fetch "…"` → `analyze <audio>` → `render out/<дата>`. Любой полученный легально mp4/mov/webm автоматически конвертируется в аудио через ffmpeg. Сбой одной песни или источника не останавливает пакет (`out/<дата>/report.json`). Запуск: `.github/workflows/generate.yml`. Ежедневно в 08:00 Алматы его запускает cron-job.org (`workflow_dispatch`, см. ниже), плюс ручной запуск; собственного расписания GitHub (`schedule`) в файле нет, оно не срабатывало; на push не запускается, два запуска одновременно не идут.

## Без терминала: Google Drive
Песни кладёте в `VYBEX/audio` на Диске, workflow по расписанию забирает их, делает ролики и кладёт в `VYBEX/ready/<дата>/` (mp4 + caption.txt + sync.txt). Настройка: `docs/drive-setup.md`.
Имя файла: `Исполнитель - Название.mp3`. Всё до первого дефиса (`-`, `–`, `—`) это исполнитель, всё после это название песни, каким бы оно ни было (`Баста - 8800`).
С какой строки начать ролик: по умолчанию выбирается припев автоматически. Чтобы начать ровно с нужной строки, допишите в конце имени начало этой строки в квадратных скобках: `Баста - 8800 [я не знаю что].mp3`. Текст берётся из распознанного whisper'ом (достаточно первых 2–3 слов, регистр и знаки не важны). Ролик начнётся именно с этой строки и продлится до конца мысли (20–40 с), Claude начало не обрежет. Строка не найдена: выбор остаётся автоматическим (в report.json в `reason` будет «not found»). Скобки в названии песни не используйте.
Нужно минимум 3 новые песни в день: обработанные переезжают в `done/`.

## Публикация в TikTok (Buffer)
Утром собираются 3 ролика, `pipeline/buffer_publisher.py` ставит их в Buffer на 12:00, 17:00 и 21:00 по Asia/Almaty (ближайшие свободные слоты, занятые дни пропускаются). Видео временно лежит в Cloudinary (Buffer не принимает ссылки Drive). Режимы: `off | plan | draft | queue`, переключаются repo variable `VYBEX_BUFFER` (по умолчанию `draft`, без неё публикации нет), также `VYBEX_POSTS_PER_DAY`, `VYBEX_TIMEZONE`. Перед отправкой проверяются MP4/H.264/1080×1920, звук, длительность, целостность, декларация прав; повтор одного файла исключён (состояние в `Drive/state/buffer.json`); ролик без звука идёт уведомлением, не автопубликацией; ошибки красят шаг и не удаляют видео. Секреты: `BUFFER_API_KEY`, `CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET`. Включение, проверка без публикации и пределы: `docs/buffer.md`.

## Сервисы проекта и как всё идёт по порядку
Один день работы, по шагам. Ничего, кроме песен в Drive, вручную делать не нужно.

| # | Когда | Что происходит | Сервис |
|---|---|---|---|
| 1 | заранее | Вы кладёте песни `Исполнитель - Название [начало строки].mp3` в `VYBEX/audio` на Google Drive | **Google Drive** |
| 2 | 08:00 Алматы | Планировщик отправляет запрос на запуск workflow `generate` (`workflow_dispatch`). Расписание самого GitHub из файла убрано. Два запуска не идут одновременно (`concurrency`) | **cron-job.org** → **GitHub Actions** |
| 3 | сразу | GitHub поднимает виртуальную машину Ubuntu, ставит Node 22, Python 3.12, ffmpeg, rclone, зависимости и Chrome для HyperFrames. Секреты и переменные берутся из Settings репозитория | **GitHub Actions**, **GitHub Secrets/Variables** |
| 4 | дальше | rclone забирает `audio/` из Drive (токен обновляется по refresh-token) | **Google Drive API** через rclone |
| 5 | дальше | ffprobe проверяет файл, whisper распознаёт слова с таймкодами, librosa считает биты, выбирается фрагмент 20–40 с без пауз и с надёжным текстом | **faster-whisper** (модель с Hugging Face, кэшируется), **librosa**, **ffmpeg** |
| 6 | дальше | Claude пишет хук, подпись, обрезку по смыслу, карточки и рисунки SVG для каждой строки. Без него карточки подбираются по ключевым словам | **Claude Code** (подписка, секрет `CLAUDE_CODE_OAUTH_TOKEN`) |
| 7 | дальше | HTML карточек рендерится в видео 1080×1920, звук вшивается (−14 LUFS), проверка `hyperframes check` и QA. Не прошло: ролик не попадёт в `ready/` | **HyperFrames** (Node, Chrome, шрифты Google Fonts, GSAP с jsDelivr), **ffmpeg** |
| 8 | дальше | Готовые mp4 и `caption.txt` кладутся в `VYBEX/ready/<дата>/`, обработанные песни переезжают в `done/` | **Google Drive** |
| 9 | дальше | Видео временно загружается на публичный хостинг, потому что Buffer не принимает ссылки Drive | **Cloudinary** |
| 10 | дальше | Ролики ставятся в очередь Buffer на 12:00, 17:00 и 21:00 по Asia/Almaty (режим `off \| plan \| draft \| queue`), состояние хранится в `Drive/state/buffer.json` | **Buffer** (GraphQL API) |
| 11 | в слот | Buffer сам публикует в TikTok-аккаунт | **Buffer** → **TikTok** |
| 12 | в конце | Итог (сколько собрано, что поставлено, ошибки) пишется в Summary запуска; результаты и состояние сохраняются при любой ошибке | **GitHub Actions** |

### Все подключённые сервисы
| Сервис | Зачем | Где настраивается | Ключ или секрет | Обязателен |
|---|---|---|---|---|
| **GitHub** (репозиторий, Actions, Secrets, Variables) | хранит код, запускает workflow, прячет ключи | репозиторий → Settings; `docs/github-setup.md` | — | да |
| **GitHub Desktop** (или `git`) | отправка изменений кода в репозиторий | на вашем компьютере | вход в GitHub | да, для обновлений кода |
| **cron-job.org** | ежедневный запуск workflow через GitHub API (`workflow_dispatch`), потому что расписание GitHub не срабатывало | cron-job.org, задание POST на `.../actions/workflows/generate.yml/dispatches` | токен GitHub (fine-grained, только Actions на этот репозиторий) хранится в заголовке задания | сейчас да |
| **Google Drive** (+ rclone) | вход (`audio/`) и выход (`ready/`, `done/`, `state/`) | `docs/drive-setup.md` | `GDRIVE_CLIENT_ID`, `GDRIVE_CLIENT_SECRET`, `GDRIVE_REFRESH_TOKEN`, `GDRIVE_FOLDER_ID` | да |
| **Claude Code** | карточки, хук, подпись, SVG-рисунки по смыслу строк | `docs/claude-author.md` | `CLAUDE_CODE_OAUTH_TOKEN` | нет (без него автоподбор по ключевым словам) |
| **faster-whisper** (Hugging Face) | распознавание слов песни | `config.json: whisper` | — | да |
| **HyperFrames** (Node, Chrome, Google Fonts, jsDelivr GSAP) | сборка видео из HTML | `docs/hyperframes-notes.md` | — | да |
| **Cloudinary** | временный публичный хостинг видео для Buffer | `docs/buffer.md` | `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | для Buffer |
| **Buffer** | очередь и публикация в TikTok | `docs/buffer.md` | `BUFFER_API_KEY`; переменные `VYBEX_BUFFER`, `VYBEX_POSTS_PER_DAY`, `VYBEX_TIMEZONE` | для публикации |
| **TikTok** (аккаунт `@vybex.mp44`) | куда публикует Buffer | подключён в Buffer | — | для публикации |
| **Openverse**, **Jamendo** | поиск музыки с открытой лицензией, если файла нет | `config.json: sources` | `JAMENDO_CLIENT_ID` (бесплатный) | нет |
| **TikTok Research API** | тренды (хэштеги, звуки); запасной файл `data/trends.json` | `pipeline/tiktok_trends.py` | доступ выдаёт TikTok, не всем | нет |

Если сервис не отвечает: Drive/Cloudinary/Buffer красят шаг в Summary и ничего не теряют (видео и состояние сохраняются); Claude недоступен: карточки подбираются автоматически; источник музыки недоступен: пробуется следующий; песня с плохим файлом или нечётким текстом пропускается, остальные идут дальше.

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
