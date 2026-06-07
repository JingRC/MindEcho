"""ProfileManager —— 歌手存档 CRUD 管理器

管理 profiles/ 目录下的所有歌手存档。
每个存档一个子文件夹，包含 profile.json + recordings/。

用法:
    mgr = ProfileManager(profiles_root=Path("profiles"))
    profiles = mgr.list_profiles()
    active = mgr.get_active_profile()  # 从 QSettings 恢复上次使用的存档
    mgr.set_active_profile(profile.id)
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import QSettings

from src.profiles.profile_model import SingerProfile, PitchStats, PassaggioData
from src.profiles.profile_model import TimbreFingerprint, UsageStats, PROFILE_VERSION


_GUEST_PROFILE_ID = "__guest__"
_INDEX_FILENAME = "_index.json"


class ProfileManager:
    """存档 CRUD 管理器"""

    def __init__(self, profiles_root: Optional[Path] = None):
        if profiles_root is None:
            # 默认路径：项目根目录下的 profiles/
            try:
                from src.gui.integrated_recording_interface import project_root
                profiles_root = project_root / "profiles"
            except Exception:
                profiles_root = Path(__file__).resolve().parent.parent.parent / "profiles"
        self._root = Path(profiles_root)
        self._root.mkdir(parents=True, exist_ok=True)

        # 访客临时目录
        self._guest_dir = self._root / "_guest"
        self._guest_dir.mkdir(parents=True, exist_ok=True)

        # QSettings 用于持久化"上次使用的存档ID"
        self._settings = QSettings("MindEcho", "IntegratedRecorder")
        self._ensure_index()

    # ── 索引管理 ─────────────────────────────────────────

    @property
    def _index_path(self) -> Path:
        return self._root / _INDEX_FILENAME

    def _ensure_index(self) -> None:
        """确保索引文件存在"""
        if not self._index_path.exists():
            self._save_index({"version": PROFILE_VERSION, "profiles": []})

    def _load_index(self) -> dict:
        """加载索引"""
        try:
            if self._index_path.exists():
                with open(self._index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
        return {"version": PROFILE_VERSION, "profiles": []}

    def _save_index(self, index: dict) -> None:
        """保存索引（原子写入）"""
        index["version"] = PROFILE_VERSION
        index.setdefault("profiles", [])
        tmp = str(self._index_path) + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
            os.replace(tmp, str(self._index_path))
        except OSError:
            pass

    def _update_index_entry(self, profile: SingerProfile) -> None:
        """更新索引中对应条目（或新增）"""
        index = self._load_index()
        profiles = index.get("profiles", [])
        entry = {
            "id": profile.id,
            "name": profile.name,
            "folder": profile.folder_name,
            "voice_type": profile.effective_voice_type or "unspecified",
            "gender": profile.effective_gender or "",
            "created_at": profile.created_at,
            "last_active": profile.usage.last_active,
            "total_minutes": profile.usage.total_minutes,
            "passaggio_confidence": profile.passaggio.confidence,
        }
        # 替换或追加
        found = False
        for i, p in enumerate(profiles):
            if p.get("id") == profile.id:
                profiles[i] = entry
                found = True
                break
        if not found:
            profiles.append(entry)
        index["profiles"] = profiles
        self._save_index(index)

    def _remove_index_entry(self, profile_id: str) -> None:
        """从索引中删除条目"""
        index = self._load_index()
        index["profiles"] = [p for p in index.get("profiles", []) if p.get("id") != profile_id]
        # 清除 last_active 如果删除的是当前活跃存档
        if self._settings.value("last_active_profile_id", "") == profile_id:
            self._settings.setValue("last_active_profile_id", "")
        self._save_index(index)

    # ── 存档 CRUD ────────────────────────────────────────

    def list_profiles(self) -> List[SingerProfile]:
        """列出所有存档（只返回文件夹存在的，自动清理无效索引条目）"""
        index = self._load_index()
        profiles = []
        valid_entries = []
        for entry in index.get("profiles", []):
            folder = self._root / entry.get("folder", "")
            profile_json = folder / "profile.json"
            if profile_json.exists():
                try:
                    profile = self._load_profile_from_file(profile_json)
                    profiles.append(profile)
                    valid_entries.append(entry)
                except (json.JSONDecodeError, KeyError):
                    # 文件损坏，跳过
                    pass
            else:
                # 文件夹不存在或 profile.json 不存在，清理
                pass
        # 写回清理后的索引
        if len(valid_entries) != len(index.get("profiles", [])):
            index["profiles"] = valid_entries
            self._save_index(index)
        # 按最后活跃时间排序（最近用的排在前面）
        profiles.sort(key=lambda p: p.usage.last_active or p.created_at or "", reverse=True)
        return profiles

    def get_profile(self, profile_id: str) -> Optional[SingerProfile]:
        """根据 ID 获取存档"""
        for p in self.list_profiles():
            if p.id == profile_id:
                return p
        return None

    def get_profile_by_name(self, name: str) -> Optional[SingerProfile]:
        """根据名称获取存档"""
        for p in self.list_profiles():
            if p.name == name:
                return p
        return None

    def create_profile(
        self,
        name: str,
        voice_type: str = "",
        gender: str = "",
    ) -> SingerProfile:
        """创建新存档（同名会报错）"""
        name = name.strip()
        if not name:
            raise ValueError("存档名称不能为空")
        # 检查同名
        existing = self.get_profile_by_name(name)
        if existing is not None:
            raise ValueError(f"存档「{name}」已存在，请换一个名称")
        # 检查文件夹名是否合法
        illegal = set(r'<>:"/\|?*')
        if any(c in name for c in illegal):
            raise ValueError(f"存档名称不能包含以下字符：{' '.join(illegal)}")

        profile = SingerProfile.create_new(
            name=name,
            voice_type=voice_type,
            gender=gender,
        )
        self.save_profile(profile)
        return profile

    def save_profile(self, profile: SingerProfile) -> None:
        """保存存档到磁盘"""
        folder = self._profile_folder(profile)
        folder.mkdir(parents=True, exist_ok=True)
        # 确保 recordings 子目录存在
        (folder / "recordings").mkdir(parents=True, exist_ok=True)

        profile.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        profile_json = folder / "profile.json"
        tmp = str(profile_json) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(profile.to_json())
        os.replace(tmp, str(profile_json))

        self._update_index_entry(profile)

    def delete_profile(self, profile_id: str) -> bool:
        """删除存档（包括文件夹及所有录音）"""
        profile = self.get_profile(profile_id)
        if profile is None:
            return False
        folder = self._profile_folder(profile)
        if folder.exists():
            shutil.rmtree(str(folder), ignore_errors=True)
        self._remove_index_entry(profile_id)
        return True

    def _profile_folder(self, profile: SingerProfile) -> Path:
        """获取存档文件夹路径"""
        return self._root / profile.folder_name

    def profile_folder_path(self, profile_id: str) -> Optional[Path]:
        """获取存档文件夹路径（公开方法）"""
        profile = self.get_profile(profile_id)
        if profile is None:
            return None
        return self._profile_folder(profile)

    def _load_profile_from_file(self, path: Path) -> SingerProfile:
        """从 JSON 文件加载存档"""
        with open(path, "r", encoding="utf-8") as f:
            return SingerProfile.from_json(f.read())

    # ── 活跃存档管理 ─────────────────────────────────────

    def get_active_profile(self) -> Optional[SingerProfile]:
        """获取当前活跃存档（从 QSettings 恢复上次使用的归档）"""
        profile_id = self._settings.value("last_active_profile_id", "")
        if profile_id:
            profile = self.get_profile(str(profile_id))
            if profile is not None:
                return profile
            # 存档已被删除，清除记录
            self._settings.setValue("last_active_profile_id", "")
        return None

    def set_active_profile(self, profile: SingerProfile) -> None:
        """设置当前活跃存档"""
        self._settings.setValue("last_active_profile_id", profile.id)
        # 更新最后活跃时间
        profile.usage.last_active = time.strftime("%Y-%m-%dT%H:%M:%S")
        # 不立即保存，等 session 结束时统一更新

    def clear_active_profile(self) -> None:
        """清除活跃存档（切换到访客模式）"""
        self._settings.setValue("last_active_profile_id", "")

    def is_guest_mode(self) -> bool:
        """是否处于访客模式"""
        return not bool(self._settings.value("last_active_profile_id", ""))

    def get_active_profile_id(self) -> str:
        """获取活跃存档 ID（访客模式返回空字符串）"""
        return str(self._settings.value("last_active_profile_id", "") or "")

    # ── 访客模式 ─────────────────────────────────────────

    @property
    def guest_recordings_dir(self) -> Path:
        """访客录音目录"""
        guest_rec = self._guest_dir / "recordings"
        guest_rec.mkdir(parents=True, exist_ok=True)
        return guest_rec

    def cleanup_old_guest_recordings(self, max_age_days: int = 7) -> int:
        """清理超过 max_age_days 天的访客录音，返回清理数量"""
        removed = 0
        cutoff = time.time() - max_age_days * 86400
        guest_rec = self._guest_dir / "recordings"
        if not guest_rec.exists():
            return 0
        for item in guest_rec.iterdir():
            try:
                if item.stat().st_mtime < cutoff:
                    if item.is_file():
                        item.unlink()
                        removed += 1
                    elif item.is_dir():
                        shutil.rmtree(str(item), ignore_errors=True)
                        removed += 1
            except OSError:
                pass
        return removed

    # ── 录音目录 ─────────────────────────────────────────

    def get_recordings_dir(self, profile_id: Optional[str] = None) -> Path:
        """获取录音保存目录"""
        if profile_id:
            profile = self.get_profile(profile_id)
            if profile is not None:
                rec_dir = self._profile_folder(profile) / "recordings"
                rec_dir.mkdir(parents=True, exist_ok=True)
                return rec_dir
        return self.guest_recordings_dir

    # ── Session 结束时的数据更新 ─────────────────────────

    def update_profile_from_session(
        self,
        profile_id: str,
        voiced_frequencies_hz: List[float],
        session_duration_minutes: float,
        technique_counts: Dict[str, int],
        timbre_samples: List[dict],
    ) -> None:
        """录音结束后更新存档统计数据"""
        profile = self.get_profile(profile_id)
        if profile is None:
            return

        # 更新音域统计
        if voiced_frequencies_hz:
            profile.pitch_stats.update_from_frequencies(voiced_frequencies_hz)

        # 更新使用统计
        profile.usage.total_sessions += 1
        profile.usage.total_minutes += round(max(0.0, session_duration_minutes), 1)
        profile.usage.last_active = time.strftime("%Y-%m-%dT%H:%M:%S")

        # 更新技巧分布（EMA 合并）
        if technique_counts:
            total = sum(technique_counts.values())
            if total > 0:
                new_dist = {k: v / total for k, v in technique_counts.items()}
                old_dist = profile.usage.technique_distribution
                # EMA: 新 session 权重 0.25
                merged = {}
                all_keys = set(list(old_dist.keys()) + list(new_dist.keys()))
                for k in all_keys:
                    old_v = old_dist.get(k, 0.0)
                    new_v = new_dist.get(k, 0.0)
                    if old_dist:
                        merged[k] = 0.75 * old_v + 0.25 * new_v
                    else:
                        merged[k] = new_v
                profile.usage.technique_distribution = merged

        # 更新音色指纹
        for ts in (timbre_samples or []):
            profile.timbre.update(
                spectral_tilt=float(ts.get("spectral_tilt", 0.0) or 0.0),
                hm_over_hh=float(ts.get("hm_over_hh", 0.0) or 0.0),
                mid_high_ratio=float(ts.get("mid_high_ratio", 0.0) or 0.0),
                zcr=float(ts.get("zcr", 0.0) or 0.0),
                rms=float(ts.get("rms", 0.0) or 0.0),
            )

        # (Phase 3) 自适应 T4 估计
        self._auto_estimate_passaggio(profile)

        # 保存
        self.save_profile(profile)

    # ── Phase 3: 自适应 T4 估计 ──────────────────────────

    def _auto_estimate_passaggio(self, profile: SingerProfile) -> None:
        """基于音域统计自动估计第二换声点 T4"""
        stats = profile.pitch_stats
        if stats.total_voiced_frames < 3000 or stats.p85_hz <= 0:
            return  # 数据不足

        # T4 ≈ P85 音高（常用音域上界 ≈ 换声区附近）
        # 但需要限制在合理范围内
        from src.profiles.profile_model import _FEMALE_VOICE_TYPES
        vt = profile.effective_voice_type.lower()
        is_f = profile.is_female

        if is_f:
            t4_min, t4_max = 500.0, 800.0
        else:
            t4_min, t4_max = 250.0, 500.0

        estimated = max(t4_min, min(t4_max, stats.p85_hz))
        profile.passaggio.auto_estimated_t4 = estimated

        # 如果还没有手动校准，使用自动估计
        if profile.passaggio.source == "default":
            profile.passaggio.t4_hz = estimated
            profile.passaggio.source = "auto_estimated"
            # 置信度：基于数据量的 sigmoid 式增长
            frames_k = min(stats.total_voiced_frames / 50000.0, 1.0)
            sessions_k = min(stats.session_count / 20.0, 1.0)
            profile.passaggio.confidence = 0.30 * frames_k + 0.20 * sessions_k
        elif profile.passaggio.source == "auto_estimated":
            # EMA 更新
            profile.passaggio.t4_hz = (
                0.15 * estimated + 0.85 * profile.passaggio.t4_hz
            )
