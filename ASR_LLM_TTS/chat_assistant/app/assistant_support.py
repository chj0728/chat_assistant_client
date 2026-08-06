import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum

from pypinyin import Style, pinyin

MAX_QUEUE_SIZE = 10

SPECIAL_WORD_MAP = {
    "": [
        # 常见 ASR 错误示例，可以根据实际情况调整和扩展
    ],
}


@dataclass
class ResponseData:
    asr_text: str = ""
    llm_text: str = ""

    def clear(self) -> None:
        self.asr_text = ""
        self.llm_text = ""


class AssistantState(Enum):
    IDLE = 0
    ACTIVE = 1
    LISTENING = 2
    THINKING = 3
    SPEAKING = 4


class ComponentState(Enum):
    IDLE = 0
    ACTIVE = 1


class AssistantTextProcessor:
    def __init__(
        self,
        wake_word: str,
        fuzzy_similarity_threshold: float,
        word_map: dict[str, list[str]] | None = None,
    ) -> None:
        self.wake_word = wake_word
        self.fuzzy_similarity_threshold = fuzzy_similarity_threshold
        self.word_map = word_map or SPECIAL_WORD_MAP
        self.wake_word_pinyin = self.extract_chinese_and_convert_to_pinyin(wake_word)

    def extract_chinese_and_convert_to_pinyin(self, input_string: str) -> str:
        """提取输入字符串中的中文字符并转换为拼音"""
        chinese_characters = re.findall(r"[\u4e00-\u9fa5]", input_string)
        chinese_text = "".join(chinese_characters)
        pinyin_result = pinyin(chinese_text, style=Style.NORMAL)
        return " ".join(item[0] for item in pinyin_result)

    def is_kws_pinyin_match(self, detected_pinyin: str) -> tuple[bool, str, float]:
        """
        基于拼音的模糊匹配，判断检测到的拼音是否与唤醒词的拼音相似
        返回值包含是否匹配、最佳匹配的拼音窗口以及相似度分数
        """
        if not detected_pinyin or not self.wake_word_pinyin:
            return False, "", 0.0

        detected_tokens = detected_pinyin.split()
        target_tokens = self.wake_word_pinyin.split()
        if not detected_tokens or not target_tokens:
            return False, "", 0.0

        if self.wake_word_pinyin in detected_pinyin:
            return True, self.wake_word_pinyin, 1.0

        target_joined = "".join(target_tokens)
        target_len = len(target_tokens)
        candidate_lens = {target_len}
        if target_len > 1:
            candidate_lens.add(target_len - 1)
            candidate_lens.add(target_len + 1)

        best_score = 0.0
        best_window = ""

        for win_len in sorted(candidate_lens):
            if win_len <= 0:
                continue

            if len(detected_tokens) < win_len:
                window_tokens_list = [detected_tokens]
            else:
                window_tokens_list = [
                    detected_tokens[i : i + win_len]
                    for i in range(len(detected_tokens) - win_len + 1)
                ]

            for window_tokens in window_tokens_list:
                window_joined = "".join(window_tokens)
                score = SequenceMatcher(None, window_joined, target_joined).ratio()

                if score > best_score:
                    best_score = score
                    best_window = " ".join(window_tokens)

                if score >= self.fuzzy_similarity_threshold:
                    return True, " ".join(window_tokens), score

        return False, best_window, best_score

    @staticmethod
    def count_chinese_characters(input_string: str) -> int:
        """统计输入字符串中中文字符的数量"""
        return len(re.findall(r"[\u4e00-\u9fa5]", input_string))

    def replace_special_characters(self, input_string: str) -> str:
        """根据预定义的词汇映射表替换输入字符串中的特殊字符或常见错误"""
        if not input_string:
            return input_string

        normalized = input_string
        for correct_word, variants in self.word_map.items():
            for variant in variants:
                normalized = normalized.replace(variant, correct_word)

        return normalized

    @staticmethod
    def remove_intent_tags(input_string: str) -> str:
        """移除输入字符串中的意图标签"""
        if not input_string:
            return input_string

        cleaned_string = re.sub(
            r"<INTENT>.*?</INTENT>", "", input_string, flags=re.DOTALL
        )
        return cleaned_string.strip()

    @staticmethod
    def remove_special_symbols(input_string: str) -> str:
        """移除输入字符串中的特殊符号
        只保留中文、英文、数字和常用标点符号
        """
        if not input_string:
            return input_string

        cleaned_string = re.sub(
            r"[^\u4e00-\u9fa5a-zA-Z0-9\s.,!?，。！？]", "", input_string
        )
        return cleaned_string.strip()

    def unify_text(self, input_string: str) -> str:
        """对输入字符串进行统一处理，包括替换特殊字符、移除意图标签和特殊符号"""
        if not input_string:
            return input_string

        # text = self.replace_special_characters(input_string)
        text = self.remove_intent_tags(input_string)
        text = self.remove_special_symbols(text)
        return text.strip()


if __name__ == "__main__":
    processor = AssistantTextProcessor(
        wake_word="小美", fuzzy_similarity_threshold=0.8, word_map=SPECIAL_WORD_MAP
    )

    test_inputs = [
        "小美，今天天气怎么样？<INTENT>查询天气</INTENT>",
        "我想听音乐，小美。<INTENT>播放音乐</INTENT>",
        "小美“”小美:''小美",
        "**小明，你好！**",
        "小美，帮我设置个闹钟",
    ]

    for input_text in test_inputs:
        print(f"原始输入: {input_text}")
        pinyin_text = processor.extract_chinese_and_convert_to_pinyin(input_text)
        print(f"拼音转换: {pinyin_text}")
        is_match, matched_window, similarity = processor.is_kws_pinyin_match(
            pinyin_text
        )
        print(
            f"是否匹配: {is_match}, 最佳匹配窗口: '{matched_window}', 相似度: {similarity:.2f}"
        )
        unified_text = processor.unify_text(input_text)
        print(f"统一处理后文本: {unified_text}")
        print("-" * 50)
