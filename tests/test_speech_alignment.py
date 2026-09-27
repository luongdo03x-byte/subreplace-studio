from app.core.translation.alignment import align_to_speech
from app.models.subtitle import SubtitleSegment


def test_fragments_become_one_complete_spoken_sentence():
    fragments = [SubtitleSegment(id=str(i), start_ms=start, end_ms=end,
        source_language='zh', source_text='藐视君上的罪行', target_language='vi')
        for i, (start, end) in enumerate([(6360, 6720), (7720, 7880)])]
    speech = [{'start_ms':6120, 'end_ms':7920, 'text':'秒释军上的罪行', 'confidence':.8}]
    result = align_to_speech(fragments, speech, duration_ms=10000)
    assert len(result) == 1
    assert (result[0].start_ms, result[0].end_ms) == (6120, 7920)
    assert result[0].source_text == '藐视君上的罪行'


def test_partial_ocr_does_not_replace_whole_spoken_sentence():
    fragment = SubtitleSegment(id='a', start_ms=12640, end_ms=12880,
        source_language='zh', source_text='丞相之位', target_language='vi')
    result = align_to_speech([fragment], [dict(start_ms=10720, end_ms=12800,
        text='老臣愿意卸去丞相之位', confidence=.8)], duration_ms=14000)
    assert result[0].source_text == '老臣愿意卸去丞相之位'
    assert result[0].start_ms == 10720


def test_audio_only_lines_are_kept_and_overlaps_clipped():
    result = align_to_speech([], [dict(start_ms=0, end_ms=1500, text='等等陛下'),
        dict(start_ms=1400, end_ms=3000, text='若今夜宴完')], duration_ms=2800)
    assert [(s.start_ms, s.end_ms) for s in result] == [(0,1400),(1400,2800)]
    assert result[0].source_text == '等等陛下'


def test_no_speech_keeps_ocr_fallback():
    cue = SubtitleSegment(id='a', start_ms=0, end_ms=1000, source_language='zh', source_text='你好', target_language='vi')
    assert align_to_speech([cue], [], duration_ms=2000) == [cue]


def test_ocr_spanning_two_sentences_does_not_duplicate_dialogue():
    cue = SubtitleSegment(id='a', start_ms=0, end_ms=4000, source_language='zh',
                          source_text='你先回去我等着你', target_language='vi')
    result = align_to_speech([cue], [dict(start_ms=0,end_ms=2000,text='你先回去'),
        dict(start_ms=2000,end_ms=4000,text='我等着你')], duration_ms=4000)
    assert [s.source_text for s in result] == ['你先回去', '我等着你']
