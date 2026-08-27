from __future__ import annotations

import argparse
import os
import sys

from app.application.view_model import PreflightFailedError, ProjectStartRequest, StudioViewModel


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="subreplace-batch", description="Run SubReplace Studio pipeline without the desktop UI")
    parser.add_argument("--source", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--target", choices=("vi", "en"), default="vi")
    parser.add_argument("--translation-provider", choices=("openai", "gemini", "custom", "local"), default="openai")
    parser.add_argument("--translation-model", default="")
    parser.add_argument("--endpoint", default="")
    parser.add_argument("--local-command", default="")
    parser.add_argument("--api-key-env", default="")
    parser.add_argument("--temporal-provider", choices=("classical", "propainter", "e2fgvi"), default="classical")
    parser.add_argument("--temporal-repo", default="")
    parser.add_argument("--temporal-checkpoint", default="")
    parser.add_argument("--no-fp16", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    api_key = ""
    if args.api_key_env:
        api_key = os.environ.get(args.api_key_env, "")
        if not api_key:
            print(f"Environment variable {args.api_key_env} is not set", file=sys.stderr)
            return 2
    request = ProjectStartRequest(
        source_path=args.source,
        project_root=args.project,
        project_name=args.name,
        target_language=args.target,
        translation_provider=args.translation_provider,
        translation_model=args.translation_model,
        endpoint=args.endpoint,
        api_key=api_key,
        local_command=args.local_command,
        temporal_provider=args.temporal_provider,
        temporal_repo_dir=args.temporal_repo,
        temporal_checkpoint=args.temporal_checkpoint,
        fp16=not args.no_fp16,
    )
    vm = StudioViewModel(require_desktop=False)

    def progress(event) -> None:
        print(f"[{event.status.value:9}] {event.stage} {event.progress * 100:6.2f}% {event.message}".rstrip(), flush=True)

    try:
        handle, _report = vm.start(request, on_progress=progress)
    except PreflightFailedError as exc:
        for check in exc.report.checks:
            print(f"{check.status.value.upper():8} {check.name}: {check.message}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    handle.worker.join()
    record = handle.job_store.load(handle.job_id)
    if record.status.value != "completed":
        print(f"Job {record.id} ended with status {record.status.value}", file=sys.stderr)
        return 2
    print(f"Completed: {vm.session.current_project.root / 'exports' / f'final_{args.target}.mp4'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
