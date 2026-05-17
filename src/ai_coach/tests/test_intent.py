"""意图检测单元测试 —— 验证闲聊 vs 声乐教练 vs 联网搜索意图分类"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai_coach.context.templates import detect_intent, detect_search_intent


class TestDetectIntent:
    """声乐教练意图检测"""

    # ── 明确的声乐问题 ──
    def test_coaching_high_note(self):
        is_coaching, conf = detect_intent("我唱高音的时候嗓子很紧怎么办")
        assert is_coaching is True
        assert conf > 0.6

    def test_coaching_breath(self):
        is_coaching, conf = detect_intent("气息控制怎么做腹式呼吸")
        assert is_coaching is True
        assert conf > 0.6

    def test_coaching_resonance(self):
        is_coaching, conf = detect_intent("头腔共鸣和胸腔共鸣有什么区别")
        assert is_coaching is True

    def test_coaching_mixed_voice(self):
        is_coaching, conf = detect_intent("强混和弱混怎么练习")
        assert is_coaching is True

    def test_coaching_vibrato(self):
        is_coaching, conf = detect_intent("颤音一直唱不好，有什么方法")
        assert is_coaching is True

    def test_coaching_chorus_shake(self):
        is_coaching, conf = detect_intent("为什么我唱副歌的时候声音会发抖")
        assert is_coaching is True

    def test_coaching_pitch_accuracy(self):
        is_coaching, conf = detect_intent("我的音准不行，经常跑调")
        assert is_coaching is True

    def test_coaching_belting(self):
        is_coaching, conf = detect_intent("belting怎么唱才不会伤嗓子")
        assert is_coaching is True

    def test_coaching_SOVT(self):
        is_coaching, conf = detect_intent("SOVT练习有什么用")
        assert is_coaching is True

    def test_coaching_analyze(self):
        is_coaching, conf = detect_intent("帮我分析一下最近唱歌的问题")
        assert is_coaching is True

    def test_coaching_practice(self):
        is_coaching, conf = detect_intent("有什么练声的方法推荐")
        assert is_coaching is True

    # ── 明确的日常闲聊 ──
    def test_casual_hello(self):
        is_coaching, conf = detect_intent("你好呀")
        assert is_coaching is False

    def test_casual_good_morning(self):
        is_coaching, conf = detect_intent("早安～今天天气真好")
        assert is_coaching is False

    def test_casual_how_are_you(self):
        is_coaching, conf = detect_intent("你在干嘛呢")
        assert is_coaching is False

    def test_casual_chat(self):
        is_coaching, conf = detect_intent("陪我聊聊天")
        assert is_coaching is False

    def test_casual_who_are_you(self):
        is_coaching, conf = detect_intent("你叫什么名字")
        assert is_coaching is False

    # ── 模糊边界（无法判断 → 默认闲聊） ──
    def test_ambiguous(self):
        is_coaching, conf = detect_intent("嗯好的谢谢")
        assert is_coaching is False
        assert conf == 0.3  # 无任何关键词 → 默认低置信度


class TestDetectSearchIntent:
    """联网搜索意图检测"""

    def test_search_recommend(self):
        assert detect_search_intent("推荐几首适合练高音的歌") is True

    def test_search_new_song(self):
        assert detect_search_intent("周杰伦最近有新歌吗") is True

    def test_search_intro(self):
        assert detect_search_intent("介绍一下林俊杰的唱法特点") is True

    def test_search_lyrics(self):
        assert detect_search_intent("夜曲的歌词是什么") is True

    def test_search_chart(self):
        assert detect_search_intent("现在华语排行榜前十名") is True

    def test_no_search_coaching(self):
        assert detect_search_intent("高音怎么练才能稳") is False

    def test_no_search_casual(self):
        assert detect_search_intent("嗨，今天怎么样") is False
