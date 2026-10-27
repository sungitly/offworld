"""Regression checks for original-file isolation and private build defaults."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import process


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


if __name__ == '__main__':
    unittest.main()
