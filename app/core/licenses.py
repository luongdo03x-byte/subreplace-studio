from __future__ import annotations

from dataclasses import dataclass


class LicensePolicyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    name: str
    version: str
    license_name: str
    commercial_use_allowed: bool | None
    weights_bundled: bool
    user_install_required: bool = False

    def assert_distributable(self, *, commercial_build: bool = True) -> None:
        if commercial_build and self.weights_bundled and self.commercial_use_allowed is not True:
            raise LicensePolicyError(
                f"{self.name} cannot be distributed with bundled weights in a commercial build "
                f"under {self.license_name}"
            )


def default_provider_registry() -> tuple[ProviderMetadata, ...]:
    return (
        ProviderMetadata("PaddleOCR", "PP-OCR", "Apache-2.0", True, True),
        ProviderMetadata("faster-whisper", "runtime-selected", "MIT", True, True),
        ProviderMetadata("OpenCV", "runtime", "Apache-2.0", True, False),
        ProviderMetadata("ProPainter", "v0.1.0", "NTU-S-Lab-1.0", False, False, True),
        ProviderMetadata("E2FGVI", "CVPR22", "CC-BY-NC-4.0", False, False, True),
        ProviderMetadata("STTN", "blocked", "MIT-unverified", None, False, True),
    )
