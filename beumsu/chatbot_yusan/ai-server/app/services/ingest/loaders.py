from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


class OfficialDataLoader:
    """Load official heritage data from JSON or a directory of CSV files.

    JSON format:
      {
        "entities": [...],
        "aliases": [...],
        "documents": [...],
        "relations": [...],
        "images": [...]
      }

    CSV directory format:
      entities.csv, aliases.csv, documents.csv, relations.csv, images.csv
    """

    def load(self, path: str | Path) -> dict[str, list[dict[str, Any]]]:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"Official data path does not exist: {source}")
        if source.is_dir():
            return self._load_directory(source)
        if source.suffix.lower() == ".json":
            return self._load_json(source)
        raise ValueError(f"Unsupported official data format: {source.suffix}")

    def _load_json(self, path: Path) -> dict[str, list[dict[str, Any]]]:
        with path.open("r", encoding="utf-8-sig") as fp:
            data = json.load(fp)
        return self._normalize_dataset(data)

    def _load_directory(self, path: Path) -> dict[str, list[dict[str, Any]]]:
        return self._normalize_dataset(
            {
                "entities": self._load_csv(path / "entities.csv"),
                "aliases": self._load_csv(path / "aliases.csv"),
                "documents": self._load_csv(path / "documents.csv"),
                "relations": self._load_csv(path / "relations.csv"),
                "images": self._load_csv(path / "images.csv"),
            }
        )

    def _load_csv(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            return [dict(row) for row in csv.DictReader(fp)]

    def _normalize_dataset(self, data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        return {
            "entities": list(data.get("entities") or []),
            "aliases": list(data.get("aliases") or []),
            "documents": list(data.get("documents") or []),
            "relations": list(data.get("relations") or []),
            "images": list(data.get("images") or []),
        }
