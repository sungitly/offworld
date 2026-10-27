"""Render a complete, progressively enhanced homepage from artifact metadata."""
from collections import Counter
from html import escape
import json
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

LABELS = {'slides': '幻灯片', 'video': '视频', 'html': '网页'}


def local_url(value):
    """Only generated artifact paths may enter link/image attributes."""
    if not isinstance(value, str) or '\\' in value:
        raise ValueError('Invalid artifact path')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] not in {'slides', 'videos', 'htmls'}:
        raise ValueError('Artifact URL must remain within its generated directory')
    return quote(value, safe='/')


def video_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Published video URL must use HTTPS without credentials')
    return value


def render_homepage(root, destination, items):
    template = root / 'site/index.html'
    if not template.exists():
        return False
    overrides_path = root / 'site/content.json'
    overrides = json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
    items = [item for item in items if item['type'] in LABELS]
    counts = Counter(item['type'] for item in items)
    buttons = []
    for kind, label in [('all', '全部'), *LABELS.items()]:
        count = len(items) if kind == 'all' else counts[kind]
        if kind != 'all' and count == 0:
            continue
        buttons.append(f'<button class="filter-button" type="button" data-filter="{kind}" aria-pressed="{str(kind == "all").lower()}">{label}<span class="filter-count" aria-hidden="true">{count:02}</span></button>')
    cards = []
    for index, item in enumerate(items):
        kind = item['type']
        display = overrides.get(item['id'], {})
        title = escape(display.get('title') or item['title'])
        description = escape(display.get('description', ''))
        category = escape(display.get('category') or LABELS[kind])
        if kind == 'video':
            duration = max(0, round(item.get('duration', 0)))
            detail = f'{duration // 60}:{duration % 60:02}'
            format_label = 'VIDEO'
            available = item.get('status') == 'uploaded' and bool(item.get('url'))
            url = video_url(item['url']) if available else ''
            action = f'<span class="video-play" aria-hidden="true"><span>▶</span></span><span class="video-duration" aria-hidden="true">{detail}</span>' if available else '<span class="video-duration">待上传</span>'
            label = f'播放 {title}'
        else:
            available = True
            url = local_url(item['path'])
            format_label = f'SLIDES · {item["pages"]} 页' if kind == 'slides' else 'WEB'
            action = '<span class="cover-action" aria-hidden="true">↗</span>'
            label = f'打开 {title}'
        if item.get('cover'):
            cover = local_url(item['cover'])
            image = f'<img src="/{escape(cover)}" alt="" width="1920" height="1080" loading="{"eager" if index < 2 else "lazy"}" decoding="async" {"fetchpriority=high" if index == 0 else ""}>'
        else:
            cover = ''
            image = '<span class="cover-placeholder" aria-hidden="true">HTML</span>'
        inner = f'<figure class="work-cover {"video-cover" if kind == "video" else ""}">{image}{action}</figure><div class="work-meta"><span>{category}</span><span class="work-format">{format_label}</span></div><h3>{title}</h3>'
        if description:
            inner += f'<p class="work-description">{description}</p>'
        if available:
            href = escape(url if kind == 'video' else '/' + url)
            attrs = f'data-video data-title="{title}" data-poster="/{escape(cover)}"' if kind == 'video' else ''
            inner = f'<a class="work-link" href="{href}" aria-label="{label}" {attrs}>{inner}</a>'
        cards.append(f'<article class="work-card" data-type="{kind}">{inner}</article>')
    output = template.read_text().replace('__ARTIFACT_CARDS__', '\n'.join(cards)).replace('__FILTERS__', ''.join(buttons)).replace('__WORK_COUNT__', str(len(items)))
    (destination / 'index.html').write_text(output)
    return True
