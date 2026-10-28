"""Regression checks for original-file isolation and private build defaults."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import process
import upload_videos
from gallery import render_homepage


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(process, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.config = patch.object(process, 'CONFIG', {'name': 'test', 'visibility': 'public'})
        self.config.start()
        self.addCleanup(self.config.stop)
        for name in ['sources', 'htmls', 'slides', 'videos', '.cache']:
            (self.root / name).mkdir()

    def test_build_excludes_originals_and_gitkeep(self):
        (self.root / 'sources/original.pptx').write_bytes(b'private original')
        (self.root / '.env').write_text('SECRET=private')
        (self.root / 'slides/.gitkeep').touch()
        deck = self.root / 'slides/demo'
        deck.mkdir()
        (deck / 'index.html').write_text('<h1>demo</h1>')
        process.write_json(deck / 'metadata.json', {'id': 'demo', 'type': 'slides'})
        process.build()
        files = {str(p.relative_to(self.root / 'dist')) for p in (self.root / 'dist').rglob('*') if p.is_file()}
        self.assertEqual(files, {'slides/demo/index.html', 'slides/demo/metadata.json', 'artifacts.json'})

    def test_private_build_requires_explicit_flag(self):
        process.CONFIG['visibility'] = 'private'
        with self.assertRaisesRegex(ValueError, 'Private repository'):
            process.build()
        self.assertFalse((self.root / 'dist').exists())
        process.build(allow_private=True)

    def test_build_rejects_link_without_overwriting_previous_output(self):
        (self.root / 'dist').mkdir()
        (self.root / 'dist/previous.html').write_text('previous good output')
        (self.root / 'sources/secret.txt').write_text('secret')
        (self.root / 'htmls/leak.txt').symlink_to(self.root / 'sources/secret.txt')
        with self.assertRaisesRegex(ValueError, 'Unexpected deployment asset'):
            process.build()
        self.assertEqual((self.root / 'dist/previous.html').read_text(), 'previous good output')

    def test_html_bundle_preserves_relative_assets(self):
        bundle = self.root / 'sources/demo'
        (bundle / 'assets').mkdir(parents=True)
        (bundle / 'index.html').write_text('<img src="assets/a.svg">')
        (bundle / 'assets/a.svg').write_text('<svg/>')
        process.import_html(bundle)
        target = self.root / 'htmls' / process.slug(bundle)
        self.assertTrue((target / 'assets/a.svg').exists())
        self.assertEqual(json.loads((target / 'metadata.json').read_text())['type'], 'html')

    def test_bundle_rejects_original_files(self):
        bundle = self.root / 'sources/demo'
        bundle.mkdir()
        (bundle / 'index.html').write_text('demo')
        (bundle / 'private.pptx').write_bytes(b'original')
        with self.assertRaisesRegex(ValueError, 'Unsupported file'):
            process.import_html(bundle)

    def test_standalone_html_requires_bundle_for_relative_resources(self):
        source = self.root / 'sources/demo.html'
        source.write_text('<img src="image.jpg">')
        with self.assertRaisesRegex(ValueError, 'local dependencies'):
            process.import_html(source)

    def test_homepage_build_includes_assets_and_excludes_editorial_inputs(self):
        site = self.root / 'site'
        (site / 'assets').mkdir(parents=True)
        (site / 'index.html').write_text('<main>__WORK_COUNT____FILTERS____ARTIFACT_CARDS__</main>')
        (site / 'assets/app.js').write_text('void 0')
        (site / 'content.json').write_text('{}')
        (site / '_d_meta.json').write_text('{}')
        process.build()
        self.assertTrue((self.root / 'dist/assets/app.js').exists())
        output = (self.root / 'dist/index.html').read_text()
        self.assertNotIn('__ARTIFACT_CARDS__', output)
        self.assertFalse((self.root / 'dist/content.json').exists())
        self.assertFalse((self.root / 'dist/_d_meta.json').exists())

    def test_homepage_escapes_titles_and_encodes_local_paths(self):
        (self.root / 'site').mkdir()
        (self.root / 'site/index.html').write_text('__ARTIFACT_CARDS__')
        item = {'id': 'test', 'type': 'slides', 'title': '<script>bad</script>',
                'path': 'slides/中文/index.html', 'cover': 'slides/中文/001.jpg', 'pages': 2}
        render_homepage(self.root, self.root, [item])
        output = (self.root / 'index.html').read_text()
        self.assertNotIn('<script>', output)
        self.assertIn('&lt;script&gt;', output)
        self.assertIn('/slides/%E4%B8%AD%E6%96%87/index.html', output)

    def test_homepage_rejects_paths_outside_artifacts_and_non_https_video(self):
        (self.root / 'site').mkdir()
        (self.root / 'site/index.html').write_text('__ARTIFACT_CARDS__')
        item = {'id': 'test', 'type': 'slides', 'title': 'Test',
                'path': 'slides/../../.env', 'pages': 2}
        with self.assertRaises(ValueError):
            render_homepage(self.root, self.root, [item])
        item = {'id': 'test', 'type': 'video', 'title': 'Test',
                'url': 'javascript:alert(1)', 'status': 'uploaded'}
        with self.assertRaises(ValueError):
            render_homepage(self.root, self.root, [item])

    def test_unpublished_video_has_no_play_link(self):
        (self.root / 'site').mkdir()
        (self.root / 'site/index.html').write_text('__ARTIFACT_CARDS__')
        item = {'id': 'test', 'type': 'video', 'title': 'Test', 'status': 'pending-upload'}
        render_homepage(self.root, self.root, [item])
        output = (self.root / 'index.html').read_text()
        self.assertNotIn('data-video', output)
        self.assertIn('待上传', output)

    def test_video_domain_refresh_preserves_upload_but_changed_source_does_not(self):
        source = self.root / 'sources/original.mp4'
        source.write_bytes(b'original video')
        ident = process.slug(source)
        process.CONFIG.update(mediaBaseUrl='https://media.sunlei.page', videoNames={ident: 'ai-intro-astra-v1'})
        meta = self.root / 'videos' / ident / 'metadata.json'
        process.write_json(meta, {'id': ident, 'objectKey': 'videos/ai-intro-astra-v1.mp4',
            'sourceSha256': process.digest(source), 'status': 'uploaded', 'url': 'https://old.r2.dev/old.mp4'})
        probe = json.dumps({'streams': [{'codec_type': 'video', 'width': 1920, 'height': 1080}], 'format': {'duration': '86'}})
        with patch.object(process, 'run', return_value=probe):
            process.video(source)
            unchanged = json.loads(meta.read_text())
            self.assertEqual(unchanged['status'], 'uploaded')
            self.assertEqual(unchanged['url'], 'https://media.sunlei.page/videos/ai-intro-astra-v1.mp4')
            source.write_bytes(b'new video content')
            process.video(source)
            changed = json.loads(meta.read_text())
            self.assertEqual(changed['status'], 'pending-upload')
            self.assertNotIn('url', changed)


class VideoNameTests(unittest.TestCase):
    def test_readable_name_and_legacy_compatibility(self):
        with patch.object(process, 'CONFIG', {'videoNames': {'example': 'ai-intro-astra-v1'}}):
            self.assertEqual(process.video_object_key('example', 'abcdef' * 11), 'videos/ai-intro-astra-v1.mp4')
            self.assertEqual(process.video_object_key('legacy', '0123456789abcdef'), 'videos/legacy/0123456789abcdef.mp4')

    def test_duplicate_or_unsafe_names_are_rejected(self):
        for names in [{'one': 'same', 'two': 'same'}, {'one': '../secret'}, {'one': 'a name'}, {'one': ''}]:
            with self.subTest(names=names), patch.object(process, 'CONFIG', {'videoNames': names}), self.assertRaises(ValueError):
                process.video_object_key('one', 'abc')

    def test_existing_named_object_cannot_be_replaced_by_other_content(self):
        client = Mock()
        data = {'id': 'example', 'objectKey': 'videos/ai-intro-astra-v1.mp4'}
        with patch.object(upload_videos, 'CONFIG', {'videoNames': {'example': 'ai-intro-astra-v1'}}):
            for metadata in [{}, {'source-sha256': 'other-content'}]:
                client.head_object.return_value = {'Metadata': metadata}
                with self.assertRaisesRegex(ValueError, 'increment its version'):
                    upload_videos.ensure_named_video_immutable(client, 'offworld', data, 'current-content')
            client.head_object.return_value = {'Metadata': {'source-sha256': 'current-content'}}
            upload_videos.ensure_named_video_immutable(client, 'offworld', data, 'current-content')

    def test_lookup_failures_do_not_allow_an_overwrite(self):
        client = Mock()
        data = {'id': 'example', 'objectKey': 'videos/example-v1.mp4'}
        with patch.object(upload_videos, 'CONFIG', {'videoNames': {'example': 'example-v1'}}):
            client.head_object.side_effect = RuntimeError('network failure')
            with self.assertRaisesRegex(RuntimeError, 'network failure'):
                upload_videos.ensure_named_video_immutable(client, 'offworld', data, 'checksum')


class UploadEnvTests(unittest.TestCase):
    def test_local_credentials_load_without_overwriting_exported_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.env').write_text("R2_ACCOUNT_ID=example-account\nexport AWS_ACCESS_KEY_ID='local-key'\nAWS_SECRET_ACCESS_KEY=example-secret # comment\nUNRELATED=ignored\n")
            with patch.object(upload_videos, 'ROOT', root), patch.dict(os.environ, {'AWS_ACCESS_KEY_ID': 'exported-key'}, clear=True):
                upload_videos.load_local_env()
                self.assertEqual(os.environ['R2_ACCOUNT_ID'], 'example-account')
                self.assertEqual(os.environ['AWS_ACCESS_KEY_ID'], 'exported-key')
                self.assertEqual(os.environ['AWS_SECRET_ACCESS_KEY'], 'example-secret')
                self.assertNotIn('UNRELATED', os.environ)


if __name__ == '__main__':
    unittest.main()
