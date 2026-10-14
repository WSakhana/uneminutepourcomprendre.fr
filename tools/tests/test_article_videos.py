"""Vérifie les lecteurs et données structurées d'un article à une ou plusieurs vidéos."""
import copy
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_articles as build


class ArticleVideosTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.article = next(a for a in build.load_articles() if a['slug'] == 'animaux-squelettes-etonnants')
        cls.original_public = build.PUBLIC
        cls.temp = tempfile.TemporaryDirectory(prefix='article-videos-test-')
        build.PUBLIC = Path(cls.temp.name) / 'public'
        shutil.copytree(cls.original_public, build.PUBLIC)
        cls.sizes = build.build_images(cls.article, False)

    @classmethod
    def tearDownClass(cls):
        build.PUBLIC = cls.original_public
        cls.temp.cleanup()

    def render(self, article):
        build.article_page(article, self.sizes)
        return (build.PUBLIC / 'articles' / article['slug'] / 'index.html').read_text(encoding='utf-8')

    def graph(self, page):
        match = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
        return json.loads(match.group(1))['@graph']

    def test_two_players_before_the_article_title(self):
        page = self.render(self.article)
        players = re.findall(r'<iframe[^>]*src="([^"]+)"', page)
        self.assertEqual(len(players), 2)
        self.assertIn('/embed/rwS44FiCKaQ?', players[0])
        self.assertIn('/embed/dS6oZUkzHo8?', players[1])
        self.assertLess(page.rindex('</iframe>'), page.index('<h1'))

    def test_both_video_objects_are_linked_to_the_article(self):
        page = self.render(self.article)
        graph = self.graph(page)
        article = next(n for n in graph if n['@type'] == 'Article')
        videos = [n for n in graph if n['@type'] == 'VideoObject']
        self.assertEqual({n['@id'] for n in videos}, {ref['@id'] for ref in article['video']})
        self.assertEqual([n['uploadDate'] for n in videos], ['2026-09-13', '2026-10-02'])
        self.assertNotEqual(videos[0]['thumbnailUrl'], videos[1]['thumbnailUrl'])

    def test_single_video_keeps_its_existing_contract(self):
        article = copy.deepcopy(self.article)
        article.pop('additional_videos')
        page = self.render(article)
        graph = self.graph(page)
        self.assertEqual(page.count('<iframe '), 1)
        self.assertNotIn('class="article-videos"', page)
        node = next(n for n in graph if n['@type'] == 'Article')
        self.assertIsInstance(node['video'], dict)
        self.assertEqual(node['video']['@id'], next(n for n in graph if n['@type'] == 'VideoObject')['@id'])
        self.assertIn('Regarder sur YouTube', page)

    def test_card_announces_the_number_of_videos(self):
        card = build.card(self.article, self.sizes, 2)
        self.assertIn('2 vidéos', card)
        self.assertNotIn('vidéo de ', card)


if __name__ == '__main__':
    unittest.main()
