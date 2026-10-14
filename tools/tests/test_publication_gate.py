"""Vérifie les cas qui pourraient exposer une vidéo privée ou un brouillon."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_articles as build
from sync_youtube_articles import eligible, replace_scalar, resolve_missing_id


class PublicationGateTest(unittest.TestCase):
    def setUp(self):
        self.meta = {'ready': True, 'video': {'id': 'abcdefghijk'}}
        self.public = {'abcdefghijk': {'status': {'privacyStatus': 'public', 'embeddable': True, 'uploadStatus': 'processed'}, 'snippet': {'liveBroadcastContent': 'none'}}}

    def test_only_processed_public_embeddable_video_is_eligible(self):
        self.assertTrue(eligible(self.meta, self.public))
        for field, value in [('privacyStatus', 'private'), ('privacyStatus', 'unlisted'), ('embeddable', False), ('uploadStatus', 'uploaded')]:
            data = copy.deepcopy(self.public)
            data['abcdefghijk']['status'][field] = value
            self.assertFalse(eligible(self.meta, data), (field, value))

    def test_date_in_the_past_does_not_publish_private_video(self):
        self.public['abcdefghijk']['status'].update(privacyStatus='private', publishAt='2020-01-01T00:00:00Z')
        self.assertFalse(eligible(self.meta, self.public))

    def test_unknown_identity_or_unready_article_fails_closed(self):
        self.assertFalse(eligible(self.meta, {}))
        self.assertFalse(eligible({'ready': False, 'video': {'id': 'abcdefghijk'}}, self.public))
        self.assertFalse(eligible({'ready': True, 'video': {'id': ''}}, self.public))

    def test_all_parts_must_be_public(self):
        self.meta['additional_videos'] = [{'id': 'lmnopqrstuv'}]
        self.assertFalse(eligible(self.meta, self.public))

    def test_upcoming_live_video_is_not_released(self):
        self.public['abcdefghijk']['snippet']['liveBroadcastContent'] = 'upcoming'
        self.assertFalse(eligible(self.meta, self.public))

    def test_missing_id_requires_unique_filename_and_duration(self):
        meta = {'editorial_ready': True, 'project_key': 'short-14', 'video_file': 'Montage/UMPC-R 14 - avion.mp4', 'video': {'id': '', 'duration_seconds': 30.5}}
        video = {'id': 'abcdefghijk', 'fileDetails': {'fileName': 'UMPC-R 14 - avion.mp4'}, 'contentDetails': {'duration': 'PT31S'}}
        self.assertEqual(resolve_missing_id(meta, {'abcdefghijk': video}, set()), video)
        self.assertIsNone(resolve_missing_id(meta, {'abcdefghijk': video, 'lmnopqrstuv': video}, set()))
        self.assertIsNone(resolve_missing_id(meta, {'abcdefghijk': video}, {'abcdefghijk'}))
        video['contentDetails']['duration'] = 'PT60S'
        self.assertIsNone(resolve_missing_id(meta, {'abcdefghijk': video}, set()))

    def test_scalar_update_preserves_the_video_table(self):
        original = 'slug = "a"\nstatus = "draft"\n\n[video]\nstatus = "private"\n'
        self.assertEqual(replace_scalar(original, 'status', 'published'), 'slug = "a"\nstatus = "published"\n\n[video]\nstatus = "private"\n')

    def test_draft_is_not_loaded_or_rendered(self):
        with tempfile.TemporaryDirectory(prefix='publication-gate-test-') as tmp:
            root = Path(tmp); content = root/'content'; public = root/'public'; draft = content/'hidden'
            draft.mkdir(parents=True);public.mkdir()
            (draft/'article.toml').write_text('slug = "hidden"\nstatus = "draft"\n', encoding='utf-8')
            (draft/'body.html').write_text('<p>Contenu privé incomplet</p>', encoding='utf-8')
            with patch.object(build, 'CONTENT', content), patch.object(build, 'PUBLIC', public):
                self.assertEqual(build.load_articles(), [])
                stale = public/'articles/hidden'; stale.mkdir(parents=True)
                (stale/'index.html').write_text('ancienne page', encoding='utf-8')
                with self.assertRaises(SystemExit):
                    build.load_articles()


if __name__ == '__main__':
    unittest.main()
