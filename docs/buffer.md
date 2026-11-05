# Выкладка в TikTok через Buffer

Схема: утром Actions делает 3 ролика → `pipeline/buffer_publisher.py` кладёт их в очередь Buffer → Buffer сам выкладывает по расписанию канала в течение дня.

## Один раз настроить
1. **Buffer → канал @vybex.mp44 → Posting schedule**: задайте 3 времени в день (например 12:00, 16:00, 20:00). `addToQueue` берёт ближайший свободный слот.
2. **Buffer → Settings → API**: создайте ключ. В GitHub Secrets: `BUFFER_API_KEY`.
3. **Cloudinary** (бесплатно, без карты): Dashboard → Cloud name / API key / API secret. В Secrets: `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`. Buffer не берёт ссылки Google Drive (нужен публичный прямой HTTPS), поэтому файл временно лежит в Cloudinary под именем из sha256 ролика, весь Drive не раскрывается.
4. Канал найдётся сам, если в Buffer ровно один TikTok. Либо локально: `set BUFFER_API_KEY=...` (в вашем терминале, не в чате) и `python -m pipeline buffer setup`, id запишется в `config.json`.

## Режимы (`VYBEX_BUFFER`: repo variable, иначе `config.json → buffer.mode`)
| режим | что делает |
|---|---|
| `off` | ничего не отправляет |
| `draft` (по умолчанию) | пост создаётся как **черновик** в Buffer, не публикуется |
| `queue` | пост уходит в очередь и **публикуется** по расписанию |

Любое другое значение = `off`. Чтобы включить настоящую выкладку: Settings → Secrets and variables → Actions → Variables → `VYBEX_BUFFER` = `queue`.

## Защиты
- Повтор: sha256 файла хранится в `gd:state/buffer.json` (между запусками). Тот же ролик не уйдёт дважды; черновик можно позже отправить в `queue`.
- Файл на хостинге нужен до публикации (Buffer скачивает его в момент выхода поста), поэтому удаляется по возрасту, `keep_days` = 7, при следующем запуске.
- Перед `createPost` проверяется ссылка: HTTPS, 200 без редиректа, `video/*`, размер совпадает. Файл ≤ `max_mb` (100), только `.mp4`.
- Любая ошибка: ролик остаётся в `out/<date>/ready` и в Drive, в `report.json` у песни поле `buffer` (state/detail), в Summary строка `buffer: …`.
- Метка ИИ уходит флагами `aiAssisted` и `metadata.tiktok.isAiGenerated`.

## Пределы
- Если пост стоит в очереди дольше `keep_days`, Buffer не найдёт файл: ставьте расписание плотнее или увеличьте `keep_days`.
- Очередь бесплатного Buffer ограничена (около 10 постов на канал): при 3 в день накопление невозможно, если слоты заданы.
- Видимость и права на музыку Buffer не проверяет; TikTok может заглушить трек или ограничить охват.
