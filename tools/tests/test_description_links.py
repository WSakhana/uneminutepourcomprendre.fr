import sys
import unittest
import tempfile
import json
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from update_youtube_article_links import transform,extract_urls,verify_scheduled_article
import run_article_sync


class DescriptionLinksTest(unittest.TestCase):
    def setUp(self):self.url='https://uneminutepourcomprendre.fr/articles/exemple/'

    def test_preserves_chapters_hashtags_and_footer(self):
        before='Introduction.\n\nCHAPITRES\n00:00 Début\n01:00 Suite\n\nSources :\n- Auteur : https://doi.org/10.1234/abc\n\nUne question ?\n\n#Science #Animaux'
        new,refs=transform(before,self.url)
        self.assertIn('00:00 Début\n01:00 Suite',new)
        self.assertIn('Une question ?',new)
        self.assertIn('#Science #Animaux',new)
        self.assertNotIn('https://doi.org',new)
        self.assertIn('https://doi.org','\n'.join(refs))

    def test_keeps_ai_disclosure_from_source_list(self):
        new,refs=transform('Texte.\n\nSources :\n- Étude : https://example.org/study\n- Images illustratives générées par IA.',self.url)
        self.assertIn('Images illustratives générées par IA.',new)
        self.assertNotIn('Images illustratives','\n'.join(refs))

    def test_is_idempotent(self):
        new,_=transform('Texte.\n\nSources :\n- A : https://example.org',self.url)
        again,refs=transform(new,self.url)
        self.assertEqual(again,new)
        self.assertEqual(refs,[])

    def test_unheaded_source_bullet_and_music_are_transferred(self):
        new,refs=transform('Texte.\n\n- A : https://example.org\n\n- Musique : Auteur, titre',self.url)
        self.assertNotIn('Musique',new)
        self.assertIn('Musique','\n'.join(refs))

    def test_wikipedia_parentheses_are_preserved(self):
        url='https://en.wikipedia.org/wiki/Skyrock_(social_network_site)'
        self.assertEqual(extract_urls(url),[url])


class ScheduledDescriptionTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='description-links-test-')
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'article.toml'
        self.path.with_name('body.html').write_text('<section id="references-video-abc">https://example.org/study</section>',encoding='utf-8')
        self.meta={'status':'draft','ready':True,'video':{'id':'abc'},'sources':[{'url':'https://example.org/study'}]}
        self.video={'id':'abc','status':{'privacyStatus':'private','publishAt':'2030-01-01T12:00:00Z','uploadStatus':'processed','embeddable':True}}
        self.refs=['Sources : https://example.org/study']

    def test_scheduled_description_can_be_prepared_with_preserved_sources(self):
        self.assertTrue(verify_scheduled_article(self.path,self.meta,self.video,self.refs)[0])

    def test_private_unscheduled_and_unlisted_videos_remain_excluded(self):
        self.video['status'].pop('publishAt')
        self.assertFalse(verify_scheduled_article(self.path,self.meta,self.video,self.refs)[0])
        self.video['status'].update(privacyStatus='unlisted',publishAt='2030-01-01T12:00:00Z')
        self.assertFalse(verify_scheduled_article(self.path,self.meta,self.video,self.refs)[0])

    def test_missing_source_url_blocks_description_replacement(self):
        self.path.with_name('body.html').write_text('<section id="references-video-abc"></section>',encoding='utf-8')
        self.assertFalse(verify_scheduled_article(self.path,self.meta,self.video,self.refs)[0])

    def test_wrong_article_or_unready_draft_blocks_replacement(self):
        self.meta['video']['id']='other'
        self.assertFalse(verify_scheduled_article(self.path,self.meta,self.video,self.refs)[0])
        self.meta['video']['id']='abc';self.meta['ready']=False
        self.assertFalse(verify_scheduled_article(self.path,self.meta,self.video,self.refs)[0])

    def test_automation_never_calls_youtube_mutation_even_with_legacy_config_enabled(self):
        root=Path(self.temp.name);(root/'tracking').mkdir()
        (root/'tracking/youtube-description-links.local.json').write_text(json.dumps({'enabled':True}))
        with patch.object(run_article_sync,'ROOT',root),patch.object(run_article_sync,'environment_value',return_value=None),patch.object(run_article_sync.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as execute:
            with self.assertRaises(SystemExit) as result:run_article_sync.main()
        self.assertEqual(result.exception.code,0)
        scripts=[Path(call.args[0][1]).name for call in execute.call_args_list]
        self.assertEqual(scripts,['sync_youtube_articles.py','write_article_report.py'])


if __name__=='__main__':unittest.main()
