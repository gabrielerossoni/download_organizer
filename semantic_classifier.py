"""Offline semantic routing: no Torch, Transformers, server or generative model."""
from pathlib import Path
import os


class SemanticClassifier:
    def __init__(self, cfg):
        # NumPy's BLAS thread stacks otherwise reserve hundreds of MB on this PC.
        os.environ["OPENBLAS_NUM_THREADS"] = "1"
        os.environ["OMP_NUM_THREADS"] = "1"
        import numpy as np
        import onnxruntime as ort
        import sentencepiece as spm
        self.np = np
        self.cfg = cfg
        root = Path(cfg.get("semantic_model_dir", Path(__file__).parent / "models" / "minilm"))
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        # Keep loading conservative; avoid extra optimized/prepacked weight copies.
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        options.add_session_config_entry("session.disable_prepacking", "1")
        self.session = ort.InferenceSession(str(root / "model.onnx"), options, providers=["CPUExecutionProvider"])
        self.tokenizer = spm.SentencePieceProcessor(model_file=str(root / "sentencepiece.bpe.model"))
        self.categories = [(kind, entry["name"], (entry.get("description") or entry["name"]) +
                            '\n' + '; '.join(entry.get('examples', [])[:5]))
                           for kind, key in (("school", "school_subjects"), ("personal", "personal_categories"))
                           for entry in cfg.get(key, []) if entry.get("folder")]
        # One sample at a time keeps activation memory independent of batch size.
        self.vectors = np.stack([self.encode(description) for _, _, description in self.categories])

    def encode(self, text):
        np = self.np
        # XLM-R's fairseq vocabulary shifts SentencePiece IDs by one; UNK is 3.
        pieces = self.tokenizer.encode(text, out_type=int)[:126]
        ids = np.asarray([[0] + [piece + 1 if piece else 3 for piece in pieces] + [2]], dtype=np.int64)
        inputs = {"input_ids": ids, "attention_mask": np.ones_like(ids), "token_type_ids": np.zeros_like(ids)}
        inputs = {item.name: inputs[item.name] for item in self.session.get_inputs()}
        output = self.session.run(None, inputs)[0]
        # No padding with single-sample inference, so no expanded attention-mask copy.
        vector = output[0].mean(axis=0)
        return vector / max(float(np.linalg.norm(vector)), 1e-9)

    def rank(self, filename, content):
        np = self.np
        text = Path(filename).stem.replace("_", " ").replace("-", " ") + "\n" + content[:800]
        scores = self.vectors @ self.encode(text)
        ranking = np.argsort(scores)[::-1]
        best = int(ranking[0])
        score = float(scores[best])
        margin = score - float(scores[int(ranking[1])]) if len(ranking) > 1 else score
        return best, score, margin

    def classify(self, filename, content):
        best, score, margin = self.rank(filename, content)
        if score < self.cfg.get("ai_min_similarity", 0.50) or margin < self.cfg.get("ai_min_margin", 0.10):
            return {"type": "unsure", "category": "", "confidence": 0, "reason": "ambiguous_similarity"}
        kind, name, _ = self.categories[best]
        return {"type": kind, "category": name, "confidence": score,
                "reason": f"semantic similarity={score:.3f}, margin={margin:.3f}; not a probability"}
