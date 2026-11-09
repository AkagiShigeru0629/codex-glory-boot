import re
from dataclasses import dataclass
from pathlib import PureWindowsPath


_PACKAGE_VERSION = re.compile(
    r"^OpenAI\.Codex_(?P<version>\d+(?:\.\d+){3})_[^_]+__",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SkinProfile:
    package_version: str
    required_selectors: tuple[str, ...]
    required_tokens: tuple[str, ...]


def package_version_from_path(process_path: str) -> str | None:
    """从 Store 应用目录名提取四段式包版本。"""
    for part in PureWindowsPath(process_path).parts:
        match = _PACKAGE_VERSION.match(part)
        if match is not None:
            return match.group("version")
    return None


def select_skin_profile(
    profiles: tuple[SkinProfile, ...],
    version: str | None,
) -> SkinProfile | None:
    """只允许已登记且完全匹配当前包版本的样式配置。"""
    if version is None:
        return None
    for profile in profiles:
        if profile.package_version == version:
            return profile
    return None
