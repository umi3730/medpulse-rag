#!/usr/bin/env python3
# coding: utf-8
"""
医药知识图谱数据爬虫
从 xywy.com（寻医问药网）爬取疾病信息，输出与 data/medical.json 格式一致的 JSONL 文件。

用法:
    python3 data_spider.py                          # 爬取全部 1-11000
    python3 data_spider.py --start 1 --end 100      # 指定范围
    python3 data_spider.py --resume                  # 断点续爬
    python3 data_spider.py --start 1 --end 5 --test  # 测试模式，打印不写文件
"""

import argparse
import json
import os
import re
import sys
import time
import random
import logging
from pathlib import Path

import requests
from lxml import etree

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("spider")

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
DICT_DIR = BASE_DIR.parent / "dict"
OUTPUT_PATH = DATA_DIR / "medical.json"
PROGRESS_PATH = BASE_DIR / ".spider_progress.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# 字段映射（中文属性 → 英文 key），来自原 build_data.py
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
# 分词工具（用于并发症切分，取自 max_cut.py，去掉文件依赖）
# ---------------------------------------------------------------------------
class CutWords:
    """基于词典的最大双向匹配分词，用于切分并发症文本。"""

    def __init__(self):
        dict_path = DICT_DIR / "disease.txt"
        self.word_dict = set()
        self.max_wordlen = 0
        if dict_path.exists():
            for line in open(dict_path, encoding="utf-8"):
                wd = line.strip()
                if wd:
                    self.word_dict.add(wd)
                    if len(wd) > self.max_wordlen:
                        self.max_wordlen = len(wd)
        if self.max_wordlen == 0:
            self.max_wordlen = 5

    def max_forward_cut(self, sent):
        cutlist, index = [], 0
        while index < len(sent):
            matched = False
            for i in range(self.max_wordlen, 0, -1):
                cand = sent[index: index + i]
                if cand in self.word_dict:
                    cutlist.append(cand)
                    matched = True
                    break
            if not matched:
                i = 1
                cutlist.append(sent[index])
            index += i
        return cutlist

    def max_backward_cut(self, sent):
        cutlist, index = [], len(sent)
        while index > 0:
            matched = False
            for i in range(self.max_wordlen, 0, -1):
                tmp = i + 1
                cand = sent[index - tmp: index]
                if cand in self.word_dict:
                    cutlist.append(cand)
                    matched = True
                    break
            if not matched:
                tmp = 1
                cutlist.append(sent[index - 1])
            index -= tmp
        return cutlist[::-1]

    def max_biward_cut(self, sent):
        fwd = self.max_forward_cut(sent)
        bwd = self.max_backward_cut(sent)
        single = lambda wl: sum(1 for w in wl if len(w) == 1)
        if len(fwd) == len(bwd):
            return bwd if single(fwd) > single(bwd) else fwd
        return fwd if len(bwd) > len(fwd) else bwd


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


# ---------------------------------------------------------------------------
# 爬虫主类
# ---------------------------------------------------------------------------
class MedicalSpider:
    """从 xywy.com 爬取疾病数据，直接输出 JSONL 格式。"""

    def __init__(self, output_path=OUTPUT_PATH, start_page=1, end_page=11000,
                 delay=0.3, max_retries=3, test_mode=False):
        self.output_path = Path(output_path)
        self.start_page = start_page
        self.end_page = end_page
        self.delay = delay
        self.max_retries = max_retries
        self.test_mode = test_mode

        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        self.cutter = CutWords()

        # 检查项缓存 {url: name}
        self._inspect_cache = {}

    # =======================================================================
    # HTTP 请求
    # =======================================================================
    def get_html(self, url):
        """请求页面并返回 HTML 文本（GBK 编码）。失败返回空字符串。"""
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, timeout=15)
                resp.encoding = "gbk"
                if resp.status_code == 200:
                    return resp.text
                if resp.status_code == 404:
                    return ""
                log.warning("HTTP %d for %s (attempt %d)", resp.status_code, url, attempt)
            except requests.RequestException as e:
                log.warning("Request error for %s: %s (attempt %d)", url, e, attempt)
            if attempt < self.max_retries:
                time.sleep(1 * attempt)
        return ""

    # =======================================================================
    # 页面解析器
    # =======================================================================
    def parse_basic_info(self, url):
        """解析疾病概述页，返回 (name, category, desc, attributes_dict)。"""
        html = self.get_html(url)
        if not html:
            return None, [], "", {}
        sel = etree.HTML(html)

        # 疾病名称
        title_list = sel.xpath("//title/text()")
        title = title_list[0] if title_list else ""
        name = title.split("的简介")[0].split("_")[0].strip() if title else ""

        # 分类
        category = sel.xpath('//div[@class="wrap mt10 nav-bar"]/a/text()')
        if not category:
            category = sel.xpath('//div[contains(@class,"nav-bar")]//a/text()')

        # 描述
        desc_parts = sel.xpath('//div[@class="jib-articl-con jib-lh-articl"]/p/text()')
        if not desc_parts:
            desc_parts = sel.xpath('//div[contains(@class,"jib-articl-con")]//p/text()')
        desc = "\n".join(desc_parts).replace("\r\n\t", "").replace("\r\n\n\n", "").replace("\r\n", "\n").strip()

        # 属性信息（如 医保疾病：否、治疗周期：3个月 等）
        ps = sel.xpath('//div[@class="mt20 articl-know"]/p')
        if not ps:
            ps = sel.xpath('//div[contains(@class,"articl-know")]/p')
        attrs = {}
        for p in ps:
            info = p.xpath("string(.)").replace("\r", "").replace("\n", "").replace("\xa0", "").replace("\t", "").strip()
            if "：" in info:
                parts = info.split("：", 1)
                key, value = parts[0].strip(), parts[1].strip()
                en_key = ATTR_MAP.get(key)
                if en_key:
                    if en_key in STRIP_FIELDS:
                        value = value.replace(" ", "").replace("\t", "")
                    elif en_key in SPLIT_FIELDS:
                        value = [v for v in value.split(" ") if v]
                    attrs[en_key] = value

        return name, category, desc, attrs

    def parse_common(self, url):
        """通用解析：提取所有 <p> 标签文本，返回合并字符串。"""
        html = self.get_html(url)
        if not html:
            return ""
        sel = etree.HTML(html)
        ps = sel.xpath("//p")
        lines = []
        for p in ps:
            info = p.xpath("string(.)").replace("\r", "").replace("\n", "").replace("\xa0", "").replace("\t", "").strip()
            if info:
                lines.append(info)
        return "\n".join(lines)

    def parse_symptom(self, url):
        """解析症状页，返回症状列表。"""
        html = self.get_html(url)
        if not html:
            return []
        sel = etree.HTML(html)
        symptoms = sel.xpath('//a[@class="gre"]/text()')
        if not symptoms:
            # 备选选择器
            symptoms = sel.xpath('//div[contains(@class,"symptom")]//a/text()')
        if not symptoms:
            symptoms = sel.xpath('//p[@class="gre"]/text()')
        # 过滤停用词
        filtered = []
        for s in symptoms:
            s = s.strip()
            if s and s[0] not in STOP_CHARS and len(s) > 1:
                filtered.append(s)
        return list(set(filtered))

    def parse_inspect(self, url):
        """解析检查项页，返回检查项名称列表。"""
        html = self.get_html(url)
        if not html:
            return []
        sel = etree.HTML(html)
        # 获取检查项链接
        hrefs = sel.xpath('//li[@class="check-item"]/a/@href')
        if not hrefs:
            hrefs = sel.xpath('//div[contains(@class,"check")]//a/@href')
        # 解析每个检查项的名称
        names = []
        for href in hrefs:
            name = self._get_inspect_name(href)
            if name:
                names.append(name)
        return names

    def _get_inspect_name(self, url):
        """获取单个检查项的名称（带缓存）。"""
        if not url.startswith("http"):
            url = "http://jck.xywy.com" + url if url.startswith("/") else "http://jck.xywy.com/" + url
        if url in self._inspect_cache:
            return self._inspect_cache[url]
        html = self.get_html(url)
        if not html:
            return ""
        sel = etree.HTML(html)
        title_list = sel.xpath("//title/text()")
        name = ""
        if title_list:
            name = title_list[0].split("结果分析")[0].split("_")[0].strip()
        self._inspect_cache[url] = name
        return name

    def parse_treat(self, url):
        """解析治疗页，返回治疗信息列表。"""
        html = self.get_html(url)
        if not html:
            return []
        sel = etree.HTML(html)
        ps = sel.xpath('//div[starts-with(@class,"mt20 articl-know")]/p')
        if not ps:
            ps = sel.xpath('//div[contains(@class,"articl-know")]/p')
        items = []
        for p in ps:
            info = p.xpath("string(.)").replace("\r", "").replace("\n", "").replace("\xa0", "").replace("\t", "").strip()
            if info:
                items.append(info)
        return items

    def parse_food(self, url):
        """解析食物页，返回 {do_eat, not_eat, recommand_eat}。"""
        html = self.get_html(url)
        if not html:
            return {}, [], []
        sel = etree.HTML(html)
        divs = sel.xpath('//div[@class="diet-img clearfix mt20"]')
        if not divs:
            divs = sel.xpath('//div[contains(@class,"diet-img")]')
        do_eat, not_eat, recommand_eat = [], [], []
        try:
            if len(divs) > 0:
                do_eat = [t.strip() for t in divs[0].xpath(".//div/p/text()") if t.strip()]
            if len(divs) > 1:
                not_eat = [t.strip() for t in divs[1].xpath(".//div/p/text()") if t.strip()]
            if len(divs) > 2:
                recommand_eat = [t.strip() for t in divs[2].xpath(".//div/p/text()") if t.strip()]
        except Exception:
            pass
        return do_eat, not_eat, recommand_eat

    def parse_drug(self, url):
        """解析药品页，返回 (recommand_drug, drug_detail)。"""
        html = self.get_html(url)
        if not html:
            return [], []
        sel = etree.HTML(html)
        drug_detail = [
            i.replace("\n", "").replace("\t", "").replace(" ", "")
            for i in sel.xpath('//div[@class="fl drug-pic-rec mr30"]/p/a/text()')
        ]
        if not drug_detail:
            drug_detail = [
                i.replace("\n", "").replace("\t", "").replace(" ", "")
                for i in sel.xpath('//div[contains(@class,"drug-pic")]//p//a/text()')
            ]
        # 提取药品名（去括号内厂商名）
        recommand_drug = list(set(
            i.split("(")[-1].replace(")", "") for i in drug_detail if i
        ))
        return recommand_drug, drug_detail

    # =======================================================================
    # 数据转换（合并 build_data.py 的逻辑）
    # =======================================================================
    def transform(self, name, category, desc, attrs, cause, prevent,
                  symptoms, checks, treat_info, do_eat, not_eat, recommand_eat,
                  recommand_drug, drug_detail):
        """将解析结果转换为最终 JSON 记录（与 data/medical.json 格式一致）。"""
        record = {}
        record["name"] = name
        record["desc"] = desc
        record["category"] = category
        record["prevent"] = prevent
        record["cause"] = cause
        record["symptom"] = symptoms
        # 属性字段
        for key in ["yibao_status", "get_prob", "easy_get", "get_way",
                     "cure_department", "cure_way", "cure_lasttime",
                     "cured_prob", "common_drug", "cost_money"]:
            if key in attrs:
                record[key] = attrs[key]
        # 并发症（需要分词）
        if "acompany" in attrs:
            raw = attrs["acompany"]
            if isinstance(raw, str):
                acompany = [w for w in self.cutter.max_biward_cut(raw) if len(w) > 1]
            else:
                acompany = raw
            record["acompany"] = acompany
        # 检查
        record["check"] = checks
        # 食物
        if do_eat:
            record["do_eat"] = do_eat
        if not_eat:
            record["not_eat"] = not_eat
        if recommand_eat:
            record["recommand_eat"] = recommand_eat
        # 药品
        record["recommand_drug"] = recommand_drug
        record["drug_detail"] = drug_detail
        return record

    # =======================================================================
    # 断点续爬支持
    # =======================================================================
    def _load_progress(self):
        """加载已完成的页码集合。"""
        if PROGRESS_PATH.exists():
            try:
                data = json.loads(PROGRESS_PATH.read_text())
                return set(data.get("done_pages", []))
            except Exception:
                return set()
        return set()

    def _save_progress(self, done_pages):
        """保存进度。"""
        PROGRESS_PATH.write_text(json.dumps({"done_pages": sorted(done_pages)}, ensure_ascii=False))

    # =======================================================================
    # 主流程
    # =======================================================================
    def crawl(self, resume=False):
        """爬取主流程。"""
        done_pages = self._load_progress() if resume else set()
        if resume and done_pages:
            log.info("断点续爬：已完成 %d 页，从断点继续", len(done_pages))

        # 确保输出目录存在
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if resume else "w"
        success_count = 0
        fail_count = 0

        with open(self.output_path, mode, encoding="utf-8") as f:
            for page in range(self.start_page, self.end_page + 1):
                if page in done_pages:
                    continue
                try:
                    record = self._crawl_one(page)
                    if record and record.get("name"):
                        if self.test_mode:
                            print(json.dumps(record, ensure_ascii=False, indent=2))
                        else:
                            f.write(json.dumps(record, ensure_ascii=False) + "\n")
                            f.flush()
                        success_count += 1
                        log.info("[%d/%d] ✓ %s", page, self.end_page, record["name"])
                    else:
                        log.debug("[%d] 无数据，跳过", page)

                    done_pages.add(page)
                    # 每 50 页保存一次进度
                    if page % 50 == 0:
                        self._save_progress(done_pages)

                except KeyboardInterrupt:
                    log.info("用户中断，保存进度...")
                    self._save_progress(done_pages)
                    log.info("已爬取 %d 条，进度已保存，可用 --resume 继续", success_count)
                    return
                except Exception as e:
                    fail_count += 1
                    log.error("[%d] 异常: %s", page, e)

                # 限速：随机延迟
                time.sleep(self.delay + random.uniform(0, 0.3))

        # 最终保存进度
        self._save_progress(done_pages)
        log.info("爬取完成：成功 %d 条，失败 %d 条", success_count, fail_count)

    def _crawl_one(self, page):
        """爬取单个疾病页（8 个子页面）并返回转换后的记录。"""
        base = "http://jib.xywy.com/il_sii"

        # 1. 基本信息（最重要，失败则跳过）
        name, category, desc, attrs = self.parse_basic_info(f"{base}/gaishu/{page}.htm")
        if not name:
            return None

        # 2. 病因 & 预防
        cause = self.parse_common(f"{base}/cause/{page}.htm")
        prevent = self.parse_common(f"{base}/prevent/{page}.htm")

        # 3. 症状
        symptoms = self.parse_symptom(f"{base}/symptom/{page}.htm")

        # 4. 检查项
        checks = self.parse_inspect(f"{base}/inspect/{page}.htm")

        # 5. 治疗
        treat_info = self.parse_treat(f"{base}/treat/{page}.htm")

        # 6. 食物
        do_eat, not_eat, recommand_eat = self.parse_food(f"{base}/food/{page}.htm")

        # 7. 药品
        recommand_drug, drug_detail = self.parse_drug(f"{base}/drug/{page}.htm")

        # 转换为最终格式
        return self.transform(
            name, category, desc, attrs, cause, prevent,
            symptoms, checks, treat_info,
            do_eat, not_eat, recommand_eat,
            recommand_drug, drug_detail,
        )


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="医药知识图谱数据爬虫")
    parser.add_argument("--start", type=int, default=1, help="起始页码 (默认 1)")
    parser.add_argument("--end", type=int, default=11000, help="结束页码 (默认 11000)")
    parser.add_argument("--output", type=str, default=str(OUTPUT_PATH), help="输出文件路径")
    parser.add_argument("--resume", action="store_true", help="断点续爬")
    parser.add_argument("--delay", type=float, default=0.3, help="请求间隔秒数 (默认 0.3)")
    parser.add_argument("--test", action="store_true", help="测试模式：只打印不写文件")
    args = parser.parse_args()

    spider = MedicalSpider(
        output_path=args.output,
        start_page=args.start,
        end_page=args.end,
        delay=args.delay,
        test_mode=args.test,
    )
    spider.crawl(resume=args.resume)


if __name__ == "__main__":
    main()
