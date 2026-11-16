"""Tables of the card kinds: only `draw` (a picture Claude draws as SVG with tweens) exists. The ready-made kinds are gone: the old template cards
(pair, pulse, route, ... scene) were removed on 2026-11-09 and the eight animated scenes (weather, typing, bloom, duo, breath, deep, unlock, night)
on 2026-11-16, both by the owner's decision: nothing but a drawing made for the line may appear in a video. Nothing here renders."""
# kind -> (app title, icon colour, category line under the title)
DEFAULT_APP = {"draw": ("Заметки", "#ffb020", "набросок")}
# island notification text used when a card has none of its own: generic UI flavour, never facts about the song
BANNER_POOL = [
    {"app": "Сообщения", "text": "Новое сообщение", "icon": "#34c759"},
    {"app": "Напоминание", "text": "Не забудь послушать до конца", "icon": "#ff9f1a"},
    {"app": "Музыка", "text": "Сейчас играет", "icon": "#ff4f6d"},
    {"app": "Новости", "text": "Есть обновление", "icon": "#3b82f6"},
]
