from __future__ import annotations

import sys
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


class ProPainterProvider:
    PROVIDER = "ProPainter"
    VERSION = "v0.1.0"
    LICENSE = "NTU-S-Lab-1.0"
    REQUIRED_FILES = (
        "inference_propainter.py",
        "weights/ProPainter.pth",
        "weights/recurrent_flow_completion.pth",
        "weights/raft-things.pth",
    )

    def __init__(self, *, repo_dir: str | Path, python_executable: str | None = None) -> None:
        self.repo_dir = Path(repo_dir).resolve()
        self.python_executable = python_executable or sys.executable
        require_license(
            self.repo_dir,
            provider=self.PROVIDER,
            license_name=self.LICENSE,
            version=self.VERSION,
        )
        # Requiring all weights prevents upstream's automatic first-run download.
        require_files(self.repo_dir, self.REQUIRED_FILES)

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
        with temporary_workspace("subreplace-propainter-") as temp:
            root = Path(temp)
            video = root / "input.mp4"
            mask_dir = root / "masks"
            output = root / "output"
            write_video(video, frames, context.fps)
            write_mask_directory(mask_dir, masks)
            h, w = frames[0].shape[:2]
            command = [
                self.python_executable,
                "inference_propainter.py",
                "--video",
                str(video),
                "--mask",
                str(mask_dir),
                "--output",
                str(output),
                "--height",
                str(h),
                "--width",
                str(w),
                "--save_fps",
                str(int(round(context.fps))),
            ]
            if context.fp16:
                command.append("--fp16")
            stdout = run_checked(command, cwd=self.repo_dir)
            result_path = output / video.stem / "inpaint_out.mp4"
            output_frames = read_video(result_path, len(frames))
            return InpaintingResult(output_frames, self.name, stdout)
