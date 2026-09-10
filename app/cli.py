from __future__ import annotations

import argparse
import os
import sys

from app.application.view_model import PreflightFailedError, ProjectStartRequest, StudioViewModel
from app.providers.tts.edge import VOICE_FEMALE, VOICE_MALE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="subreplace-batch", description="Run SubReplace Studio pipeline without the desktop UI")
    parser.add_argument("--source", default="")
    parser.add_argument("--project", default="")
    parser.add_argument('--overlay-manifest', default='')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--overlay-prepare', action='store_true')
    actions.add_argument('--overlay-approve', type=int)
    actions.add_argument('--overlay-render', action='store_true')
    actions.add_argument('--overlay-y', type=int)
    parser.add_argument('--accept-fallback', action='store_true')
    parser.add_argument('--subtitle', default='')
    parser.add_argument('--output', default='')
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
    parser.add_argument("--erase-subtitles", action="store_true")
    parser.add_argument("--no-dub", action="store_true")
    parser.add_argument("--dub-voice-female", default=VOICE_FEMALE)
    parser.add_argument("--dub-voice-male", default=VOICE_MALE)
    parser.add_argument("--dub-default-gender", choices=("female", "male"), default="female")
    parser.add_argument("--dub-rate", default="+0%")
    parser.add_argument("--duck-ratio", type=int, default=12)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.overlay_manifest:
        from app.application.overlay_cli import run_overlay
        try:
            return run_overlay(args)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if not args.source or not args.project:
        print('--source and --project are required', file=sys.stderr)
        return 2
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
        erase_subtitles=args.erase_subtitles,
        dub_enabled=not args.no_dub,
        dub_voice_female=args.dub_voice_female,
        dub_voice_male=args.dub_voice_male,
        dub_default_gender=args.dub_default_gender,
        dub_rate=args.dub_rate,
        duck_ratio=args.duck_ratio,
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
