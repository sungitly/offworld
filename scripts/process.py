#!/usr/bin/env python3
"""Convert local sources to static artifacts. Originals never enter dist/."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'artifact.config.json').read_text())
TEMPLATE = (ROOT / 'scripts/templates/slides.html').read_text()
VERSION = '2'


def run(args, env=None):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True, env=env)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stderr[-2000:]} {result.stdout[-1000:]}')
    return result.stdout


def render_environment():
    env = os.environ.copy()
    if sys.platform == 'darwin' and not env.get('FONTCONFIG_FILE'):
        # Some headless LibreOffice bundles omit modern macOS CJK asset directories.
        folders = [Path('/System/Library/Fonts'), Path('/Library/Fonts'), Path.home() / 'Library/Fonts']
        folders += list(Path('/System/Library/AssetsV2').glob('com_apple_MobileAsset_Font*'))
        cache = ROOT / '.cache/fontconfig'
        cache.mkdir(parents=True, exist_ok=True)
        config = cache / 'fonts.conf'
        config.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>' +
            ''.join('<dir>' + html.escape(str(p)) + '</dir>' for p in folders if p.exists()) +
            '<cachedir>' + html.escape(str(cache)) + '</cachedir></fontconfig>')
        env['FONTCONFIG_FILE'] = str(config)
    return env


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def slug(path):
    name = unicodedata.normalize('NFKC', path.stem).lower()
    name = re.sub(r'[^\w-]+', '-', name).strip('-')[:70] or 'artifact'
    suffix = hashlib.sha256(path.name.encode()).hexdigest()[:8]
    return f'{name}-{suffix}'


def replace_dir(staged, destination):
    # Keep previous output intact until conversion has completed successfully.
    backup = destination.with_name(destination.name + '.previous')
    if backup.exists():
        raise RuntimeError(f'Previous interrupted conversion needs inspection: {backup}')
    if destination.exists():
        destination.rename(backup)
    try:
        shutil.move(str(staged), destination)
    except Exception:
        if backup.exists():
            backup.rename(destination)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def slides(source, force):
    ident = slug(source)
    target = ROOT / 'slides' / ident
    fingerprint = hashlib.sha256((digest(source) + VERSION + TEMPLATE +
        str(CONFIG['imageWidth']) + str(CONFIG['jpegQuality'])).encode()).hexdigest()
    marker = ROOT / '.cache' / f'{ident}.json'
    if not force and marker.exists() and json.loads(marker.read_text()).get('fingerprint') == fingerprint:
        meta = json.loads((target / 'metadata.json').read_text()) if (target / 'metadata.json').exists() else None
        if meta and (target / 'index.html').exists() and all((target / 'images' / f'{i:03}.jpg').exists() for i in range(1, meta['pages'] + 1)):
            print(f'Unchanged: {source.name}', flush=True)
            return
    with zipfile.ZipFile(source) as archive:
        expected = sum(bool(re.fullmatch(r'ppt/slides/slide\d+\.xml', n)) for n in archive.namelist())
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temp:
        work = Path(temp)
        run([os.environ.get('SOFFICE', 'soffice'), '-env:UserInstallation=' + (work / 'profile').as_uri(),
             '--headless', '--convert-to', 'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}', '--outdir', work, source], env=render_environment())
        pdf = work / (source.stem + '.pdf')
        if not pdf.exists():
            raise RuntimeError(f'No PDF produced for {source.name}')
        match = re.search(r'^Pages:\s+(\d+)', run(['pdfinfo', pdf]), re.M)
        if not match or int(match[1]) != expected:
            raise RuntimeError(f'Page count mismatch: {source.name}, expected {expected}')
        staged = work / 'output'
        images = staged / 'images'
        images.mkdir(parents=True)
        run(['pdftoppm', '-jpeg', '-jpegopt', f"quality={CONFIG['jpegQuality']}", '-scale-to', CONFIG['imageWidth'], pdf, images / 'page'])
        pages = sorted(images.glob('page-*.jpg'), key=lambda p: int(p.stem.split('-')[-1]))
        if len(pages) != expected:
            raise RuntimeError('Image count mismatch')
        for i, image in enumerate(pages, 1):
            image.rename(images / f'{i:03}.jpg')
        fallback = ''.join(f'<img src="images/{i:03}.jpg" alt="第 {i} 页" style="width:100%">' for i in range(1, expected + 1))
        viewer = TEMPLATE.replace('__COUNT__', str(expected)).replace('__NOSCRIPT__', fallback).replace('__TITLE__', html.escape(source.stem))
        (staged / 'index.html').write_text(viewer)
        write_json(staged / 'metadata.json', {'id': ident, 'type': 'slides', 'title': source.stem,
            'path': f'slides/{ident}/index.html', 'cover': f'slides/{ident}/images/001.jpg', 'pages': expected})
        target.parent.mkdir(exist_ok=True)
        replace_dir(staged, target)
        write_json(marker, {'fingerprint': fingerprint})
    print(f'Slides: {source.name} → {expected} pages', flush=True)


def import_html(source):
    # For external assets, use sources/<name>/index.html and keep the bundle together.
    ident = slug(source)
    target = ROOT / 'htmls' / ident
    if source.is_file():
        content = source.read_text()
        refs = re.findall(r'(?:src|href)\s*=\s*["\']([^"\']+)', content, re.I)
        if any(not re.match(r'^(?:[a-z][a-z0-9+.-]*:|//|#)', r, re.I) for r in refs):
            raise ValueError(f'{source.name}: put HTML with local dependencies in sources/<name>/index.html')
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target / 'index.html')
    else:
        forbidden = {'.pptx', '.pdf', '.mp4', '.mov', '.mkv', '.webm'}
        for item in source.rglob('*'):
            if item.is_symlink() or item.suffix.lower() in forbidden or any(p.startswith('.') for p in item.relative_to(source).parts):
                raise ValueError(f'Unsupported file in HTML bundle: {item}')
        with tempfile.TemporaryDirectory(dir=ROOT / '.cache') as temp:
            staged = Path(temp) / 'bundle'
            shutil.copytree(source, staged)
            replace_dir(staged, target)
    write_json(target / 'metadata.json', {'id': ident, 'type': 'html', 'title': source.stem,
        'path': f'htmls/{ident}/index.html'})
    print(f'HTML: {source.name}', flush=True)


def video(source):
    ident = slug(source)
    target = ROOT / 'videos' / ident
    target.mkdir(parents=True, exist_ok=True)
    info = json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', source]))
    stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
    duration = float(info['format'].get('duration', 0))
    run(['ffmpeg', '-v', 'error', '-y', '-ss', min(1, duration / 2), '-i', source,
         '-frames:v', '1', '-vf', 'scale=1280:-2', '-update', '1', target / 'poster.jpg'])
    old = json.loads((target / 'metadata.json').read_text()) if (target / 'metadata.json').exists() else {}
    checksum = digest(source)
    key = f'videos/{ident}/{checksum[:16]}.mp4'
    data = {'id': ident, 'type': 'video', 'title': source.stem, 'cover': f'videos/{ident}/poster.jpg',
            'duration': round(duration, 2), 'width': stream['width'], 'height': stream['height'],
            'objectKey': key, 'status': 'pending-upload'}
    if old.get('objectKey') == key and old.get('status') == 'uploaded':
        data.update({k: old[k] for k in ('status', 'url') if k in old})
    write_json(target / 'metadata.json', data)
    print(f'Video prepared: {source.name} ({duration:.1f}s)', flush=True)


def catalog():
    items = []
    for category in ('htmls', 'slides', 'videos'):
        for path in sorted((ROOT / category).glob('*/metadata.json')):
            items.append(json.loads(path.read_text()))
    write_json(ROOT / 'artifacts.json', {'name': CONFIG['name'], 'visibility': CONFIG['visibility'], 'items': items})
    return items


def process(force=False):
    (ROOT / '.cache').mkdir(exist_ok=True)
    errors = []
    for source in sorted((ROOT / 'sources').iterdir()):
        if source.name.startswith('.'):
            continue
        try:
            if source.is_symlink():
                raise ValueError('Symbolic links are not supported')
            if source.is_dir() and (source / 'index.html').exists():
                import_html(source)
            elif source.suffix.lower() == '.pptx':
                slides(source, force)
            elif source.suffix.lower() == '.html':
                import_html(source)
            elif source.suffix.lower() in {'.mp4', '.mov', '.mkv', '.webm'}:
                video(source)
            else:
                print(f'Skipped unsupported source: {source.name}', flush=True)
        except Exception as error:
            errors.append(f'{source.name}: {error}')
    catalog()
    if errors:
        raise RuntimeError('\n'.join(errors))


def build(allow_private=False):
    if CONFIG['visibility'] != 'public' and not allow_private:
        raise ValueError('Private repository: use --allow-private only for a protected deployment or local preview')
    items = catalog()
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temp:
        staged = Path(temp) / 'site'
        staged.mkdir()
        for category in ('htmls', 'slides', 'videos'):
            if (ROOT / category).exists():
                shutil.copytree(ROOT / category, staged / category, symlinks=True, ignore=shutil.ignore_patterns('.gitkeep'))
        shutil.copy2(ROOT / 'artifacts.json', staged / 'artifacts.json')
        forbidden = {'.pptx', '.pdf', '.mp4', '.mov', '.mkv', '.webm', '.py'}
        for path in staged.rglob('*'):
            if path.is_symlink() or path.suffix.lower() in forbidden or any(p.startswith('.') for p in path.relative_to(staged).parts):
                raise ValueError(f'Unexpected deployment asset: {path}')
            if path.is_file() and path.stat().st_size > 25 * 1024 * 1024:
                raise ValueError(f'Pages asset exceeds 25 MiB: {path}')
        replace_dir(staged, ROOT / 'dist')
    print(f'Built dist/: {len(items)} artifacts. No homepage yet.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['process', 'build', 'catalog'])
    parser.add_argument('--force', action='store_true', help='Render unchanged PPTX again')
    parser.add_argument('--allow-private', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'process':
            process(args.force)
        elif args.command == 'build':
            build(args.allow_private)
        else:
            catalog()
    except Exception as error:
        parser.exit(1, f'Error: {error}\n')
