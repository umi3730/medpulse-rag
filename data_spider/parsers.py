#!/usr/bin/env python3
# coding: utf-8
"""
页面解析器：8 个子页面解析 + 数据转换（transform）
"""

import logging

from lxml import etree

from config import ATTR_MAP, STRIP_FIELDS, SPLIT_FIELDS, STOP_CHARS

log = logging.getLogger("spider")


class PageParsers:
    """
    从 xywy.com 各子页面提取结构化数据。

    所有 parse_* 方法接收 HTML 文本，返回解析结果。
    HTTP 请求由 Spider 负责，解析器只做内容提取。
    """

    def __init__(self):
        # 检查项缓存 {url: name}，由 spider 传入 html 时使用
        self._inspect_cache = {}

    # =======================================================================
    # 概述页
    # =======================================================================
    def parse_basic_info(self, html):
        """解析疾病概述页，返回 (name, category, desc, attrs)。"""
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

        # 属性信息
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

    # =======================================================================
    # 通用文本页（病因 / 预防）
    # =======================================================================
    def parse_common(self, html):
        """提取所有 <p> 标签文本，返回合并字符串。"""
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

    # =======================================================================
    # 症状页
    # =======================================================================
    def parse_symptom(self, html):
        """解析症状页，返回症状列表。"""
        if not html:
            return []
        sel = etree.HTML(html)
        symptoms = sel.xpath('//a[@class="gre"]/text()')
        if not symptoms:
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

    # =======================================================================
    # 检查项页
    # =======================================================================
    def parse_inspect(self, html):
        """解析检查项页，返回检查项链接列表（需二次解析获取名称）。"""
        if not html:
            return []
        sel = etree.HTML(html)
        hrefs = sel.xpath('//li[@class="check-item"]/a/@href')
        if not hrefs:
            hrefs = sel.xpath('//div[contains(@class,"check")]//a/@href')
        return hrefs

    def parse_inspect_name(self, html):
        """从检查项详情页提取检查项名称。"""
        if not html:
            return ""
        sel = etree.HTML(html)
        title_list = sel.xpath("//title/text()")
        if title_list:
            return title_list[0].split("结果分析")[0].split("_")[0].strip()
        return ""

    # =======================================================================
    # 治疗页
    # =======================================================================
    def parse_treat(self, html):
        """解析治疗页，返回治疗信息列表。"""
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

    # =======================================================================
    # 食物页
    # =======================================================================
    def parse_food(self, html):
        """解析食物页，返回 (do_eat, not_eat, recommand_eat)。"""
        if not html:
            return [], [], []
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

    # =======================================================================
    # 药品页
    # =======================================================================
    def parse_drug(self, html):
        """解析药品页，返回 (recommand_drug, drug_detail)。"""
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
        recommand_drug = list(set(
            i.split("(")[-1].replace(")", "") for i in drug_detail if i
        ))
        return recommand_drug, drug_detail

    # =======================================================================
    # 数据转换
    # =======================================================================
    @staticmethod
    def transform(name, category, desc, attrs, cause, prevent,
                  symptoms, checks, treat_info, do_eat, not_eat, recommand_eat,
                  recommand_drug, drug_detail, splitter):
        """将各解析器的原始结果合并为最终 JSON 记录。"""
        record = {
            "name": name,
            "desc": desc,
            "category": category,
            "prevent": prevent,
            "cause": cause,
            "symptom": symptoms,
        }
        # 属性字段
        for key in ["yibao_status", "get_prob", "easy_get", "get_way",
                     "cure_department", "cure_way", "cure_lasttime",
                     "cured_prob", "common_drug", "cost_money"]:
            if key in attrs:
                record[key] = attrs[key]
        # 并发症（LLM 分词）
        if "acompany" in attrs:
            raw = attrs["acompany"]
            if isinstance(raw, str):
                record["acompany"] = splitter.split(raw)
            else:
                record["acompany"] = raw
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
