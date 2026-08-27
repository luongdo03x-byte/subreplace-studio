from __future__ import annotations

from typing import Any

import numpy as np

from app.core.ocr.protocol import OCRResult
from app.providers.errors import ProviderUnavailableError
from app.providers.ocr.paddle_common import create_chinese_paddle_ocr


class PaddleOCRProvider:
    def __init__(self, engine: Any | None = None) -> None:
        if engine is not None:
            self.engine = engine
            return
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise ProviderUnavailableError("PaddleOCR is not installed; install the 'ai' dependencies") from exc
        self.engine = create_chinese_paddle_ocr(PaddleOCR)

    @staticmethod
    def _parse_prediction(raw: Any) -> tuple[str, float]:
        if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], dict):
            return PaddleOCRProvider._parse_prediction(raw[0])
        if isinstance(raw, dict):
            # PaddleOCR 3.x predict() exposes plural keys (rec_texts/rec_scores);
            # older builds expose singular rec_text/rec_score.
            text = raw.get("rec_text") or raw.get("rec_texts") or raw.get("text") or ""
            score = raw.get("rec_score") or raw.get("rec_scores") or raw.get("score") or 0.0
            if isinstance(text, list):
                if not text:
                    return "", 0.0
                scores = score if isinstance(score, list) else [score] * len(text)
                best = max(range(len(text)), key=lambda i: float(scores[i]))
                return str(text[best]), float(scores[best])
            return str(text), float(score)
        # PaddleOCR 2.x: [[[points], (text, score)], ...]
        if isinstance(raw, list):
            nodes = raw
            while len(nodes) == 1 and isinstance(nodes[0], list):
                nodes = nodes[0]
            best_text, best_score = "", 0.0
            for node in nodes:
                if isinstance(node, (list, tuple)) and len(node) >= 2:
                    candidate = node[-1]
                    if isinstance(candidate, (list, tuple)) and len(candidate) >= 2 and isinstance(candidate[0], str):
                        if float(candidate[1]) > best_score:
                            best_text, best_score = candidate[0], float(candidate[1])
            return best_text, best_score
        return "", 0.0

    def recognize(
        self,
        frame: np.ndarray,
        regions: list[tuple[int, int, int, int]],
        *,
        frame_index: int = 0,
    ) -> list[OCRResult]:
        results: list[OCRResult] = []
        for x, y, w, h in regions:
            crop = frame[max(0, y): y + h, max(0, x): x + w]
            if crop.size == 0:
                continue
            if hasattr(self.engine, "predict"):
                raw = self.engine.predict(crop)
                if not isinstance(raw, list):
                    raw = list(raw)
            else:
                raw = self.engine.ocr(crop, cls=False)
            text, confidence = self._parse_prediction(raw)
            results.append(OCRResult(text, confidence, frame_index))
        return results
