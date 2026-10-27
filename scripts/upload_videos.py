#!/usr/bin/env python3
"""Print an R2 upload plan; --execute uploads prepared MP4 files using boto3."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote, urlparse
from process import ROOT, CONFIG, catalog, digest, run, slug, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Upload; default is a local plan only')
    args = parser.parse_args()
    sources = {slug(p): p for p in (ROOT / 'sources').iterdir()
               if p.is_file() and p.suffix.lower() in {'.mp4', '.mov', '.mkv', '.webm'}}
    jobs = []
    for meta_file in sorted((ROOT / 'videos').glob('*/metadata.json')):
        data = json.loads(meta_file.read_text())
        source = sources.get(data['id'])
        if source is None:
            continue
        checksum = digest(source)
        if data['objectKey'] != f"videos/{data['id']}/{checksum[:16]}.mp4":
            parser.error('Source changed: run python3 scripts/process.py process first')
        jobs.append((source, meta_file, data, checksum))
        print(f"{source.name} → s3://{CONFIG['r2Bucket']}/{data['objectKey']}", flush=True)
    if not args.execute:
        print('Plan only. No network requests or uploads. Add --execute after configuring R2.')
        return
    needed = ('R2_ACCOUNT_ID', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY')
    if any(not os.environ.get(name) for name in needed):
        parser.error('Set R2_ACCOUNT_ID, AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your environment')
    base = CONFIG.get('mediaBaseUrl', '').rstrip('/')
    if CONFIG['visibility'] == 'public' and (urlparse(base).scheme != 'https' or not urlparse(base).netloc):
        parser.error('Set mediaBaseUrl to your public R2 custom domain (https://...)')
    if CONFIG['visibility'] != 'public' and base:
        parser.error('Private repositories must keep mediaBaseUrl empty')
    try:
        import boto3
    except ImportError:
        parser.error('Install the optional dependency: python3 -m pip install -r scripts/requirements-r2.txt')
    client = boto3.client('s3', endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", region_name='auto')
    bucket = CONFIG['r2Bucket']
    # Verify credentials/bucket before spending time transcoding.
    client.head_bucket(Bucket=bucket)
    for source, meta_file, data, checksum in jobs:
        media = ROOT / '.cache/media' / (checksum + '.mp4')
        media.parent.mkdir(parents=True, exist_ok=True)
        if not media.exists():
            info = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', source]))
            video = next(s for s in info['streams'] if s['codec_type'] == 'video')
            audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
            options = ['-c:v', 'copy'] if video['codec_name'] == 'h264' and video.get('pix_fmt') == 'yuv420p' else ['-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p']
            options += ['-c:a', 'copy'] if audio and audio['codec_name'] == 'aac' else ['-c:a', 'aac', '-b:a', '192k']
            temp = media.with_suffix('.partial.mp4')
            run(['ffmpeg', '-v', 'error', '-y', '-i', source, '-map', '0:v:0', '-map', '0:a:0?',
                 *options, '-movflags', '+faststart', temp])
            temp.rename(media)
        for path, key, mime in [(media, data['objectKey'], 'video/mp4'),
                               (meta_file.parent / 'poster.jpg', data['objectKey'][:-4] + '-poster.jpg', 'image/jpeg')]:
            client.upload_file(str(path), bucket, key, ExtraArgs={'ContentType': mime,
                'CacheControl': 'public, max-age=31536000, immutable' if CONFIG['visibility'] == 'public' else 'private, no-store'})
        data['status'] = 'uploaded'
        if CONFIG['visibility'] == 'public':
            data['url'] = base + '/' + quote(data['objectKey'], safe='/')
        else:
            data.pop('url', None)  # Private URLs must be signed at request time, never stored in static JSON.
        write_json(meta_file, data)
        print(f"Uploaded: {source.name}", flush=True)
    catalog()


if __name__ == '__main__':
    main()
