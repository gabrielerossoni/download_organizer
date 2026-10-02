"""Download only the two pinned official files; verify their SHA-256."""
import hashlib
from pathlib import Path
from urllib.request import urlopen

REPOSITORY = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
FILES = (
    ("onnx/model_quint8_avx2.onnx", "model.onnx", 118453870, "98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f"),
    ("sentencepiece.bpe.model", "sentencepiece.bpe.model", 5069051, "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865"),
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    root = Path(__file__).resolve().parent.parent / "models" / "minilm"
    root.mkdir(parents=True, exist_ok=True)
    for remote, local, size, expected in FILES:
        target = root / local
        if target.exists() and target.stat().st_size == size and digest(target) == expected:
            print(f"Already verified: {local}")
            continue
        partial = target.with_suffix(".part")
        count = 0
        checksum = hashlib.sha256()
        try:
            with urlopen(f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{remote}", timeout=60) as source, partial.open("wb") as output:
                while chunk := source.read(65536):
                    count += len(chunk)
                    if count > size:
                        raise ValueError("Download exceeded expected size")
                    checksum.update(chunk)
                    output.write(chunk)
            if count != size or checksum.hexdigest() != expected:
                raise ValueError(f"Hash/size mismatch: {local}")
            partial.replace(target)
            print(f"Installed and verified: {local} ({size} bytes)")
        finally:
            partial.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
