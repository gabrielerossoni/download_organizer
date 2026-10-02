"""Collect local examples, review CSV labels, calibrate on separate project groups.

Never moves files. Folder-derived labels are explicitly unverified.
"""
import argparse
import csv
import hashlib
import json
import logging
import os
from collections import Counter, defaultdict
from pathlib import Path

from organizer import AIClassifier, CONFIG_PATH
from tiny_classifier import fit, rank

ROOT = Path(__file__).parent
DATA = ROOT / 'memory' / 'classification'
SKIP = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', 'dist', 'build', 'target', 'bin', 'obj'}
EXTENSIONS = {'.pdf', '.docx', '.txt', '.md', '.csv', '.py', '.java', '.c', '.cpp', '.html'}
FIELDS = ['path', 'filename', 'content', 'kind', 'label', 'group', 'reviewed']


def categories(cfg):
    return [(kind, entry) for kind, key in (('school', 'school_subjects'), ('personal', 'personal_categories'))
            for entry in cfg.get(key, []) if entry.get('folder')]


def collect(cfg, school_roots, projects_root):
    sources = []
    for kind, entry in categories(cfg):
        sources.append((kind, entry['name'], Path(entry['folder'])))
    aliases = {'Sistemi_Reti': 'Sistemi', 'Tecnologia': 'Tecnologie', 'Corsi_Esterni': 'Corsi Esterni'}
    names = {entry['name'] for kind, entry in categories(cfg) if kind == 'school'}
    for root in school_roots:
        for directory in sorted(Path(root).iterdir()):
            name = aliases.get(directory.name, directory.name)
            if directory.is_dir() and name in names:
                sources.append(('school', name, directory))
    if projects_root:
        sources.append(('personal', 'Progetti', Path(projects_root)))
    sources = list({(kind, name, str(path.resolve()).casefold()): (kind, name, path)
                    for kind, name, path in sources}.values())
    extractor = AIClassifier(cfg, logging.getLogger('lab'))
    rows, seen = [], set()
    shared = Counter(str(path.resolve()).casefold() for _, _, path in sources)
    skipped_shared = 0
    for kind, name, root in sources:
        if shared[str(root.resolve()).casefold()] > 1:
            skipped_shared += 1
            continue  # Italiano/Storia share a folder: no fabricated gold labels.
        if not root.is_dir() or root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
            continue
        group_counts = Counter()
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith('.')
                             and not (Path(directory) / d).is_symlink()
                             and not getattr(Path(directory) / d, 'is_junction', lambda: False)())
            for filename in sorted(files):
                path = Path(directory) / filename
                if path.is_symlink() or filename.startswith('.') or path.suffix.lower() not in EXTENSIONS or path.stat().st_size > 10_000_000:
                    continue
                # Personal source repositories are represented by documentation, not vendor/code files.
                if kind == 'personal' and path.suffix.lower() not in {'.md', '.pdf', '.docx', '.txt'}:
                    continue
                relative = path.relative_to(root)
                parts = list(relative.parts[:-1])
                if 'src' in parts:
                    parts = parts[:parts.index('src')]
                group = str(root / Path(*parts)) if parts else str(root)
                if kind == 'personal':
                    # All documentation of one personal repository stays in one partition.
                    group = str(root / Path(*parts[:2])) if parts else str(root)
                if group_counts[group] >= 12:
                    continue
                content = extractor._extract_text(path)
                # Group duplicates by content; empty extraction uses normalized filename.
                signature = hashlib.sha256((content.strip() or Path(filename).stem.casefold()).encode()).hexdigest()
                if signature in seen:
                    continue
                seen.add(signature)
                group_counts[group] += 1
                rows.append(dict(path=str(path), filename=filename, content=content, kind=kind,
                                 label=name, group=group, reviewed='no'))
    DATA.mkdir(parents=True, exist_ok=True)
    target = DATA / 'examples.csv'
    if target.exists():
        raise ValueError('examples.csv esiste: conservarlo o rinominarlo prima di raccogliere di nuovo')
    with target.open('w', newline='', encoding='utf-8-sig') as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'examples': len(rows), 'by_label': dict(Counter(r['label'] for r in rows)),
                      'shared_sources_skipped': skipped_shared, 'csv': str(target)}, ensure_ascii=False, indent=2))


def split(rows):
    # Whole project groups stay together, including groups with conflicting reviewed labels.
    partitions = ([], [], [])
    groups = defaultdict(list)
    for row in rows:
        groups[row['group']].append(row)
    counts = Counter()
    for group in sorted(groups, key=lambda group: hashlib.sha256(group.encode()).hexdigest()):
        label = min((r['kind'], r['label']) for r in groups[group])
        number = counts[label]
        counts[label] += 1
        index = (0, 1, 2)[number % 3]
        partitions[index].extend(groups[group])
    return partitions


def metrics(predictions, minimum, margin):
    accepted = [r for r in predictions if r['score'] >= minimum and r['margin'] >= margin]
    correct = sum(r['correct'] for r in accepted)
    return {'total': len(predictions), 'accepted': len(accepted), 'errors': len(accepted) - correct,
            'precision': round(correct / len(accepted), 4) if accepted else None,
            'coverage': round(len(accepted) / len(predictions), 4) if predictions else 0}


def calibrate(predictions):
    best, thresholds = 0, (1.01, 1.01)
    for minimum in sorted({r['score'] for r in predictions if r['score'] > 0}):
        for margin in sorted({r['margin'] for r in predictions if r['margin'] > 0}):
            result = metrics(predictions, minimum, margin)
            # Zero observed errors on >=5 independent validation files is only an experimental gate.
            if result['accepted'] >= 5 and result['errors'] == 0 and result['accepted'] > best:
                best, thresholds = result['accepted'], (minimum, margin)
    return thresholds


def evaluate(cfg, use_semantic):
    with (DATA / 'examples.csv').open(newline='', encoding='utf-8-sig') as source:
        rows = list(csv.DictReader(source))
    allowed = {(kind, entry['name']) for kind, entry in categories(cfg)}
    if not rows or any((r['kind'], r['label']) not in allowed or not r['group'] for r in rows):
        raise ValueError('Etichette o gruppi non validi nel CSV')
    # Editing can introduce duplicates; exclude ALL conflicting labels, not just the last one.
    duplicates = defaultdict(list)
    for row in rows:
        key = (row['content'].strip() or Path(row['filename']).stem.casefold())
        duplicates[key].append(row)
    clean = [items[0] for items in duplicates.values()
             if len({(r['kind'], r['label']) for r in items}) == 1]
    train, validation, test = split(clean)
    active = sorted(allowed)
    model = fit(train, active)
    report = {'label_source': 'human' if all(r['reviewed'].lower() == 'yes' for r in clean) else 'unverified_folders',
              'split': {name: dict(Counter(r['label'] for r in part))
                        for name, part in zip(('train', 'validation', 'test'), (train, validation, test))},
              'discarded_duplicates_or_conflicts': len(rows) - len(clean),
              'limitations': 'Folder labels may be wrong. Whole groups held out. Missing classes and unfamiliar documents remain unvalidated. No moves.'}
    predictions = {}
    for name, part in (('validation', validation), ('test', test)):
        predictions[name] = []
        for row in part:
            index, score, margin = rank(model, row['filename'], row['content'])
            predictions[name].append({'path': row['path'], 'expected': row['label'],
                                      'predicted': active[index][1], 'score': score, 'margin': margin,
                                      'correct': active[index] == (row['kind'], row['label'])})
    minimum, margin = calibrate(predictions['validation'])
    model.update(min_score=minimum, min_margin=margin)
    result = metrics(predictions['test'], minimum, margin)
    # No experimental artifact can accidentally become the runtime model.
    sparse = {name: [category for kind, category in active
                     if sum((r['kind'], r['label']) == (kind, category) for r in part) < 3]
              for name, part in zip(('train', 'validation', 'test'), (train, validation, test))}
    model['reviewed'] = (report['label_source'] == 'human' and result['accepted'] >= 10
                         and result['errors'] == 0 and not any(sparse.values()))
    report['tiny'] = {'min_score': minimum, 'min_margin': margin,
                      'validation': metrics(predictions['validation'], minimum, margin), 'test': result,
                      'unfiltered_test': metrics(predictions['test'], 0, 0),
                      'missing_or_sparse_categories': sparse,
                      'eligible_for_manual_activation': model['reviewed']}
    target = ROOT / 'models' / 'tiny-candidate.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(model, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    report['tiny']['model_bytes'] = target.stat().st_size
    if use_semantic:
        from semantic_classifier import SemanticClassifier
        semantic = SemanticClassifier(cfg)
        sem = {}
        for name, part in (('validation', validation), ('test', test)):
            sem[name] = []
            for row in part:
                index, score, distance = semantic.rank(row['filename'], row['content'])
                kind, category, _ = semantic.categories[index]
                sem[name].append({'path': row['path'], 'expected': row['label'], 'predicted': category,
                                  'score': score, 'margin': distance,
                                  'correct': (kind, category) == (row['kind'], row['label'])})
        minimum, margin = calibrate(sem['validation'])
        report['semantic'] = {'calibration_found': minimum <= 1,
                              'suggested_similarity': minimum if minimum <= 1 else None,
                              'suggested_margin': margin if minimum <= 1 else None,
                              'validation': metrics(sem['validation'], minimum, margin),
                              'test': metrics(sem['test'], minimum, margin),
                              'unfiltered_test': metrics(sem['test'], 0, 0),
                              'current_thresholds_test': metrics(sem['test'], cfg.get('ai_min_similarity', .5), cfg.get('ai_min_margin', .1))}
        predictions['semantic'] = sem
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'predictions.json').write_text(json.dumps(predictions, ensure_ascii=False, indent=2), encoding='utf-8')
    (DATA / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('collect', 'evaluate'))
    parser.add_argument('--school-root', action='append', default=[])
    parser.add_argument('--projects-root')
    parser.add_argument('--semantic', action='store_true')
    args = parser.parse_args()
    cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    if args.action == 'collect':
        collect(cfg, args.school_root, args.projects_root)
    else:
        evaluate(cfg, args.semantic)


if __name__ == '__main__':
    main()
