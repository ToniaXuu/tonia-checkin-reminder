#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tonia-checkin-reminder — 打卡提醒推送（支持多条提醒 · 多通道）
==================================================================

配置来自 config.json 的 reminders 数组，每条提醒有自己的：
  时间 / 通道 / 文案 / 开关 / ID

轮询模式：定时器只负责「每隔几分钟叫醒脚本一次」，
发不发由脚本判断 —— 当前时间是否落在某条提醒的 [设定时间, +容差] 窗口内。
因此网页上改时间与文案即可立即生效，无需改动定时器。

用法:
    python scripts/send_reminder.py --list              # 列出所有提醒与当前窗口状态
    python scripts/send_reminder.py                     # auto：按时间窗口判断该发哪些
    python scripts/send_reminder.py --dry-run           # 只打印，不发送、不写日志
    python scripts/send_reminder.py --id dt-1705        # 强制处理指定提醒（忽略窗口）
    python scripts/send_reminder.py --id dt-1705 --force  # 同时忽略当日去重

环境变量:
    DINGTALK_WEBHOOK / DINGTALK_SECRET
    FEISHU_WEBHOOK   / FEISHU_SECRET
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import random
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("❌ 缺少依赖：pip install requests")

from workday import get_workday_info, month_workdays

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
CONFIG_FILE = ROOT_DIR / "config.json"
QUOTES_FILE = SCRIPT_DIR / "quotes.json"
LOG_FILE = ROOT_DIR / "data" / "reminder_log.json"

CST = timezone(timedelta(hours=8))
WEEKDAY_CN = "一二三四五六日"

WEATHER_MAP = {
    0: "☀️ 晴", 1: "🌤 晴间多云", 2: "⛅ 多云", 3: "☁️ 阴",
    45: "🌫 雾", 48: "🌫 雾凇",
    51: "🌦 毛毛雨", 53: "🌦 小雨", 55: "🌧 中雨",
    56: "🌧 冻雨", 57: "🌧 冻雨",
    61: "🌧 小雨", 63: "🌧 中雨", 65: "🌧 大雨",
    66: "🌧 冻雨", 67: "🌧 冻雨",
    71: "🌨 小雪", 73: "🌨 中雪", 75: "❄️ 大雪", 77: "🌨 雪粒",
    80: "🌦 阵雨", 81: "🌧 阵雨", 82: "⛈ 强阵雨",
    85: "🌨 阵雪", 86: "❄️ 阵雪",
    95: "⛈ 雷阵雨", 96: "⛈ 雷暴伴冰雹", 99: "⛈ 强雷暴",
}


# ────────────────────────── 基础工具 ──────────────────────────

def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def now_cn():
    return datetime.now(CST)


def date_cn(d):
    return f"{d.month}月{d.day}日 星期{WEEKDAY_CN[d.weekday()]}"


def parse_hhmm(s):
    hh, mm = str(s).split(":")
    return int(hh), int(mm)


# ────────────────────────── 天气 ──────────────────────────

def fetch_weather(city):
    """open-meteo 免费无 key 天气；失败返回 None，不影响提醒。"""
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={city['lat']}&longitude={city['lon']}"
            "&daily=temperature_2m_max,temperature_2m_min,weathercode,"
            "precipitation_probability_max"
            f"&timezone={urllib.parse.quote(city.get('timezone', 'Asia/Shanghai'))}"
            "&forecast_days=1"
        )
        r = requests.get(url, timeout=10).json()
        d = r.get("daily") or {}
        if not d:
            return None
        code = d["weathercode"][0]
        rain = (d.get("precipitation_probability_max") or [None])[0]
        line = f"{WEATHER_MAP.get(code, '🌡 未知')} {int(d['temperature_2m_min'][0])}°C ~ {int(d['temperature_2m_max'][0])}°C"
        if rain is not None and rain >= 40:
            line += f"　☔ 降水概率 {rain}%"
        return line
    except Exception as e:
        print(f"  ⚠️ 天气获取失败：{e}")
        return None


# ────────────────────────── 通道：钉钉 ──────────────────────────

def _dingtalk_url(webhook, secret):
    if not secret:
        return webhook
    ts = str(round(time.time() * 1000))
    h = hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(h))
    sep = "&" if "?" in webhook else "?"
    return f"{webhook}{sep}timestamp={ts}&sign={sign}"


def send_dingtalk(webhook, secret, title, text, dry=False):
    if dry:
        print("     🧪 [钉钉] dry-run，未实际发送")
        return True
    try:
        payload = {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
        r = requests.post(_dingtalk_url(webhook, secret), json=payload, timeout=15).json()
        if r.get("errcode") == 0:
            print("     ✅ 钉钉推送成功")
            return True
        print(f"     ❌ 钉钉推送失败：errcode={r.get('errcode')} {r.get('errmsg')}")
    except Exception as e:
        print(f"     ❌ 钉钉推送异常：{e}")
    return False


# ────────────────────────── 通道：飞书 ──────────────────────────

def _feishu_sign(secret, ts):
    """飞书加签：以 'timestamp\\nsecret' 为密钥，对空串做 HMAC-SHA256 后 base64。"""
    s = f"{ts}\n{secret}"
    return base64.b64encode(
        hmac.new(s.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")


def send_feishu(webhook, secret, card, dry=False):
    if dry:
        print("     🧪 [飞书] dry-run，未实际发送")
        return True
    try:
        payload = {"msg_type": "interactive", "card": card}
        if secret:
            ts = str(int(time.time()))
            payload["timestamp"] = ts
            payload["sign"] = _feishu_sign(secret, ts)
        r = requests.post(webhook, json=payload, timeout=15).json()
        if r.get("code") == 0 or r.get("StatusCode") == 0:
            print("     ✅ 飞书推送成功")
            return True
        print(f"     ❌ 飞书推送失败：{r.get('msg') or r}")
    except Exception as e:
        print(f"     ❌ 飞书推送异常：{e}")
    return False


# ────────────────────────── 消息组装 ──────────────────────────

def build_context(cfg, rem, now):
    """把单条提醒组装成渲染上下文，钉钉 / 飞书共用。"""
    opts = cfg.get("options") or {}
    city = cfg.get("city") or {}

    # 正文：优先用自定义文案；为空时才回退到随机文案
    main = (rem.get("message") or "").strip()
    if not main and opts.get("include_quote", False):
        pool = load_json(QUOTES_FILE, {}) or {}
        lst = (pool.get("out") or []) + (pool.get("in") or [])
        if lst:
            main = random.choice(lst)

    weather_line = ""
    if opts.get("include_weather", False):
        w = fetch_weather(city)
        if w:
            weather_line = w

    stats_line = ""
    if opts.get("include_month_stats", False):
        total, passed = month_workdays(now.year, now.month)
        if total:
            stats_line = f"本月工作日进度 {passed}/{total} 天"

    return {
        "date_cn": date_cn(now),
        "time": now.strftime("%H:%M"),
        "label": rem.get("label") or "打卡提醒",
        "emoji": rem.get("emoji") or "🔔",
        "main": main,
        "city": city.get("name", ""),
        "weather_line": weather_line,
        "stats_line": stats_line,
    }


def build_dingtalk(c):
    title = f"{c['emoji']} {c['label']}提醒 | {c['date_cn']}"

    parts = [
        f"### {c['emoji']} {c['label']}提醒",
        "",
        f"{c['date_cn']} · {c['time']}",
    ]

    if c["main"]:
        parts += ["", "---", "", f"**{c['main']}**"]

    extras = []
    if c["weather_line"]:
        extras.append(f"☁️ {c['city']}天气　{c['weather_line']}")
    if c["stats_line"]:
        extras.append(f"▸ {c['stats_line']}")
    if extras:
        parts += ["", "---", ""] + ["  \n".join(extras)]

    return title, "\n".join(parts)


def build_feishu(c):
    title = f"{c['emoji']} {c['label']}提醒 | {c['date_cn']}"

    elements = [
        {"tag": "div", "fields": [
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**📅 日期**\n{c['date_cn']}"}},
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**🕐 时间**\n{c['time']}"}},
        ]}
    ]

    if c["main"]:
        elements += [
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": c["main"]}},
        ]

    extras = []
    if c["weather_line"]:
        extras.append(f"☁️ {c['city']}天气　{c['weather_line']}")
    if c["stats_line"]:
        extras.append(f"▸ {c['stats_line']}")
    if extras:
        elements += [
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(extras)}},
        ]

    card = {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {"template": "orange", "title": {"tag": "plain_text", "content": title}},
        "elements": elements,
    }
    return title, card


# ────────────────────────── 通道分发 ──────────────────────────

def dispatch(cfg, rem, ctx, dry=False):
    """按 reminder.channels 逐个通道发送，返回成功通道列表。"""
    ch_cfg = cfg.get("channels") or {}
    want = rem.get("channels") or ["dingtalk"]
    sent = []

    for name in want:
        cc = ch_cfg.get(name) or {}
        if not cc.get("enabled", True):
            print(f"     ⏭️ 通道 {name} 已在配置中关闭")
            continue

        wh = os.environ.get(cc.get("webhook_env", ""), "")
        sec = os.environ.get(cc.get("secret_env", ""), "")
        if not wh:
            print(f"     ⚠️ 未配置环境变量 {cc.get('webhook_env')}，跳过 {name}")
            continue

        if name == "dingtalk":
            title, text = build_dingtalk(ctx)
            print(f"     📤 [钉钉] {title}")
            if send_dingtalk(wh, sec, title, text, dry=dry) and not dry:
                sent.append("dingtalk")
        elif name == "feishu":
            title, card = build_feishu(ctx)
            print(f"     📤 [飞书] {title}")
            if send_feishu(wh, sec, card, dry=dry) and not dry:
                sent.append("feishu")
        else:
            print(f"     ⚠️ 未知通道：{name}")

    return sent


# ────────────────────────── 窗口判定与去重 ──────────────────────────

def iter_with_delta(reminders, now, tolerance):
    """产出 (reminder, delta分钟)；delta 为当前时间相对该提醒设定时间的差值。"""
    for rem in reminders:
        if not rem.get("enabled", True):
            continue
        t = rem.get("time")
        if not t:
            continue
        try:
            th, tm = parse_hhmm(t)
        except Exception:
            print(f"  ⚠️ [{rem.get('id')}] 时间格式非法：{t}")
            continue
        target = now.replace(hour=th, minute=tm, second=0, microsecond=0)
        yield rem, (now - target).total_seconds() / 60


def resolve_due(cfg, now, tolerance):
    """
    返回 [(reminder, delta), ...] —— 当前命中时间窗口的提醒（按时间先后排序）。
    窗口 = [设定时间 - 1分钟, 设定时间 + 容差]，-1 分钟用于容忍秒级时钟误差。
    """
    due = []
    for rem, delta in iter_with_delta(cfg.get("reminders") or [], now, tolerance):
        if -1 <= delta <= tolerance:
            due.append((rem, delta))
    due.sort(key=lambda x: x[1])
    return due


def sent_today(rid, day):
    """查询当天是否已推送过该条提醒（按 ID 去重）。返回 ts 或 None。"""
    log = load_json(LOG_FILE, {"history": []}) or {}
    for h in log.get("history", []):
        if h.get("date") == day and h.get("rid") == rid:
            return h.get("ts", "")
    return None


def append_log(rem, channels):
    log = load_json(LOG_FILE, {"history": []}) or {"history": []}
    log.setdefault("history", [])
    log["history"].append({
        "date": now_cn().strftime("%Y-%m-%d"),
        "rid": rem.get("id"),
        "time": rem.get("time"),
        "label": rem.get("label", ""),
        "ts": now_cn().isoformat(timespec="seconds"),
        "channels": channels,
    })
    log["history"] = log["history"][-500:]
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ────────────────────────── 主流程 ──────────────────────────

def cmd_list(cfg, now, tolerance):
    reminders = cfg.get("reminders") or []
    print(f"🕐 当前 {now.strftime('%Y-%m-%d %H:%M:%S')}（UTC+8）· 容差 {tolerance} 分钟\n")
    if not reminders:
        print("  （config.json 里没有任何提醒）")
        return 0
    for rem, delta in iter_with_delta(reminders, now, tolerance):
        in_win = -1 <= delta <= tolerance
        flag = "  ★ 正在窗口内" if in_win else ""
        print(f"  [{rem.get('id')}] {rem.get('time')}  {'/'.join(rem.get('channels') or [])}{flag}")
        print(f"       {rem.get('message') or '（无自定义文案）'}")
    off = [r.get("id") for r in reminders if not r.get("enabled", True)]
    if off:
        print(f"\n  已停用：{', '.join(off)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="打卡提醒推送")
    ap.add_argument("--id", dest="rid", default=None, help="只处理指定 ID 的提醒（忽略时间窗口）")
    ap.add_argument("--dry-run", action="store_true", help="只打印不发送、不写日志")
    ap.add_argument("--force", action="store_true", help="忽略工作日判断与当日去重")
    ap.add_argument("--list", action="store_true", help="列出所有提醒及当前窗口状态")
    args = ap.parse_args()

    cfg = load_json(CONFIG_FILE) or {}
    reminders = cfg.get("reminders") or []
    opts = cfg.get("options") or {}
    tolerance = int(opts.get("tolerance_minutes", 10))
    now = now_cn()
    today = now.strftime("%Y-%m-%d")

    if args.list:
        return cmd_list(cfg, now, tolerance)

    if not reminders:
        print("❌ config.json 里没有配置任何提醒（reminders 为空）")
        return 1

    print(f"🕐 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)")

    # 1) 选出本次要处理的提醒
    if args.rid:
        rem = next((r for r in reminders if r.get("id") == args.rid), None)
        if not rem:
            print(f"❌ 找不到 id 为 {args.rid} 的提醒")
            return 1
        targets = [(rem, 0.0)]
        print(f"🎯 手动指定：[{rem['id']}] {rem.get('time')}")
    else:
        targets = resolve_due(cfg, now, tolerance)
        if not targets:
            print(f"⏭️ 当前没有提醒命中时间窗口（容差 {tolerance} 分钟），退出")
            print("   · 查看全部提醒与窗口状态：--list")
            print("   · 强制发送某条提醒：--id <提醒ID>")
            return 0
        for rem, delta in targets:
            print(f"🎯 命中 [{rem['id']}] {rem.get('time')}（距设定时间 {int(round(delta))} 分钟）")

    # 2) 工作日判定
    work, work_desc, src = get_workday_info(now, opts.get("skip_holidays", True))
    print(f"📅 工作日判定：{'是' if work else '否'} — {work_desc}（来源：{src}）")
    if not work and not args.force:
        print("🎉 今天不用上班，静默跳过（--force 可强制发送）")
        return 0

    # 3) 逐条处理
    ok_count = 0
    for rem, _ in targets:
        print(f"\n─── [{rem.get('id')}] {rem.get('label', '提醒')} {rem.get('time')} ───")

        if not rem.get("enabled", True) and not args.force:
            print("     ⏭️ 该提醒已停用")
            continue

        prev = sent_today(rem.get("id"), today)
        if prev and not args.force:
            print(f"     ✅ 今天已推送过（{prev}），跳过")
            continue

        ctx = build_context(cfg, rem, now)

        if args.dry_run:
            _, text = build_dingtalk(ctx)
            print("     📨 消息预览：")
            for line in text.splitlines():
                print("        " + line)

        sent = dispatch(cfg, rem, ctx, dry=args.dry_run)
        if sent:
            # --force 属于「临时强制发送」，不写入去重日志，
            # 否则测试一次就会把当天真正该发的那一轮拦掉。
            if args.force:
                print("     📝 --force 模式：不写入去重日志（不影响当日正常调度）")
            else:
                append_log(rem, sent)
                print(f"     📝 已记录日志：{', '.join(sent)}")
            ok_count += 1

    print(f"\n完成：本次成功推送 {ok_count} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
