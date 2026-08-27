from __future__ import annotations

import sys
import uuid
from pathlib import Path

import numpy as np

from app.core.eraser.inpainting_provider import InpaintingContext, InpaintingResult

from .external_plugin import (
    read_video,
    require_files,
    require_license,
    run_checked,
    temporary_workspace,
    write_mask_directory,
    write_video,
)


class E2FGVIProvider:
    PROVIDER = "E2FGVI"
    VERSION = "CVPR22"
    LICENSE = "CC-BY-NC-4.0"

    def __init__(
        self,
        *,
        repo_dir: str | Path,
        checkpoint: str | Path,
        python_executable: str | None = None,
        model: str = "e2fgvi_hq",
    ) -> None:
        self.repo_dir = Path(repo_dir).resolve()
        self.checkpoint = Path(checkpoint).resolve()
        self.python_executable = python_executable or sys.executable
        self.model = model
        require_license(
            self.repo_dir,
            provider=self.PROVIDER,
            license_name=self.LICENSE,
            version=self.VERSION,
        )
        require_files(self.repo_dir, ("test.py",))
        if not self.checkpoint.is_file():
            from .external_plugin import PluginValidationError
            raise PluginValidationError(f"missing E2FGVI checkpoint: {self.checkpoint}")
        if self.model not in {"e2fgvi", "e2fgvi_hq"}:
            raise ValueError("model must be e2fgvi or e2fgvi_hq")

    @property
    def name(self) -> str:
        return self.PROVIDER

    def inpaint(
        self,
        frames: list[np.ndarray],
        masks: list[np.ndarray],
        context: InpaintingContext,
    ) -> InpaintingResult:
        if len(frames) != len(masks):
            raise ValueError("frames and masks must have identical length")
        with temporary_workspace("subreplace-e2fgvi-") as temp:
            root = Path(temp)
            unique = f"subreplace_{uuid.uuid4().hex[:10]}"
            video = root / f"{unique}.mp4"
            mask_dir = root / "masks"
            write_video(video, frames, context.fps)
            write_mask_directory(mask_dir, masks)
            h, w = frames[0].shape[:2]
            command = [
                self.python_executable,
                "test.py",
                "--model",
                self.model,
                "--video",
                str(video),
                "--mask",
                str(mask_dir),
                "--ckpt",
                str(self.checkpoint),
                "--savefps",
                str(int(round(context.fps))),
            ]
            if self.model == "e2fgvi_hq":
                command += ["--set_size", "--width", str(w), "--height", str(h)]
            stdout = run_checked(command, cwd=self.repo_dir)
            result_path = self.repo_dir / "results" / f"{unique}_results.mp4"
            output_frames = read_video(result_path, len(frames))
            try:
                result_path.unlink()
            except OSError:
                pass
            return InpaintingResult(output_frames, self.name, stdout)
