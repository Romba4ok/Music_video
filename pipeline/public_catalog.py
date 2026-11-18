"""Read public HTML search forms and advertised audio metadata, without executing scripts."""

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from .sources import Candidate


class PublicCatalogHTML(HTMLParser):
    def __init__(self, site, page):
        super().__init__(convert_charrefs=True)
        self.site, self.page = site, page
        self.forms, self.tracks, self.text = [], [], []
        self.form, self.structured = None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.form = {'action': urljoin(self.page, attrs.get('action') or self.page),
                         'method': attrs.get('method', 'get').lower(), 'hidden': {}, 'query': '', 'password': False}
        elif tag == 'input' and self.form is not None:
            name, kind = attrs.get('name', ''), attrs.get('type', 'text').lower()
            if kind == 'password':
                self.form['password'] = True
            elif name and kind == 'hidden':
                self.form['hidden'][name] = attrs.get('value', '')
            elif kind in ('text', 'search') and name.lower() in ('q', 'query', 'word', 'story', 'search', 's'):
                self.form['query'] = name
        if tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json':
            self.structured = []
        artist, title = attrs.get('data-artist'), attrs.get('data-title')
        audio = next((attrs[k] for k in ('data-download-url', 'data-track', 'data-url') if attrs.get(k)), '')
        if artist and title and audio:
            self.tracks.append(Candidate(self.site, title, artist, urljoin(self.page, audio), landing=self.page))

    def handle_endtag(self, tag):
        if tag == 'form' and self.form is not None:
            if self.form['query'] and not self.form['password'] and self.form['method'] in ('get', 'post'):
                self.forms.append(self.form)
            self.form = None
        if tag == 'script' and self.structured is not None:
            try:
                self.read_recordings(json.loads(''.join(self.structured)))
            except (ValueError, TypeError):
                pass
            self.structured = None

    def handle_data(self, value):
        if self.structured is not None:
            self.structured.append(value)
        else:
            self.text.append(value)

    def read_recordings(self, value):
        if isinstance(value, list):
            for child in value:
                self.read_recordings(child)
        elif isinstance(value, dict):
            types = value.get('@type', [])
            if isinstance(types, str):
                types = [types]
            if 'MusicRecording' in types:
                artists = value.get('byArtist') or []
                if not isinstance(artists, list):
                    artists = [artists]
                artist = ' & '.join(a.get('name', '') if isinstance(a, dict) else str(a) for a in artists)
                media = value.get('audio') or value.get('associatedMedia') or {}
                if isinstance(media, list):
                    media = next((m for m in media if isinstance(m, dict) and m.get('contentUrl')), {})
                audio = value.get('contentUrl') or (media.get('contentUrl', '') if isinstance(media, dict) else '')
                title = value.get('name')
                if artist and isinstance(title, str):
                    duration = re.fullmatch(r'PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?', str(value.get('duration', '')))
                    sec = int(duration[1] or 0) * 60 + float(duration[2] or 0) if duration else 0
                    self.tracks.append(Candidate(self.site, title, artist, urljoin(self.page, audio) if audio else '',
                                                 landing=self.page, sec=sec))
            for child in value.values():
                if isinstance(child, (dict, list)):
                    self.read_recordings(child)

    @property
    def empty(self):
        return bool(re.search(r'ничего\s+не\s+найдено|нет\s+результатов|no\s+(?:results|songs|tracks)\s+found',
                              ' '.join(self.text), re.I))


def read_public_html(html, site, page):
    parser = PublicCatalogHTML(site, page)
    parser.feed(html)
    parser.close()
    return parser
