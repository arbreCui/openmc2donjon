"""Generic DONJON deck runner for ``run-sph-loop`` solver commands."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess


DEFAULT_CASE_DIR = "openmc2donjon/case_runs/donjon_sph_loop_adapter"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    solve = subparsers.add_parser("solve", help="run a DONJON solve deck")
    _add_common_args(solve)
    solve.add_argument("--result", type=Path, required=True)

    apply = subparsers.add_parser("apply", help="run a DONJON MAC/DSPH apply deck")
    _add_common_args(apply)
    apply.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "solve":
        return _solve(args)
    if args.command == "apply":
        return _apply(args)
    raise AssertionError(args.command)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--donjon-root", type=Path, required=True)
    parser.add_argument("--deck-template", type=Path, required=True)
    parser.add_argument("--macrolib", type=Path, required=True)
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--case-id", default=None)
    parser.add_argument("--case-dir", default=DEFAULT_CASE_DIR)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--runner", type=Path, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="render the deck and stage inputs without calling DONJON",
    )


def _solve(args: argparse.Namespace) -> int:
    mode = "solve"
    context = _prepare_context(args, mode=mode)
    _render_deck(args.deck_template, context["deck_path"], context)
    _run_donjon(args, context)
    if not args.dry_run:
        _require_file(context["listing"])
        args.result.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(context["listing"], args.result)
    print(
        f"DONJON deck runner solve iteration={args.iteration} "
        f"deck={context['deck_path']} result={args.result}"
    )
    return 0


def _apply(args: argparse.Namespace) -> int:
    mode = "apply"
    context = _prepare_context(args, mode=mode)
    corrected = context["corrected_macrolib"]
    if corrected.exists():
        corrected.unlink()
    _render_deck(args.deck_template, context["deck_path"], context)
    _run_donjon(args, context)
    if not args.dry_run:
        _require_file(corrected)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(corrected, args.output)
    print(
        f"DONJON deck runner apply iteration={args.iteration} "
        f"deck={context['deck_path']} output={args.output}"
    )
    return 0


def _prepare_context(args: argparse.Namespace, *, mode: str) -> dict[str, object]:
    _require_file(args.macrolib)
    _require_file(args.deck_template)
    case_id = _case_id(args, mode)
    work_dir = args.work_dir or Path("/tmp") / "openmc2donjon_donjon_deck_runner" / case_id
    work_dir.mkdir(parents=True, exist_ok=True)

    staged_macrolib = work_dir / f"{case_id}.macrolib.txt"
    corrected = work_dir / f"{case_id}.corrected.macrolib.txt"
    shutil.copyfile(args.macrolib, staged_macrolib)

    deck_rel = f"{args.case_dir.rstrip('/')}/{case_id}.x2m"
    deck_path = args.donjon_root / "data" / deck_rel
    deck_path.parent.mkdir(parents=True, exist_ok=True)
    listing = args.donjon_root / "Darwin_arm64" / f"{Path(deck_rel).stem}.result"

    context: dict[str, object] = {
        "mode": mode,
        "iteration": args.iteration,
        "iteration1": args.iteration + 1,
        "case_id": case_id,
        "case_dir": args.case_dir.rstrip("/"),
        "donjon_root": args.donjon_root,
        "deck_rel": deck_rel,
        "deck_path": deck_path,
        "work_dir": work_dir,
        "macrolib": staged_macrolib,
        "input_macrolib": staged_macrolib,
        "corrected_macrolib": corrected,
        "listing": listing,
    }
    if hasattr(args, "result"):
        context["result"] = args.result
        context["requested_result"] = args.result
    if hasattr(args, "output"):
        context["output"] = args.output
        context["requested_output"] = args.output
    return context


def _case_id(args: argparse.Namespace, mode: str) -> str:
    template = args.case_id or f"openmc2donjon_sph_loop_{mode}_iter{{iteration}}"
    return template.format(
        mode=mode,
        iteration=args.iteration,
        iteration1=args.iteration + 1,
    )


def _render_deck(template: Path, deck_path: Path, context: dict[str, object]) -> None:
    try:
        text = template.read_text(encoding="utf-8").format(**context)
    except KeyError as exc:
        raise ValueError(f"unknown DONJON deck template field {exc.args[0]!r}") from exc
    deck_path.write_text(text, encoding="utf-8")


def _run_donjon(args: argparse.Namespace, context: dict[str, object]) -> None:
    if args.dry_run:
        print(f"DONJON deck runner dry-run: {context['deck_path']}")
        return
    runner = args.runner or args.donjon_root / "rdonjon"
    if not runner.exists():
        raise FileNotFoundError(f"missing DONJON runner: {runner}")
    completed = subprocess.run(
        [str(runner), "-q", str(context["deck_rel"])],
        cwd=args.donjon_root,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"DONJON failed for {context['deck_rel']} with exit code "
            f"{completed.returncode}"
        )


def _require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


if __name__ == "__main__":
    raise SystemExit(main())
