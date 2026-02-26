#!/usr/bin/env python3
"""
Initialize one KB per PDF from ../documents, then generate profiles.

Flow per PDF:
  1) Create KB (name derived from PDF filename)
  2) Process document into RAG KB
  3) Generate knowledge scope
  4) Generate student profiles
  5) Save outputs under benchmark/data/generated/profiles_from_documents_<timestamp>/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import yaml

from benchmark.data_generation.profile_generator import generate_profiles_for_kb
from benchmark.data_generation.scope_generator import generate_knowledge_scope
from src.knowledge.initializer import KnowledgeBaseInitializer

logger = logging.getLogger("benchmark.init_kbs_profiles")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "benchmark" / "config" / "benchmark_config.yaml"
DEFAULT_DOCS_DIR = PROJECT_ROOT.parent / "documents"


def _sanitize_kb_name(name: str) -> str:
    """Convert filename stem into a valid kb_name."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "kb"


def _unique_name(base: str, used: set[str]) -> str:
    """Make KB name unique in current run."""
    if base not in used:
        used.add(base)
        return base
    i = 2
    while f"{base}_{i}" in used:
        i += 1
    name = f"{base}_{i}"
    used.add(name)
    return name


def _load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


async def _process_pdf(
    *,
    pdf_path: Path,
    kb_name: str,
    kb_base_dir: Path,
    profile_cfg: dict,
    rag_cfg: dict,
    output_dir: Path,
    skip_extract: bool,
) -> dict:
    """Initialize KB from one PDF and generate profiles."""
    logger.info("=" * 70)
    logger.info("PDF: %s", pdf_path.name)
    logger.info("KB : %s", kb_name)
    logger.info("=" * 70)

    initializer = KnowledgeBaseInitializer(
        kb_name=kb_name,
        base_dir=str(kb_base_dir),
    )
    initializer.create_directory_structure()
    copied = initializer.copy_documents([str(pdf_path)])
    if not copied:
        raise RuntimeError(f"Failed to copy PDF: {pdf_path}")

    await initializer.process_documents()
    if not skip_extract:
        initializer.extract_numbered_items()

    scope = await generate_knowledge_scope(
        kb_name=kb_name,
        seed_queries=rag_cfg.get("seed_queries"),
        mode=rag_cfg.get("mode", "naive"),
        kb_base_dir=str(kb_base_dir),
    )

    profiles = await generate_profiles_for_kb(
        knowledge_scope=scope,
        background_types=profile_cfg.get(
            "background_types", ["beginner", "intermediate", "advanced"]
        ),
        profiles_per_kb=profile_cfg.get("profiles_per_subtopic", 3),
    )

    out = {
        "pdf_file": str(pdf_path),
        "kb_name": kb_name,
        "knowledge_scope": scope,
        "profiles": profiles,
        "num_profiles": len(profiles),
    }
    out_path = output_dir / f"{kb_name}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    logger.info("Saved: %s", out_path)
    return out


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialize one KB per PDF in ../documents, then generate profiles."
    )
    parser.add_argument(
        "--docs-dir",
        default=str(DEFAULT_DOCS_DIR),
        help=f"Directory containing PDF files (default: {DEFAULT_DOCS_DIR})",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help=f"Benchmark config path (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Skip numbered items extraction for faster initialization",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process first N PDFs (0 = all)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    docs_dir = Path(args.docs_dir)
    if not docs_dir.is_absolute():
        docs_dir = (PROJECT_ROOT / docs_dir).resolve()
    if not docs_dir.exists():
        raise FileNotFoundError(f"Documents dir not found: {docs_dir}")

    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = (PROJECT_ROOT / cfg_path).resolve()
    cfg = _load_config(cfg_path)

    kb_base_dir = Path(
        cfg.get("knowledge_bases", {}).get("base_dir", "./data/knowledge_bases")
    )
    if not kb_base_dir.is_absolute():
        kb_base_dir = (PROJECT_ROOT / kb_base_dir).resolve()

    profile_cfg = cfg.get("profile_generation", {})
    rag_cfg = cfg.get("rag_query", {})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = PROJECT_ROOT / "benchmark" / "data" / "generated" / f"profiles_from_documents_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(docs_dir.glob("*.pdf"))
    if args.limit and args.limit > 0:
        pdfs = pdfs[: args.limit]
    if not pdfs:
        raise ValueError(f"No PDF files found in: {docs_dir}")

    used_names: set[str] = set()
    results = []
    for pdf in pdfs:
        kb_name = _unique_name(_sanitize_kb_name(pdf.stem), used_names)
        try:
            result = await _process_pdf(
                pdf_path=pdf,
                kb_name=kb_name,
                kb_base_dir=kb_base_dir,
                profile_cfg=profile_cfg,
                rag_cfg=rag_cfg,
                output_dir=output_dir,
                skip_extract=args.skip_extract,
            )
            results.append(result)
        except Exception as e:
            logger.exception("Failed on %s -> %s: %s", pdf.name, kb_name, e)

    summary = {
        "timestamp": timestamp,
        "docs_dir": str(docs_dir),
        "kb_base_dir": str(kb_base_dir),
        "num_pdfs": len(pdfs),
        "num_success": len(results),
        "results": [
            {
                "pdf_file": r["pdf_file"],
                "kb_name": r["kb_name"],
                "num_profiles": r["num_profiles"],
            }
            for r in results
        ],
    }
    summary_path = output_dir / "_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\nDone.")
    print(f"Output dir: {output_dir}")
    print(f"Summary: {summary_path}")
    print(f"Success: {len(results)}/{len(pdfs)} PDFs")


if __name__ == "__main__":
    asyncio.run(main())
