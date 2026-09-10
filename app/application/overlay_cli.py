import json
import os
from pathlib import Path
from app.application.batch import BatchItem
from app.application.overlay_batch import OverlayBatchController
from app.application.view_model import ProjectStartRequest, StudioViewModel


def run_overlay(args):
    controller = OverlayBatchController(StudioViewModel(require_desktop=False), Path(args.overlay_manifest),
                                        on_progress=lambda message: print(message, flush=True))
    if args.overlay_prepare:
        if args.source:
            if not args.project or not args.output:
                raise ValueError('--project and --output are required for a new overlay source')
            key = os.environ.get(args.api_key_env, '') if args.api_key_env else ''
            if args.api_key_env and not key:
                raise ValueError('API key environment variable is empty')
            request = ProjectStartRequest(args.source, args.project, args.name or Path(args.source).stem,
                target_language=args.target, translation_provider=args.translation_provider,
                translation_model=args.translation_model, endpoint=args.endpoint, local_command=args.local_command,
                api_key=key, overlay_prepare_only=True, subtitle_path=args.subtitle,
                dub_enabled=not args.no_dub and not args.subtitle,
                dub_voice_female=args.dub_voice_female, dub_voice_male=args.dub_voice_male,
                dub_default_gender=args.dub_default_gender, dub_rate=args.dub_rate, duck_ratio=args.duck_ratio)
            controller.prepare((BatchItem(request, Path(args.output)),))
        else:
            controller.prepare()
    elif args.overlay_render:
        result = controller.export()
        print(json.dumps({'outputs': [str(r.output_path) for r in result.successful],
                          'merge_error': result.merge_error, 'cancelled': result.cancelled}, ensure_ascii=False))
        return 0 if len(result.successful) == result.total and not result.merge_error else 2
    elif args.overlay_approve is not None or args.overlay_y is not None:
        rows = controller.rows()
        source_id = str(Path(args.project).resolve()) if args.project else (rows[0]['id'] if len(rows) == 1 else '')
        if not source_id:
            raise ValueError('Select a source in the batch using --project')
        if args.overlay_y is not None:
            controller.service.set_y(source_id, args.overlay_y)
        else:
            controller.service.approve(source_id, args.overlay_approve, accept_fallback=args.accept_fallback)
    rows = controller.rows()
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 2 if any(r['payload'].get('blocking') for r in rows) else 0
