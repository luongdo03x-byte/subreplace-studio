from app.cli import build_parser, main


def test_review_actions_do_not_require_reentering_source():
    args = build_parser().parse_args(['--overlay-manifest', 'batch.json', '--overlay-render'])
    assert args.overlay_render
    assert not args.source


def test_legacy_run_still_requires_source_and_project(capsys):
    assert main([]) == 2
    assert 'source' in capsys.readouterr().err
