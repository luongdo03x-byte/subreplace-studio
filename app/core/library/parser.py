from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


class EpisodeParseError(ValueError):
    pass


_LABELED = re.compile(
    r"(?:^|[^a-z0-9])(?:ep(?:isode)?|tap|tập|part)[\s_.-]*(\d+)(?:[^0-9]|$)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d+")


def parse_episode_number(path: str | Path) -> int:
    stem = Path(path).stem
    labeled = _LABELED.search(stem)
    if labeled:
        number = int(labeled.group(1))
    else:
        numbers = _NUMBER.findall(stem)
        unique_numbers = {int(value) for value in numbers}
        if len(unique_numbers) != 1:
            raise EpisodeParseError(f"Cannot determine one episode number from filename: {Path(path).name}")
        number = unique_numbers.pop()
    if number <= 0:
        raise EpisodeParseError(f"Episode number must be positive: {Path(path).name}")
    return number


@dataclass(frozen=True, slots=True)
class ImportAnalysis:
    episodes: tuple[tuple[int, Path], ...]
    missing: tuple[int, ...]
    duplicates: dict[int, tuple[Path, ...]]
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.duplicates and not self.errors


def analyze_episode_files(paths: Iterable[str | Path]) -> ImportAnalysis:
    parsed: dict[int, list[Path]] = {}
    errors: list[str] = []
    for value in paths:
        path = Path(value).expanduser().resolve()
        try:
            parsed.setdefault(parse_episode_number(path), []).append(path)
        except EpisodeParseError as exc:
            errors.append(str(exc))
    duplicates = {number: tuple(items) for number, items in parsed.items() if len(items) > 1}
    episodes = tuple((number, items[0]) for number, items in sorted(parsed.items()) if len(items) == 1)
    numbers = sorted(parsed)
    missing = tuple(number for number in range(numbers[0], numbers[-1] + 1) if number not in parsed) if numbers else ()
    return ImportAnalysis(episodes, missing, duplicates, tuple(errors))
