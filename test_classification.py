import json
import logging
import tempfile
import unittest
from pathlib import Path

from classification_lab import calibrate, metrics, split
from tiny_classifier import TinyClassifier, fit, rank
from organizer import AIClassifier


class ClassificationTests(unittest.TestCase):
    def test_small_classifier_learns_and_rejects_unknown(self):
        categories = [('school', 'Reti'), ('school', 'TPSIT')]
        rows = [{'kind': 'school', 'label': label, 'filename': 'appunti.txt', 'content': text}
                for label, text in [('Reti', 'router subnet indirizzo'), ('Reti', 'subnet router rete'),
                                    ('TPSIT', 'thread mutex processi'), ('TPSIT', 'mutex thread fork')]]
        model = fit(rows, categories)
        self.assertEqual(rank(model, 'lezione.txt', 'router subnet')[0], 0)
        self.assertEqual(rank(model, 'lezione.txt', 'thread mutex')[0], 1)
        self.assertEqual(rank(model, 'xyz.txt', 'qwerty')[1:], (0, 0))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'model.json'
            path.write_text(json.dumps(model), encoding='utf-8')
            cfg = {'tiny_model_path': str(path), 'school_subjects':
                   [{'name': name, 'folder': temporary} for _, name in categories]}
            with self.assertRaisesRegex(ValueError, 'sperimentale'):
                TinyClassifier(cfg)
            model.update(reviewed=True, min_score=.3, min_margin=.1)
            path.write_text(json.dumps(model), encoding='utf-8')
            classifier = TinyClassifier(cfg)
            self.assertEqual(classifier.classify('lezione.txt', 'thread mutex')['category'], 'TPSIT')
            self.assertEqual(classifier.classify('xyz.txt', 'qwerty')['type'], 'unsure')
            document = Path(temporary) / 'lezione.txt'
            document.write_text('thread mutex', encoding='utf-8')
            cfg.update(ai_enabled=True, ai_backend='tiny', ai_auto_move=False)
            self.assertEqual(AIClassifier(cfg, logging.getLogger('test')).classify(document, '.txt')['reason'],
                             'review_required')
            cfg['school_subjects'][0]['name'] = 'Nuova categoria'
            with self.assertRaisesRegex(ValueError, 'Categorie cambiate'):
                TinyClassifier(cfg)
            path.write_text(' ' * 1_000_001, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'supera 1 MB'):
                TinyClassifier(cfg)

    def test_collection_preserves_review_and_excludes_shared_folder(self):
        import classification_lab as lab
        from unittest.mock import patch
        from contextlib import redirect_stdout
        from io import StringIO
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            school = root / 'school'
            school.mkdir()
            (school / 'fork.txt').write_text('processi Unix', encoding='utf-8')
            cfg = {'school_subjects': [{'name': 'TPSIT', 'folder': str(school)}]}
            with patch.object(lab, 'DATA', root / 'data'), redirect_stdout(StringIO()):
                lab.collect(cfg, [], None)
                original = (lab.DATA / 'examples.csv').read_bytes()
                with self.assertRaisesRegex(ValueError, 'esiste'):
                    lab.collect(cfg, [], None)
                self.assertEqual((lab.DATA / 'examples.csv').read_bytes(), original)
            cfg['school_subjects'].append({'name': 'Informatica', 'folder': str(school)})
            with patch.object(lab, 'DATA', root / 'shared'), redirect_stdout(StringIO()):
                lab.collect(cfg, [], None)
                import csv
                with (lab.DATA / 'examples.csv').open(encoding='utf-8-sig', newline='') as source:
                    self.assertEqual(list(csv.DictReader(source)), [])

    def test_project_groups_never_leak_between_partitions(self):
        rows = [{'kind': 'school', 'label': 'Reti', 'group': f'project-{g}', 'filename': f'{i}.txt'}
                for g in range(9) for i in range(3)]
        parts = split(rows)
        self.assertEqual(sum(map(len, parts)), len(rows))
        groups = [set(r['group'] for r in part) for part in parts]
        self.assertFalse(groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
        self.assertEqual([set(r['filename'] + r['group'] for r in p) for p in parts],
                         [set(r['filename'] + r['group'] for r in p) for p in split(list(reversed(rows)))])

    def test_calibration_does_not_accept_wrong_confident_predictions(self):
        bad = [{'score': .9, 'margin': .5, 'correct': False}] * 6
        minimum, margin = calibrate(bad)
        self.assertEqual(metrics(bad, minimum, margin)['accepted'], 0)
        good = [{'score': .9, 'margin': .5, 'correct': True}] * 6
        minimum, margin = calibrate(good + [{'score': .2, 'margin': .1, 'correct': False}])
        self.assertEqual(metrics(good, minimum, margin)['accepted'], 6)


if __name__ == '__main__':
    unittest.main()
