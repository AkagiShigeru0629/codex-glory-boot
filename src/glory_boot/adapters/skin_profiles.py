import json
from pathlib import Path

from glory_boot.domain.skin import SkinProfile


_PROFILE_PATH = (
    Path(__file__).resolve().parents[1]
    / "resources"
    / "skin_profiles.json"
)


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} 必须是非空字符串数组")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} 必须是非空字符串数组")
    return tuple(value)


def parse_skin_profiles(payload: object) -> tuple[SkinProfile, ...]:
    """严格解析已登记兼容配置。"""
    if not isinstance(payload, dict):
        raise ValueError("兼容配置顶层必须是对象")
    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list):
        raise ValueError("profiles 必须是数组")

    profiles: list[SkinProfile] = []
    for index, raw in enumerate(raw_profiles):
        if not isinstance(raw, dict):
            raise ValueError(f"profiles[{index}] 必须是对象")
        version = raw.get("package_version")
        if not isinstance(version, str) or not version.strip():
            raise ValueError(f"profiles[{index}].package_version 无效")
        profiles.append(
            SkinProfile(
                package_version=version,
                required_selectors=_strings(
                    raw.get("required_selectors"),
                    f"profiles[{index}].required_selectors",
                ),
                required_tokens=_strings(
                    raw.get("required_tokens"),
                    f"profiles[{index}].required_tokens",
                ),
            )
        )
    return tuple(profiles)


def load_skin_profiles(path: Path | None = None) -> tuple[SkinProfile, ...]:
    """读取内置配置；缺失或损坏时安全回退为空配置。"""
    profile_path = path or _PROFILE_PATH
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
        return parse_skin_profiles(payload)
    except (OSError, ValueError, TypeError):
        return ()
