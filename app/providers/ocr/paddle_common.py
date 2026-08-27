from __future__ import annotations

from typing import Any


def _cpu_runtime_kwargs() -> dict[str, Any]:
    """Disable Paddle oneDNN/MKLDNN on CPU where Paddle 3.3 PIR inference can crash."""
    try:
        import paddle

        device = str(paddle.device.get_device()).lower()
    except Exception:
        # PaddleOCR itself will surface a useful import/runtime error later. Do not
        # force a backend choice when the runtime cannot be inspected.
        return {}
    return {"enable_mkldnn": False} if device.startswith("cpu") else {}


def create_chinese_paddle_ocr(PaddleOCR):
    runtime = _cpu_runtime_kwargs()
    modern = {
        "lang": "ch",
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        **runtime,
    }
    try:
        return PaddleOCR(**modern)
    except TypeError:
        legacy = {"lang": "ch", "use_angle_cls": False, **runtime}
        try:
            return PaddleOCR(**legacy)
        except TypeError:
            # Very old PaddleOCR releases may not expose enable_mkldnn. Those
            # versions also predate the Paddle 3.3 PIR regression.
            legacy.pop("enable_mkldnn", None)
            return PaddleOCR(**legacy)
