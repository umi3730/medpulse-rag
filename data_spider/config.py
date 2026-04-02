#!/usr/bin/env python3
# coding: utf-8
"""
爬虫配置：路径、Headers、字段映射、停用词
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
OUTPUT_PATH = DATA_DIR / "medical.json"
PROGRESS_PATH = BASE_DIR / ".spider_progress.json"

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# ---------------------------------------------------------------------------
# 字段映射（中文属性 → 英文 key）
# ---------------------------------------------------------------------------
ATTR_MAP = {
    "医保疾病": "yibao_status",
    "患病比例": "get_prob",
    "易感人群": "easy_get",
    "传染方式": "get_way",
    "就诊科室": "cure_department",
    "治疗方式": "cure_way",
    "治疗周期": "cure_lasttime",
    "治愈率": "cured_prob",
    "常用药品": "common_drug",
    "治疗费用": "cost_money",
    "并发症": "acompany",
}

# 需要做空格清理的字段
STRIP_FIELDS = {"yibao_status", "get_prob", "easy_get", "get_way", "cure_lasttime", "cured_prob"}
# 需要按空格分割为列表的字段
SPLIT_FIELDS = {"cure_department", "cure_way", "common_drug"}

# ---------------------------------------------------------------------------
# 停用词（用于症状过滤）
# ---------------------------------------------------------------------------
ALPHABETS = set("abcdefghijklmnopqrstuvwxyz")
DIGITS = set("0123456789")
# 常见中文姓氏首字（用于过滤噪音）
FIRST_NAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄"
    "和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁"
)
STOP_CHARS = ALPHABETS | DIGITS | FIRST_NAMES
