#!/usr/bin/env python3
"""
SciDK Model Benchmarker
-----------------------
Run a prompt set against multiple Ollama models, collect timing + meta-stats,
and optionally score responses for quality.

Usage:
    python scidk_bench.py                        # interactive mode
    python scidk_bench.py --prompts prompts.txt  # load prompts from file
    python scidk_bench.py --no-score             # skip user scoring
    python scidk_bench.py --report results.json  # load saved run, show report
"""

import argparse
import json
import time
import sys
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import ollama
except ImportError:
    print("Install ollama Python client: pip install ollama")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Default prompt set — replace or extend with domain-specific queries
# ---------------------------------------------------------------------------

DEFAULT_PROMPTS = [
    # Factual / short expected answer
    {
        "id": "factual-1",
        "type": "factual",
        "text": "How many lobes does a mouse lung have? Answer in one sentence.",
    },
    # Cypher / tool-relevant
    {
        "id": "cypher-1",
        "type": "cypher",
        "text": "Write a Cypher query to find all Sample nodes connected to an Experiment node.",
    },
    # Reasoning
    {
        "id": "reasoning-1",
        "type": "reasoning",
        "text": (
            "A researcher ran the same imaging protocol on two different mouse strains "
            "and got different results. What are three possible explanations?"
        ),
    },
    # Structured output
    {
        "id": "structured-1",
        "type": "structured",
        "text": (
            "List the key differences between mouse and human lung anatomy. "
            "Respond as a JSON array of objects with keys 'feature' and 'difference'."
        ),
    },
    # Grounded / context-aware (tests whether model uses provided context)
    {
        "id": "grounded-1",
        "type": "grounded",
        "text": (
            "Given this Neo4j schema context:\n"
            "  Nodes: Sample, Experiment, Researcher, File, Protocol\n"
            "  Relationships: (Researcher)-[:RUNS]->(Experiment)-[:HAS_SAMPLE]->(Sample)\n"
            "Write a Cypher query to find all samples belonging to experiments "
            "run by researcher named 'Dr. Smith'."
        ),
    },
]


# ---------------------------------------------------------------------------
# Scoring rubric shown to user
# ---------------------------------------------------------------------------

SCORING_RUBRIC = """
Score the response on a scale of 1-5:
  5 — Excellent: accurate, appropriately detailed, no padding
  4 — Good: mostly correct, minor issues
  3 — Acceptable: correct direction but missing key details or too verbose
  2 — Poor: partially correct or significantly off
  1 — Fail: wrong, hallucinated, or refused to answer
"""


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def compute_meta_stats(response_text: str, elapsed: float) -> dict:
    """Compute objective meta-statistics for a response."""
    words = response_text.split()
    sentences = [s.strip() for s in re.split(r'[.!?]+', response_text) if s.strip()]
    lines = [l for l in response_text.splitlines() if l.strip()]
    code_blocks = re.findall(r'```[\s\S]*?```', response_text)
    cypher_keywords = sum(
        1 for kw in ['MATCH', 'RETURN', 'WHERE', 'CREATE', 'MERGE', 'WITH', 'OPTIONAL']
        if kw in response_text.upper()
    )

    return {
        "elapsed_sec": round(elapsed, 2),
        "char_count": len(response_text),
        "word_count": len(words),
        "sentence_count": len(sentences),
        "line_count": len(lines),
        "code_blocks": len(code_blocks),
        "cypher_keywords": cypher_keywords,
        "words_per_second": round(len(words) / elapsed, 1) if elapsed > 0 else 0,
        "avg_sentence_length": round(len(words) / len(sentences), 1) if sentences else 0,
    }


# ---------------------------------------------------------------------------
# Single model run
# ---------------------------------------------------------------------------

def run_prompt(model: str, prompt: dict, system_prompt: Optional[str] = None) -> dict:
    """Run a single prompt against a model and return full result dict."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt["text"]})

    print(f"  → Running on {model}...", end="", flush=True)
    start = time.time()

    try:
        response = ollama.chat(model=model, messages=messages)
        elapsed = time.time() - start
        content = response["message"]["content"]
        status = "ok"
    except Exception as e:
        elapsed = time.time() - start
        content = f"[ERROR: {e}]"
        status = "error"

    stats = compute_meta_stats(content, elapsed)
    print(f" {elapsed:.1f}s / {stats['word_count']} words")

    return {
        "model": model,
        "prompt_id": prompt["id"],
        "prompt_type": prompt["type"],
        "prompt_text": prompt["text"],
        "response": content,
        "status": status,
        "stats": stats,
        "score": None,
        "score_notes": None,
        "timestamp": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# User scoring
# ---------------------------------------------------------------------------

def score_result(result: dict) -> dict:
    """Interactively score a result. Modifies in place."""
    print(f"\n{'─'*60}")
    print(f"Model:  {result['model']}")
    print(f"Prompt: [{result['prompt_type']}] {result['prompt_text'][:80]}...")
    print(f"\nResponse ({result['stats']['word_count']} words, {result['stats']['elapsed_sec']}s):")
    print(f"\n{result['response']}\n")
    print(SCORING_RUBRIC)

    while True:
        raw = input("Score (1-5, or Enter to skip): ").strip()
        if raw == "":
            break
        try:
            score = int(raw)
            if 1 <= score <= 5:
                result["score"] = score
                notes = input("Notes (optional): ").strip()
                if notes:
                    result["score_notes"] = notes
                break
            else:
                print("Enter a number 1-5.")
        except ValueError:
            print("Enter a number 1-5.")

    return result


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def print_report(results: list[dict]):
    """Print aggregate stats table to terminal."""
    # Group by model
    models = sorted(set(r["model"] for r in results))
    prompt_types = sorted(set(r["prompt_type"] for r in results))

    print(f"\n{'='*70}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*70}")
    print(f"{'Model':<30} {'N':>3} {'Avg Time':>9} {'Avg Words':>10} {'Avg Score':>10}")
    print(f"{'─'*70}")

    for model in models:
        model_results = [r for r in results if r["model"] == model and r["status"] == "ok"]
        if not model_results:
            continue

        times = [r["stats"]["elapsed_sec"] for r in model_results]
        words = [r["stats"]["word_count"] for r in model_results]
        scores = [r["score"] for r in model_results if r["score"] is not None]

        avg_score = f"{statistics.mean(scores):.1f}" if scores else "—"
        print(
            f"{model:<30} {len(model_results):>3} "
            f"{statistics.mean(times):>8.1f}s "
            f"{int(statistics.mean(words)):>10} "
            f"{avg_score:>10}"
        )

    # By prompt type
    print(f"\n{'─'*70}")
    print("BY PROMPT TYPE (across all models)")
    print(f"{'─'*70}")
    print(f"{'Type':<15} {'Avg Time':>9} {'Avg Words':>10} {'Avg Score':>10}")
    print(f"{'─'*50}")

    for pt in prompt_types:
        type_results = [r for r in results if r["prompt_type"] == pt and r["status"] == "ok"]
        if not type_results:
            continue
        times = [r["stats"]["elapsed_sec"] for r in type_results]
        words = [r["stats"]["word_count"] for r in type_results]
        scores = [r["score"] for r in type_results if r["score"] is not None]
        avg_score = f"{statistics.mean(scores):.1f}" if scores else "—"
        print(
            f"{pt:<15} {statistics.mean(times):>8.1f}s "
            f"{int(statistics.mean(words)):>10} "
            f"{avg_score:>10}"
        )

    # Head-to-head matrix: score per model per prompt
    print(f"\n{'─'*70}")
    print("HEAD-TO-HEAD: Score per (model × prompt)")
    print(f"{'─'*70}")
    prompt_ids = sorted(set(r["prompt_id"] for r in results))
    col_w = 10

    header = f"{'':30}" + "".join(f"{pid[:col_w-1]:>{col_w}}" for pid in prompt_ids)
    print(header)

    for model in models:
        row = f"{model:<30}"
        for pid in prompt_ids:
            match = next(
                (r for r in results if r["model"] == model and r["prompt_id"] == pid),
                None
            )
            if match and match["score"] is not None:
                cell = f"{match['score']}/5 ({match['stats']['elapsed_sec']:.0f}s)"
            elif match and match["status"] == "ok":
                cell = f"— ({match['stats']['elapsed_sec']:.0f}s)"
            elif match:
                cell = "ERR"
            else:
                cell = "—"
            row += f"{cell:>{col_w}}"
        print(row)

    print(f"\n{'='*70}")

    # Errors
    errors = [r for r in results if r["status"] == "error"]
    if errors:
        print(f"\n⚠ {len(errors)} errors:")
        for e in errors:
            print(f"  {e['model']} / {e['prompt_id']}: {e['response']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SciDK Ollama Model Benchmarker")
    parser.add_argument("--models", nargs="+", help="Models to benchmark (default: auto-detect from ollama list)")
    parser.add_argument("--prompts", type=str, help="Path to JSON prompts file")
    parser.add_argument("--no-score", action="store_true", help="Skip interactive scoring")
    parser.add_argument("--report", type=str, help="Load existing results JSON and show report")
    parser.add_argument("--output", type=str, help="Save results to JSON file", default="bench_results.json")
    parser.add_argument("--system", type=str, help="System prompt to use for all queries")
    args = parser.parse_args()

    # Report-only mode
    if args.report:
        with open(args.report) as f:
            results = json.load(f)
        print_report(results)
        return

    # Detect available models
    if args.models:
        models = args.models
    else:
        try:
            available = ollama.list()
            models = [m["model"] for m in available["models"]]
            print(f"Found {len(models)} models: {', '.join(models)}")
        except Exception as e:
            print(f"Could not list models: {e}")
            print("Specify models with --models qwen2.5:14b llama3.3:70b")
            sys.exit(1)

    if not models:
        print("No models found. Pull some with: ollama pull qwen2.5:14b")
        sys.exit(1)

    # Load prompts
    if args.prompts:
        with open(args.prompts) as f:
            prompts = json.load(f)
        print(f"Loaded {len(prompts)} prompts from {args.prompts}")
    else:
        prompts = DEFAULT_PROMPTS
        print(f"Using {len(prompts)} built-in prompts")

    # Model selection if many available
    if len(models) > 6:
        print("\nMany models available. Which would you like to benchmark?")
        for i, m in enumerate(models):
            print(f"  {i+1}. {m}")
        selection = input("Enter numbers (e.g. 1 3 5) or Enter for all: ").strip()
        if selection:
            indices = [int(x)-1 for x in selection.split()]
            models = [models[i] for i in indices if 0 <= i < len(models)]

    system_prompt = args.system or (
        "You are a concise research data assistant. "
        "Answer factual questions briefly. "
        "For technical questions, be thorough and accurate."
    )

    print(f"\nBenchmarking {len(models)} models × {len(prompts)} prompts = {len(models)*len(prompts)} runs\n")

    # Run
    results = []
    for prompt in prompts:
        print(f"\nPrompt [{prompt['type']}]: {prompt['text'][:70]}...")
        for model in models:
            result = run_prompt(model, prompt, system_prompt)
            results.append(result)

    # Score
    if not args.no_score:
        print(f"\n\n{'='*60}")
        print(f"SCORING — {len(results)} responses to review")
        print("(You can skip any by pressing Enter)")
        print(f"{'='*60}")

        for result in results:
            if result["status"] == "ok":
                score_result(result)

    # Save
    output_path = args.output
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_path}")

    # Report
    print_report(results)


if __name__ == "__main__":
    main()
