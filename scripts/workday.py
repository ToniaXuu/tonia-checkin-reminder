#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工作日判断 —— 基于 timor.tech 免费节假日接口，自动识别法定节假日与调休补班。

可靠性设计：
  1. 单日接口   —— 带重试，失败自动降级为「周末判断」，不中断提醒
  2. 年度接口   —— 结果按年缓存到 data/holiday_{year}.json，避免重复请求与限流
                    （年度数据一年只变一次，缓存后仅需首次拉取）
"""

import json
import time
from calendar import monthrange
from datetime import datetime
from pathlib import Path

import requests

TIMOR_INFO = "https://timor.tech/api/holiday/info/{date}"
TIMOR_YEAR = "https://timor.tech/api/holiday/year/{year}"
HEADERS = {"User-Agent": "Mozilla/5.0 (tonia-checkin-reminder)"}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def get_workday_info(d, skip_holidays=True):
    """
    判断 d 是否为工作日。

    返回 (是否工作日: bool, 说明: str, 来源: str)
      来源 = 'api'                → 节假日接口判定
      来源 = 'weekend-fallback'   → 接口不可用，按周末规则降级

    timor.tech 的 type.type 含义：
      0 = 工作日   1 = 周末   2 = 法定节假日   3 = 调休补班（上班）
    """
    is_weekend = d.weekday() >= 5

    if not skip_holidays:
        return (not is_weekend), ("周末" if is_weekend else "工作日"), "weekend-fallback"

    url = TIMOR_INFO.format(date=d.strftime("%Y-%m-%d"))
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=8).json()
            if r.get("code") == 0:
                t = r.get("type") or {}
                kind = t.get("type")
                name = t.get("name") or ""
                holiday = r.get("holiday") or {}
                hname = holiday.get("name") or name

                if kind == 3:
                    return True, f"调休补班（{name}）", "api"
                if kind == 0:
                    return True, (name or "工作日"), "api"
                if kind == 1:
                    return False, f"{name or '周末'}（周末）", "api"
                if kind == 2:
                    return False, f"{hname}（法定节假日）", "api"
        except Exception as e:
            if attempt == 2:
                print(f"  ⚠️ 节假日接口异常，降级为周末判断：{e}")
            else:
                time.sleep(1.2)

    return (not is_weekend), ("周末" if is_weekend else "工作日"), "weekend-fallback"


def _year_holiday_map(year):
    """
    全年节假日表（带文件缓存）。
    返回 dict { 'MM-DD': {'holiday': bool, 'name': str} }；彻底失败返回 None。
    年度接口中 holiday=True 表示放假，holiday=False 表示调休上班。
    """
    cache = DATA_DIR / f"holiday_{year}.json"

    # 1) 命中缓存
    if cache.exists():
        try:
            with open(cache, "r", encoding="utf-8") as f:
                blob = json.load(f)
            hm = blob.get("holiday")
            if hm:
                return hm
        except Exception as e:
            print(f"  ⚠️ 节假日缓存损坏，将重新拉取：{e}")

    # 2) 请求接口（带重试）
    for attempt in range(3):
        try:
            r = requests.get(
                TIMOR_YEAR.format(year=year), headers=HEADERS, timeout=12
            ).json()
            if r.get("code") == 0:
                hm = r.get("holiday") or {}
                if hm:
                    try:
                        DATA_DIR.mkdir(parents=True, exist_ok=True)
                        with open(cache, "w", encoding="utf-8") as f:
                            json.dump(
                                {
                                    "_comment": f"{year} 年节假日表缓存，由脚本自动生成，可安全删除",
                                    "year": year,
                                    "fetched": datetime.now().isoformat(timespec="seconds"),
                                    "holiday": hm,
                                },
                                f,
                                ensure_ascii=False,
                                indent=2,
                            )
                        print(f"  💾 已缓存 {year} 年节假日表（{len(hm)} 条特殊日期）")
                    except Exception as e:
                        print(f"  ⚠️ 缓存写入失败（不影响本次运行）：{e}")
                    return hm
        except Exception as e:
            if attempt == 2:
                print(f"  ⚠️ 年度节假日接口异常：{e}")
            else:
                time.sleep(1.5)

    return None


def month_workdays(year, month, today=None):
    """
    统计某月的工作日总数与截至今天的已过工作日数。

    返回 (total, passed)；接口与缓存均不可用时返回 (None, None)。
    """
    hm = _year_holiday_map(year)
    if hm is None:
        return None, None

    today = today or datetime.now()
    total = 0
    passed = 0

    for day in range(1, monthrange(year, month)[1] + 1):
        d = datetime(year, month, day)
        info = hm.get(d.strftime("%m-%d"))
        if info:
            work = not info.get("holiday", False)
        else:
            work = d.weekday() < 5
        if work:
            total += 1
            if d.date() <= today.date():
                passed += 1

    return total, passed
