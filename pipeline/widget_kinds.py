"""Data tables of the widget kinds: default app/icon/category per kind, island notifications and toasts. The pictures themselves are drawn
by remotion/src/widgets/Bodies.tsx; nothing here renders."""
NEW_KINDS = ("pair", "pulse", "route", "venn", "ring", "thermo", "alert", "target", "polaroid")
# kind -> (app title, icon colour, category line under the title)
DEFAULT_APP = {
    "pair": ("Двое", "#ff9a6b", "контакты"), "pulse": ("Пульс", "#ff4f6d", "здоровье"), "route": ("Карты", "#2fb86b", "маршрут"),
    "venn": ("Вместе", "#ff4f8b", "общий альбом"), "ring": ("Настроение", "#ffb020", "сегодня"),
    "thermo": ("Здоровье", "#ff4f6d", "температура"), "alert": ("Оповещение", "#ff3b3b", "срочное"),
    "target": ("Прицел", "#14141f", "цель найдена"), "versus": ("Ожидание", "#8a6bff", "сравнение"), "draw": ("Заметки", "#ffb020", "набросок"), "polaroid": ("Фото", "#ff7a3d", "воспоминание"),
}
# island notification shown with the card unless the widget sets "notify": false
DEFAULT_NOTIFY = {
    "route": {"app": "Карты", "text": "Маршрут построен", "icon": "#2fb86b"},
    "thermo": {"app": "Здоровье", "text": "Температура выше нормы", "icon": "#ff4f6d"},
    "alert": {"app": "Оповещение", "text": "Срочно", "icon": "#ff3b3b"},
    "target": {"app": "Прицел", "text": "Цель найдена", "icon": "#14141f"},
}

# small pop-up banner (toast) that flies over the card mid-way, unless the widget sets "toast": false. Generic UI flavour, no facts.
DEFAULT_TOAST = {
    "pair": {"app": "Сообщения", "text": "Новое сообщение", "icon": "#34c759"},
    "pulse": {"app": "Здоровье", "text": "Пульс выше нормы", "icon": "#ff4f6d"},
    "venn": {"app": "Фото", "text": "Общий альбом обновлён", "icon": "#ff4f8b"},
    "ring": {"app": "Настроение", "text": "Уровень растёт", "icon": "#ffb020"},
    "polaroid": {"app": "Фото", "text": "Воспоминание дня", "icon": "#ff7a3d"},
    "versus": {"app": "Напоминание", "text": "Выбор ещё не сделан", "icon": "#8a6bff"},
    "counter": {"app": "Банк", "text": "Баланс изменился", "icon": "#2fb86b"},
    "search": {"app": "Подсказка", "text": "Ответов не найдено", "icon": "#8a6bff"},
}

# generic phone-banner texts used when a card has no specific one (UI flavour only, never facts about the song)
BANNER_POOL = [
    {"app": "Сообщения", "text": "Новое сообщение", "icon": "#34c759"},
    {"app": "Напоминание", "text": "Не забудь послушать до конца", "icon": "#ff9f1a"},
    {"app": "Музыка", "text": "Сейчас играет", "icon": "#ff4f6d"},
    {"app": "Новости", "text": "Есть обновление", "icon": "#3b82f6"},
]
