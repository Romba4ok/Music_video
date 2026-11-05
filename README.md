# Music Video Factory

Автоматический конвейер: песня → анализ текста и битов → вертикальное видео (HyperFrames) → QA → публикация (официальный API TikTok).
Правила для Claude: `CLAUDE.md`. Права и источники: `docs/rights.md`.

## Шаблон
`config.json: style` = `widgets` (по умолчанию): заставка с названием, «Dynamic Island» с плеером, строка песни как виджет-уведомление с иллюстрацией (закат, карта, пульс, часы, погода, ночь), прогресс-бар. `handle` в config — ваш @ник на заставке и в плеере. `cards` — старый текстовый стиль. Код: `pipeline/render_widgets.py`.

## Два режима
- **AUTO** (`with_audio`): звук из разрешённого источника (CC0/CC-BY или ваш файл) вшивается в mp4. `python -m pipeline batch --mode auto --count 3`
- **TIKTOK** (`tiktok`): mp4 без звука, тайминг под песню + `sync-N.txt` («поставьте звук с 1:02.40»); официальный звук добавляете в приложении TikTok. `python -m pipeline batch --mode tiktok --count 3`

Этапы независимы: `python -m pipeline fetch "…"` → `analyze <audio>` → `render out/<дата>`. Любой полученный легально mp4/mov/webm автоматически конвертируется в аудио через ffmpeg. Сбой одной песни или источника не останавливает пакет (`out/<дата>/report.json`). Расписание: `.github/workflows/generate.yml` (на Actions не проверен).

## Без терминала: Google Drive
Песни кладёте в `VYBEX/audio` на Диске, workflow по расписанию забирает их, делает ролики и кладёт в `VYBEX/ready/<дата>/` (mp4 + caption.txt + sync.txt). Настройка: `docs/drive-setup.md`.

## Модули (`pipeline/`, каждый запускается отдельно)
| Модуль | Команда | Что делает | Что нужно |
|---|---|---|---|
| `sources` | `python -m pipeline.sources "запрос"` | поиск музыки: local → Openverse → Jamendo, только CC0/PD/CC-BY | Jamendo: бесплатный `JAMENDO_CLIENT_ID` |
| `download` | `python -m pipeline.download url <URL>` / `video <файл> --i-have-rights` | yt-dlp только на разрешённых доменах и только если страница заявляет CC-BY/CC0; ffmpeg-извлечение звука из ВАШЕГО локального видео | флаг прав обязателен |
| `tiktok_trends` | `python -m pipeline.tiktok_trends` | хэштеги, длительность, звуки из официального Research API; запасной вариант `data/trends.json` | доступ к Research API (одобряет TikTok, не всем) |
| `analyze` | `python -m pipeline.analyze out/<дата>` | whisper (слова с таймкодами), биты, припев, фрагмент 30–60 с вокруг популярной строки | `songs.json` |
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

## Не реализовано пока
Публикация (`publish`), пополнение очереди, сбор метрик своего аккаунта в цикл. Не проверено: whisper на реальной речи (пакеты ещё ставятся), workflow на Actions.
