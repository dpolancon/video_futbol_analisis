#!/usr/bin/env python3
"""
scripts/together_cli.py
-----------------------
Command-line interface to query Together.ai models from the
video_futbol_analisis project.

Quick start
-----------
    python scripts/together_cli.py "Explain a 4-3-3 high press."

With options
-----------
    python scripts/together_cli.py "Describe a back-line offside trap." \
        --model Qwen/Qwen2.5-7B-Instruct \
        --system "You are a UEFA Pro Licence football coach." \
        --temperature 0.5

List available models
---------------------
    python scripts/together_cli.py --list-models
"""

import argparse
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.llm_client import TogetherClient, DEFAULT_MODEL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query Together.ai LLMs from the video_futbol_analisis project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        type=str,
        default=None,
        help="User prompt / question to send to the model.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Together.ai model slug (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--system",
        type=str,
        default="You are an expert football tactics and video analysis assistant.",
        help="System prompt to set the assistant's role.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature (default: 0.2).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=4000,
        help="Maximum tokens in the completion (default: 4000).",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List all models available on your Together.ai account and exit.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Initialise client (reads .env automatically)
    try:
        client = TogetherClient(default_model=args.model)
    except EnvironmentError as exc:
        print(f"\n  Error: {exc}\n", file=sys.stderr)
        sys.exit(1)

    # --list-models mode
    if args.list_models:
        print("\nAvailable models on Together.ai\n" + "=" * 72)
        try:
            models = client.list_models()
            # Group by type
            by_type: dict[str, list] = {}
            for m in models:
                t = m.get("type", "other")
                by_type.setdefault(t, []).append(m)

            for mtype, group in sorted(by_type.items()):
                print(f"\n  [{mtype.upper()}]")
                for m in sorted(group, key=lambda x: x.get("id", "")):
                    mid = m.get("id", "?")
                    name = m.get("display_name", "")
                    running = "🟢 running" if m.get("running") else "⚪ serverless"
                    ctx = m.get("context_length")
                    ctx_str = f"  ctx={ctx:,}" if ctx else ""
                    print(f"    {mid:<55} {running}{ctx_str}")

            print(f"\n  Total: {len(models)} models\n")
        except Exception as exc:  # noqa: BLE001
            print(f"  Error fetching models: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    # Require a prompt for normal operation
    if not args.prompt:
        parser.print_help()
        sys.exit(1)

    print(f"\nQuerying {args.model} ...\n" + "=" * 60)

    try:
        response = client.chat(
            user_prompt=args.prompt,
            system_prompt=args.system,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        print(response)
        print("=" * 60)
    except Exception as exc:  # noqa: BLE001
        print(f"\n  API error: {exc}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
