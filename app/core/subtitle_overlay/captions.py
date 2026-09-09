"""Display segmentation independent of narration; no words are discarded."""
import re
import unicodedata
from .models import Cue, DisplayCue


def _time(value):
    parts = re.fullmatch(r'(\d+):(\d{2}):(\d{2})[,.](\d{2,3})', value.strip())
    if not parts:
        raise ValueError(f'Invalid subtitle time: {value}')
    h, m, s, fraction = parts.groups()
    if int(m) >= 60 or int(s) >= 60:
        raise ValueError('Invalid subtitle time')
    return (int(h)*3600 + int(m)*60 + int(s))*1000 + int(fraction.ljust(3, '0'))


def validate_cues(cues):
    previous = 0
    for cue in cues:
        if cue.start_ms < previous or cue.end_ms <= cue.start_ms or not cue.text.strip():
            raise ValueError('Phụ đề rỗng, sai thời gian hoặc chồng thời gian; hãy sửa trước khi xuất.')
        previous = cue.end_ms
    if not cues:
        raise ValueError('Không có phụ đề để hiển thị')


def read_cues(path):
    content = path.read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    cues = []
    if path.suffix.lower() == '.ass':
        fields = None
        in_events = False
        for line in content.splitlines():
            if line.startswith('['):
                in_events = line.strip().lower() == '[events]'
            if not in_events:
                continue
            if line.lower().startswith('format:'):
                fields = [v.strip().lower() for v in line.split(':', 1)[1].split(',')]
            if line.lower().startswith('dialogue:'):
                if not fields or fields[-1] != 'text':
                    raise ValueError('ASS requires an Events Format with Text last')
                row = dict(zip(fields, line.split(':', 1)[1].split(',', len(fields)-1), strict=True))
                text = re.sub(r'\{[^}]*\}', '', row['text']).replace(r'\N', ' ').replace(r'\n', ' ').replace(r'\h', ' ')
                cues.append(Cue(str(len(cues)+1), _time(row['start']), _time(row['end']), text.strip()))
    else:
        for block in re.split(r'\n\s*\n', content.strip()):
            lines = block.splitlines()
            if lines and lines[0].strip().isdigit():
                lines.pop(0)
            if len(lines) < 2 or '-->' not in lines[0]:
                raise ValueError('Invalid SRT cue')
            start, end = lines[0].split('-->')
            text = re.sub(r'<[^>]*>', '', ' '.join(lines[1:]))
            cues.append(Cue(str(len(cues)+1), _time(start), _time(end), text))
    validate_cues(cues)
    return tuple(cues)


def _lines(words, metrics, width):
    text = ' '.join(words)
    if metrics.width(text) <= width:
        return (text,)
    candidates = []
    for i in range(1, len(words)):
        left, right = ' '.join(words[:i]), ' '.join(words[i:])
        a, b = metrics.width(left), metrics.width(right)
        if max(a, b) <= width:
            candidates.append((max(a, b), abs(a-b), left, right))
    if not candidates:
        return None
    _, _, left, right = min(candidates)
    return (left, right)


def segment_cues(cues, metrics, width):
    validate_cues(cues)
    if width <= 0:
        raise ValueError('No horizontal space for subtitles')
    result, warnings = [], []
    for cue in cues:
        words = unicodedata.normalize('NFC', cue.text).split()
        groups = []
        while words:
            best = None
            for count in range(1, len(words)+1):
                lines = _lines(words[:count], metrics, width)
                if lines is None:
                    break
                best = (count, lines)
            if best is None:
                raise ValueError(f'Câu {cue.id}: từ quá rộng, hãy chỉnh font hoặc nội dung.')
            count, lines = best
            groups.append(lines)
            words = words[count:]
        weights = [len(' '.join(lines)) for lines in groups]
        total = sum(weights)
        used = 0
        start = cue.start_ms
        for lines, weight in zip(groups, weights):
            used += weight
            end = cue.start_ms + round((cue.end_ms-cue.start_ms)*used/total)
            if end <= start:
                raise ValueError('Không đủ thời gian cho phân đoạn hiển thị')
            if end-start < 800 or weight / ((end-start)/1000) > 20:
                warnings.append(f'Câu {cue.id} tại {start} ms: đọc quá nhanh hoặc quá ngắn.')
            result.append(DisplayCue(cue.id, start, end, lines))
            start = end
    return tuple(result), tuple(warnings)
