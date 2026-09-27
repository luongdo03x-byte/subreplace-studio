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


def sanitize_cues(cues):
    valid = [c for c in cues if c.text and c.text.strip()]
    if not valid:
        return ()
    valid.sort(key=lambda c: (c.start_ms, c.end_ms))
    sanitized = []
    previous = 0
    for c in valid:
        start_ms = max(previous, c.start_ms)
        end_ms = max(start_ms + 100, c.end_ms)
        sanitized.append(Cue(c.id, start_ms, end_ms, c.text.strip()))
        previous = end_ms
    return tuple(sanitized)


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
    cues = sanitize_cues(cues)
    validate_cues(cues)
    return tuple(cues)


def _lines(words, metrics, width, joiner=" "):
    text = joiner.join(words).strip()
    if metrics.width(text) <= width:
        return (text,)
    candidates = []
    for i in range(1, len(words)):
        left, right = joiner.join(words[:i]).strip(), joiner.join(words[i:]).strip()
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
        text = unicodedata.normalize('NFC', cue.text)
        joiner = ' '
        words = text.split()
        if re.search(r'[\u0e00-\u0e7f\u3040-\u30ff\u3400-\u9fff]', text):
            from PySide6.QtCore import QTextBoundaryFinder
            finder = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Line, text)
            encoded = text.encode('utf-16-le')
            words, start = [], 0
            while (end := finder.toNextBoundary()) != -1:
                if end > start:
                    words.append(encoded[start*2:end*2].decode('utf-16-le'))
                start = end
            joiner = ''
        groups = []
        while words:
            best = None
            for count in range(1, len(words)+1):
                lines = _lines(words[:count], metrics, width, joiner)
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
