"""Tables of the card kinds that exist: the animated scenes (remotion/src/widgets/Scenes.tsx) and `draw` (a picture Claude draws as SVG with
tweens). The old template cards (pair, pulse, route, venn, ring, thermo, alert, target, polaroid, versus, counter, search, chat, dots, camera,
scene) were removed on 2026-11-09 by the owner's decision: they must not appear in videos. Nothing here renders."""
SCENE_KINDS = ("weather", "typing", "bloom", "duo", "breath", "deep", "unlock", "night")
# kind -> (app title, icon colour, category line under the title)
DEFAULT_APP = {
    "weather": ("Погода", "#5aa9ff", "на душе"), "typing": ("Сообщения", "#34c78a", "нет ответа"), "bloom": ("Календарь", "#ff7a59", "весна"),
    "duo": ("Избранное", "#f5b942", "только ты"), "breath": ("Дыхание", "#7a6be0", "вдох · выдох"), "deep": ("Глубина", "#3fb7c4", "всё глубже"),
    "unlock": ("Замок", "#ef8f9a", "без секретов"), "night": ("Сны", "#6b5bd6", "сладкие грёзы"), "draw": ("Заметки", "#ffb020", "набросок"),
}
# island notification text used when a card has none of its own: generic UI flavour, never facts about the song
BANNER_POOL = [
    {"app": "Сообщения", "text": "Новое сообщение", "icon": "#34c759"},
    {"app": "Напоминание", "text": "Не забудь послушать до конца", "icon": "#ff9f1a"},
    {"app": "Музыка", "text": "Сейчас играет", "icon": "#ff4f6d"},
    {"app": "Новости", "text": "Есть обновление", "icon": "#3b82f6"},
]
