"""Persistent placement default for newly prepared sources."""
import json
import math
from pathlib import Path
from app.core.settings import app_data_root


class PlacementPreferences:
    def __init__(self, path=None):
        self.path = Path(path) if path else app_data_root() / 'subtitle-placement.json'

    def load(self):
        if not self.path.exists():
            return None
        ratio = json.loads(self.path.read_text(encoding='utf-8')).get('y_ratio')
        if ratio is not None and (isinstance(ratio, bool) or not isinstance(ratio, (int, float))
                                  or not math.isfinite(ratio) or not 0 <= ratio <= 4):
            raise ValueError('Vị trí Y đã lưu không hợp lệ.')
        return ratio

    def save(self, y, height):
        if height <= 0 or not 0 <= y <= 4 * height:
            raise ValueError('Vị trí Y phải nằm trong 0–4 lần chiều cao video.')
        self._write(y / height)

    def clear(self):
        self._write(None)

    def _write(self, ratio):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps({'y_ratio': ratio}), encoding='utf-8')
        temp.replace(self.path)
