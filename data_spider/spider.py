#!/usr/bin/env python3
# coding: utf-8
"""
爬虫主类：HTTP 请求、爬取流程、断点续爬
"""

import json
import time
import random
import logging
from pathlib import Path

import requests

from config import HEADERS, OUTPUT_PATH, PROGRESS_PATH
from parsers import PageParsers
from word_splitter import LLMWordSplitter

log = logging.getLogger("spider")


class MedicalSpider:
    """从 xywy.com 爬取疾病数据，直接输出 JSONL 格式。"""

    def __init__(self, output_path=OUTPUT_PATH, start_page=1, end_page=11000,
                 delay=0.3, max_retries=3, test_mode=False,
                 ollama_model="qwen3:8b", ollama_url="http://localhost:11434"):
        self.output_path = Path(output_path)
        self.start_page = start_page
        self.end_page = end_page
        self.delay = delay
        self.max_retries = max_retries
        self.test_mode = test_mode

        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        self.parsers = PageParsers()
        self.splitter = LLMWordSplitter(model=ollama_model, base_url=ollama_url)

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
    # 检查项二次解析（需要 HTTP 请求，放在 spider 层）
    # =======================================================================
    def _resolve_inspect_names(self, hrefs):
        """将检查项链接列表解析为名称列表（带缓存）。"""
        names = []
        for href in hrefs:
            if not href.startswith("http"):
                href = "http://jck.xywy.com" + href if href.startswith("/") else "http://jck.xywy.com/" + href
            if href in self._inspect_cache:
                name = self._inspect_cache[href]
            else:
                html = self.get_html(href)
                name = self.parsers.parse_inspect_name(html)
                self._inspect_cache[href] = name
            if name:
                names.append(name)
        return names

    # =======================================================================
    # 断点续爬
    # =======================================================================
    @staticmethod
    def _load_progress():
        """加载已完成的页码集合。"""
        if PROGRESS_PATH.exists():
            try:
                data = json.loads(PROGRESS_PATH.read_text())
                return set(data.get("done_pages", []))
            except Exception:
                return set()
        return set()

    @staticmethod
    def _save_progress(done_pages):
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

                time.sleep(self.delay + random.uniform(0, 0.3))

        self._save_progress(done_pages)
        log.info("爬取完成：成功 %d 条，失败 %d 条", success_count, fail_count)

    def _crawl_one(self, page):
        """爬取单个疾病页（8 个子页面）并返回转换后的记录。"""
        base = "http://jib.xywy.com/il_sii"
        p = self.parsers

        # 1. 基本信息（最重要，失败则跳过）
        name, category, desc, attrs = p.parse_basic_info(
            self.get_html(f"{base}/gaishu/{page}.htm"))
        if not name:
            return None

        # 2. 病因 & 预防
        cause = p.parse_common(self.get_html(f"{base}/cause/{page}.htm"))
        prevent = p.parse_common(self.get_html(f"{base}/prevent/{page}.htm"))

        # 3. 症状
        symptoms = p.parse_symptom(self.get_html(f"{base}/symptom/{page}.htm"))

        # 4. 检查项（两级解析）
        hrefs = p.parse_inspect(self.get_html(f"{base}/inspect/{page}.htm"))
        checks = self._resolve_inspect_names(hrefs)

        # 5. 治疗
        treat_info = p.parse_treat(self.get_html(f"{base}/treat/{page}.htm"))

        # 6. 食物
        do_eat, not_eat, recommand_eat = p.parse_food(
            self.get_html(f"{base}/food/{page}.htm"))

        # 7. 药品
        recommand_drug, drug_detail = p.parse_drug(
            self.get_html(f"{base}/drug/{page}.htm"))

        # 转换为最终格式
        return p.transform(
            name, category, desc, attrs, cause, prevent,
            symptoms, checks, treat_info,
            do_eat, not_eat, recommand_eat,
            recommand_drug, drug_detail,
            splitter=self.splitter,
        )
