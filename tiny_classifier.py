"""Sparse TF-IDF centroids: local, stdlib-only and allowed to abstain."""
import json
import math
import re
from collections import Counter
from pathlib import Path


def tokens(filename, content):
    text = Path(filename).stem.replace('_', ' ').replace('-', ' ') + '\n' + content[:800]
    return Counter(re.findall(r"[^\W\d_]{3,}", text.casefold()))


def vector(counts, idf):
    values = {word: (1 + math.log(count)) * idf[word]
              for word, count in counts.items() if word in idf}
    norm = math.sqrt(sum(value * value for value in values.values())) or 1
    return {word: value / norm for word, value in values.items()}


def fit(rows, categories):
    counts = [tokens(row['filename'], row['content']) for row in rows]
    frequency = Counter(word for count in counts for word in count)
    # ponytail: 1000 words bound model size; enlarge only after held-out improvement.
    idf = {word: math.log((1 + len(rows)) / (1 + freq)) + 1
           for word, freq in frequency.most_common(1000) if freq >= 2}
    centroids = []
    for kind, name in categories:
        total = Counter()
        for row, count in zip(rows, counts):
            if (row['kind'], row['label']) == (kind, name):
                total.update(vector(count, idf))
        norm = math.sqrt(sum(value * value for value in total.values())) or 1
        centroids.append({word: round(value / norm, 6) for word, value in total.items()})
    return {'version': 1, 'categories': categories, 'idf': idf, 'centroids': centroids,
            'min_score': 1.01, 'min_margin': 1.01, 'reviewed': False}


class TinyClassifier:
    def __init__(self, cfg):
        path = Path(cfg.get('tiny_model_path', Path(__file__).parent / 'models' / 'tiny.json'))
        if path.stat().st_size > 1_000_000:
            raise ValueError('Il modello tiny supera 1 MB su disco')
        self.model = json.loads(path.read_text(encoding='utf-8'))
        if self.model.get('version') != 1 or not self.model.get('reviewed'):
            raise ValueError('Modello sperimentale: verificare prima le etichette')
        allowed = {(kind, entry['name']) for kind, key in
                   (('school', 'school_subjects'), ('personal', 'personal_categories'))
                   for entry in cfg.get(key, []) if entry.get('folder')}
        if set(map(tuple, self.model['categories'])) != allowed:
            raise ValueError('Categorie cambiate: rivalutare e riaddestrare tiny')

    def classify(self, filename, content):
        index, score, margin = rank(self.model, filename, content)
        if score < self.model['min_score'] or margin < self.model['min_margin']:
            return {'type': 'unsure', 'category': '', 'confidence': 0, 'reason': 'tiny_ambiguous'}
        kind, name = self.model['categories'][index]
        return {'type': kind, 'category': name, 'confidence': score,
                'reason': f'tiny similarity={score:.3f}, margin={margin:.3f}; not a probability'}


def rank(model, filename, content):
    values = vector(tokens(filename, content), model['idf'])
    scores = [sum(value * centroid.get(word, 0) for word, value in values.items())
              for centroid in model['centroids']]
    order = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)
    index = order[0]
    score = scores[index]
    return index, score, score - scores[order[1]] if len(order) > 1 else score
