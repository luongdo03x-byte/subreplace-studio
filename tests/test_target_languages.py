from PySide6.QtWidgets import QApplication
from app.ui.project_setup import ProjectSetupView
from app.core.credentials import CredentialStore
from app.core.languages import TARGET_LANGUAGES
from app.core.translation.service import TranslationService


def test_language_selection_updates_output_hint_and_voice(monkeypatch):
    monkeypatch.setattr(CredentialStore, 'load', lambda *args: '')
    app = QApplication.instance() or QApplication([])
    view = ProjectSetupView()
    assert view.target_language.count() == len(TARGET_LANGUAGES)
    view.target_language.setCurrentIndex(view.target_language.findData('fr'))
    assert '_fr.mp4' in view.language_hint.text()
    assert view.dub_enabled.isChecked()
    assert view.dub_enabled.isEnabled()
    assert view.dub_voice_female.currentData().startswith('fr-FR-')
    assert view.dub_voice_male.currentData().startswith('fr-FR-')
    view.target_language.setCurrentIndex(view.target_language.findData('vi'))
    assert view.dub_enabled.isEnabled()
    view.close()


def test_translation_service_passes_each_supported_target_to_provider():
    class Provider:
        def translate_batch(self, requests, language, glossary):
            self.language = language
            return []
    provider = Provider()
    for code, _ in TARGET_LANGUAGES:
        assert TranslationService(provider).translate([], target_language=code, glossary={}) == []
        assert provider.language == code


def test_asian_fonts_and_line_breaks_preserve_text():
    from app.core.subtitle_overlay.typography import default_style, style_for_language, FontMetrics
    from app.core.subtitle_overlay.captions import segment_cues
    from app.core.subtitle_overlay.models import Cue
    app = QApplication.instance() or QApplication([])
    samples = {
        'ja': '今日は皆さんと一緒に新しい物語についてお話ししたいと思います。',
        'ko': '오늘 여러분과 함께 새로운 이야기를 나누고 싶습니다.',
        'th': 'วันนี้เราจะพูดคุยเกี่ยวกับเรื่องราวใหม่ด้วยกัน',
        'fil': 'Magandang araw sa inyong lahat.',
        'id': 'Selamat pagi semuanya.',
    }
    for code, text in samples.items():
        metrics = FontMetrics(style_for_language(default_style(), code))
        assert metrics.has_glyphs(text), code
        width = 480 if code in {'fil', 'id'} else 260
        cues, _ = segment_cues([Cue('1', 0, 10000, text)], metrics, width)
        rendered = ''.join(line for cue in cues for line in cue.lines)
        assert ''.join(rendered.split()) == ''.join(text.split()), code
        assert all(metrics.width(line) <= width for cue in cues for line in cue.lines), code


def test_all_targets_have_matching_dub_defaults_including_saved_vietnamese_defaults():
    from app.application.view_model import StudioViewModel, ProjectStartRequest
    from app.core.dubbing.languages import VOICES
    vm = StudioViewModel(require_desktop=False)
    assert set(VOICES) == {code for code, _ in TARGET_LANGUAGES}
    for code, _ in TARGET_LANGUAGES:
        request = ProjectStartRequest(source_path='/tmp/source.mp4', project_root='/tmp/project', project_name='test', target_language=code)
        config = vm._dub_config(request)
        assert (config['voice_female'], config['voice_male']) == VOICES[code]


def test_character_budget_is_sent_without_word_budget():
    from app.core.translation.protocol import TranslationRequest
    from app.providers.translation.json_contract import request_payload
    payload = request_payload([TranslationRequest('1', '你好', '', '', max_chars=8)], 'ja', {})
    assert payload['segments'][0]['max_chars'] == 8
    assert payload['segments'][0]['max_words'] is None


def test_create_reopen_and_translate_real_segment_for_every_language(tmp_path):
    from app.core.project.service import ProjectService
    from app.models.subtitle import SubtitleSegment
    from app.core.translation.protocol import TranslationResult
    from app.cli import build_parser
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'test source')
    class Provider:
        def translate_batch(self, requests, language, glossary):
            return [TranslationResult(r.segment_id, 'Hello', 'Hello') for r in requests]
    service = ProjectService()
    for code, _ in TARGET_LANGUAGES:
        project = service.create(tmp_path / code, source_path=source, name='test', target_language=code)
        assert service.open(project.root).target_language == code
        segment = SubtitleSegment('1', 0, 1000, 'zh', '你好', code)
        translated = TranslationService(Provider()).translate([segment], target_language=code, glossary={})
        assert translated[0].target_language == code
        assert translated[0].translated_text == 'Hello'
        assert build_parser().parse_args(['--target', code]).target == code
