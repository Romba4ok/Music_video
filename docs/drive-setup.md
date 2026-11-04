# Запуск через Google Drive (без терминала)

Всё делается в браузере один раз. Дальше: кидаете песни в папку на Диске → утром в `ready/` лежат ролики.

## Папка на Диске
`VYBEX/` → внутри создайте `audio/`. Песни называйте `Исполнитель - Название.mp3` (mp3/wav/m4a/mp4).
Необязательно: `queue.txt` (строки `артист | название | популярная строка`). Остальное (`ready/`, `done/`) создаётся само.
Кладя файл в `audio/`, вы подтверждаете, что имеете право его использовать (workflow ставит `VYBEX_OWNER_DECLARES_RIGHTS=1`).

## Доступ к Диску (один раз)
1. console.cloud.google.com → новый проект → «APIs & Services» → включить **Google Drive API**.
2. «OAuth consent screen»: External, добавить свою почту в Test users, затем **Publish app → In production** (иначе токен умрёт через 7 дней; предупреждение «unverified» для личного использования нормально).
3. «Credentials» → Create OAuth client ID → Web application → Authorized redirect URI: `https://developers.google.com/oauthplayground`. Скопируйте Client ID и Secret.
4. developers.google.com/oauthplayground → шестерёнка → «Use your own OAuth credentials» (вставить ID/Secret) → в Step 1 вписать scope `https://www.googleapis.com/auth/drive` → Authorize → Exchange authorization code → скопировать **Refresh token**.
5. ID папки `VYBEX`: открыть папку, в адресе `drive.google.com/drive/folders/<ЭТО>`.

## GitHub
Репозиторий **приватный** (GitHub Desktop → Publish repository → Keep this code private). Settings → Secrets and variables → Actions → Secrets:
`GDRIVE_CLIENT_ID`, `GDRIVE_CLIENT_SECRET`, `GDRIVE_REFRESH_TOKEN`, `GDRIVE_FOLDER_ID` (опционально `JAMENDO_CLIENT_ID`).
Variables → `VYBEX_MODE` = `tiktok` или `auto`. Первый запуск: Actions → generate → Run workflow, прочитать лог.

Scope `drive` даёт доступ ко всему Диску: refresh token храните только в Secrets.
