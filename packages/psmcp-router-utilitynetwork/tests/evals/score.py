"""Score a PS-MCP eval run.

Reads a JSONL results file produced by runner.py and reports the three
sufficiency metrics per prompt:

  * discovery_rate   — fraction of runs that pulled every expected discovery target
  * correctness_rate — fraction of runs whose final answer matched the canonical answer
  * consistency      — agreement of final answers across the N runs (1.0 = identical)

Usage:
    uv run python evals/score.py                 # scores the latest run
    uv run python evals/score.py results/run-XXXX.jsonl
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from .config import load_config
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from config import load_config


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace for forgiving text comparison."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _extract_number(text: str) -> float | None:
    """Pull the first number out of a string, or None."""
    m = re.search(r"-?\d+(?:\.\d+)?", text or "")
    return float(m.group()) if m else None


def _answer_matches(final: str, expected: Any, match: str) -> bool:
    """Compare a final answer against the canonical expected answer."""
    if expected is None or str(expected).startswith("REPLACE_ME"):
        return False  # answer key not filled in yet

    if match == "numeric":
        got = _extract_number(final)
        want = _extract_number(str(expected))
        return got is not None and want is not None and got == want

    norm_final = _normalize(final)
    norm_expected = _normalize(str(expected))
    if match == "contains":
        return norm_expected in norm_final
    return norm_final == norm_expected  # exact


def _discovery_hit(trace: dict[str, Any], targets: list[str]) -> bool:
    """True if the run pulled every expected discovery target (resource or prompt)."""
    if not targets:
        return True
    pulled = set(trace.get("resources_read", [])) | set(trace.get("prompts_fetched", []))
    return all(t in pulled for t in targets)


def _consistency(answers: list[str]) -> float:
    """Fraction of runs sharing the single most common normalized answer."""
    if not answers:
        return 0.0
    counts = Counter(_normalize(a) for a in answers)
    return counts.most_common(1)[0][1] / len(answers)


def _latest_run(results_dir: Path) -> Path:
    runs = sorted(results_dir.glob("run-*.jsonl"))
    if not runs:
        raise FileNotFoundError(f"No run-*.jsonl files in {results_dir}")
    return runs[-1]


def score(path: Path) -> None:
    """Compute and print metrics for a results file."""
    by_prompt: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                by_prompt[rec["prompt_id"]].append(rec)

    print(f"\nScoring {path.name}\n" + "=" * 64)

    overall_correct = 0
    overall_runs = 0

    for pid, records in sorted(by_prompt.items()):
        expects = records[0].get("expects", {})
        match = expects.get("match", "exact")
        expected = expects.get("answer")
        discovery_targets = expects.get("discovery", []) or []

        answers: list[str] = []
        correct = 0
        discovered = 0
        errors = 0

        for rec in records:
            trace = rec["trace"]
            if trace.get("error"):
                errors += 1
            final = trace.get("final_answer", "")
            answers.append(final)
            if _answer_matches(final, expected, match):
                correct += 1
            if _discovery_hit(trace, discovery_targets):
                discovered += 1

        n = len(records)
        overall_correct += correct
        overall_runs += n

        key_ready = expected is not None and not str(expected).startswith("REPLACE_ME")

        print(f"\n[{pid}]  ({n} runs)")
        print(f"  discovery_rate   : {discovered / n:.2f}  (targets: {discovery_targets or 'none'})")
        if key_ready:
            print(f"  correctness_rate : {correct / n:.2f}")
        else:
            print("  correctness_rate : n/a  (answer key not filled — set expects.answer)")
        print(f"  consistency      : {_consistency(answers):.2f}")
        if errors:
            print(f"  errors           : {errors}/{n}")
        # Show the distinct answers so divergence is visible.
        distinct = Counter(_normalize(a) for a in answers)
        if len(distinct) > 1:
            print("  distinct answers :")
            for ans, cnt in distinct.most_common():
                preview = ans[:100] + ("…" if len(ans) > 100 else "")
                print(f"      {cnt}x  {preview!r}")

    print("\n" + "=" * 64)
    if overall_runs:
        print(f"OVERALL correctness: {overall_correct}/{overall_runs} "
              f"({overall_correct / overall_runs:.2f})")
    print()


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if args:
        path = Path(args[0])
    else:
        cfg = load_config()
        path = _latest_run(cfg.results_dir)
    score(path)


if __name__ == "__main__":
    main()
