"""Use spoken sentences as the time base, with OCR as textual corroboration."""
from difflib import SequenceMatcher
import re
from dataclasses import replace

from app.models.subtitle import SubtitleSegment


def normalized(text):
    return re.sub(r'[^\w]', '', text).lower()


def align_to_speech(segments, speech, *, duration_ms):
    valid = sorted((dict(row) for row in speech if str(row.get('text', '')).strip()
                    and int(row['end_ms']) > int(row['start_ms'])), key=lambda r: int(r['start_ms']))
    if not valid:
        return segments
    result = []
    for index, row in enumerate(valid):
        start = max(0, int(row['start_ms']))
        end = min(duration_ms, int(row['end_ms']),
                  int(valid[index + 1]['start_ms']) if index + 1 < len(valid) else duration_ms)
        if end <= start:
            continue
        text = str(row['text']).strip()
        candidates = [s for s in segments if min(s.end_ms, end) > max(s.start_ms, start)]
        match = max(candidates, key=lambda s: SequenceMatcher(None, normalized(text), normalized(s.source_text)).ratio(), default=None)
        # Partial OCR (e.g. only a title at the end of a sentence) must never
        # erase the rest of the spoken sentence. Unrelated decor is ignored.
        if match and .8 * len(normalized(text)) <= len(normalized(match.source_text)) <= 1.25 * len(normalized(text)):
            repeated = sum(normalized(s.source_text) == normalized(match.source_text) for s in candidates) >= 2
            if SequenceMatcher(None, normalized(text), normalized(match.source_text)).ratio() >= (.5 if repeated else .65):
                text = match.source_text
        if match:
            segment = replace(match, id=f'speech-{index:06d}', start_ms=start, end_ms=end,
                              source_text=text, natural_translation='', subtitle_optimized_translation='')
        else:
            segment = SubtitleSegment(id=f'speech-{index:06d}', start_ms=start, end_ms=end,
                                      source_language='zh', source_text=text, target_language='vi')
        result.append(segment)
    return result
