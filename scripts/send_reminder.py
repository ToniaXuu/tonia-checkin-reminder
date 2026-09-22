#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tonia-checkin-reminder — 每日上下班打卡提醒（钉钉 + 飞书双通道）
==================================================================

定时器（cron-job.org 精确触发 GitHub Actions）调用本脚本，
自动判断工作日 + 组装消息 + 双通道推送。

用法:
    python scripts/send_reminder.py                 # auto：按当前时间判断上/下班
    python scripts/send_reminder.py in              # 强制上班提醒
    python scripts/send_reminder.py out             # 强制下班提醒
    python scripts/send_reminder.py in --dry-run    # 只打印，不发送、不写日志
    python scripts/send_reminder.py in --force      # 忽略工作日判断（方便测试）

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
    hh, mm = s.split(":")
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
        return {
            "weather": WEATHER_MAP.get(code, "🌡 未知"),
            "temp_min": int(d["temperature_2m_min"][0]),
            "temp_max": int(d["temperature_2m_max"][0]),
            "rain": rain,
        }
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
    payload = {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
    if dry:
        print("  🧪 [钉钉] 已跳过实际发送（dry-run）")
        return True
    try:
        r = requests.post(_dingtalk_url(webhook, secret), json=payload, timeout=15).json()
        if r.get("errcode") == 0:
            print("  ✅ 钉钉推送成功")
            return True
        print(f"  ❌ 钉钉推送失败：{r.get('errmsg')}")
    except Exception as e:
        print(f"  ❌ 钉钉推送异常：{e}")
    return False


# ────────────────────────── 通道：飞书 ──────────────────────────

def _feishu_sign(secret, ts):
    """飞书加签：以 'timestamp\\nsecret' 为密钥，对空串做 HMAC-SHA256 后 base64。"""
    s = f"{ts}\n{secret}"
    return base64.b64encode(
        hmac.new(s.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")


def send_feishu(webhook, secret, card, dry=False):
    payload = {"msg_type": "interactive", "card": card}
    if secret:
        ts = str(int(time.time()))
        payload["timestamp"] = ts
        payload["sign"] = _feishu_sign(secret, ts)
    if dry:
        print("  🧪 [飞书] 已跳过实际发送（dry-run）")
        return True
    try:
        r = requests.post(webhook, json=payload, timeout=15).json()
        if r.get("code") == 0 or r.get("StatusCode") == 0:
            print("  ✅ 飞书推送成功")
            return True
        print(f"  ❌ 飞书推送失败：{r.get('msg') or r}")
    except Exception as e:
        print(f"  ❌ 飞书推送异常：{e}")
    return False


# ────────────────────────── 消息组装 ──────────────────────────

def build_context(cfg, rtype, sc, now, work_desc):
    """把消息内容组装成一份上下文，钉钉 / 飞书共用。"""
    opts = cfg.get("options", {})
    city = cfg.get("city", {})
    today = date_cn(now)
    time_line = now.strftime("%H:%M")

    # 截止时间与倒计时
    dl_h, dl_m = parse_hhmm(sc["deadline"])
    dl = now.replace(hour=dl_h, minute=dl_m, second=0, microsecond=0)
    delta_min = (dl - now).total_seconds() / 60
    if delta_min > 1:
        cd = f"还有 {int(round(delta_min))} 分钟"
    elif delta_min > -1:
        cd = "就是现在"
    else:
        cd = f"已过 {int(round(-delta_min))} 分钟"
    deadline_line = f"{sc['deadline']}（{cd}）" if opts.get("include_countdown", True) else sc["deadline"]

    # 天气
    weather_line = "—"
    if opts.get("include_weather", True):
        w = fetch_weather(city)
        if w:
            weather_line = f"{w['weather']} {w['temp_min']}°C ~ {w['temp_max']}°C"
            if w.get("rain") is not None and w["rain"] >= 40:
                weather_line += f"　☔ 降水概率 {w['rain']}%"

    # 出门清单
    checklist = opts.get(f"checklist_{rtype}") or []
    checklist_line = " · ".join(checklist) if checklist else ""

    # 月度工作日进度
    stats_line = ""
    if opts.get("include_month_stats", True):
        total, passed = month_workdays(now.year, now.month)
        if total:
            stats_line = f"本月工作日进度 {passed}/{total} 天"

    # 随机文案
    quote = ""
    if opts.get("include_quote", True):
        pool = load_json(QUOTES_FILE, {}) or {}
        lst = pool.get(rtype) or []
        if lst:
            quote = random.choice(lst)

    return {
        "date_cn": today,
        "time": time_line,
        "deadline_line": deadline_line,
        "city": city.get("name", ""),
        "weather_line": weather_line,
        "checklist_line": checklist_line,
        "stats_line": stats_line,
        "quote": quote,
        "work_desc": work_desc,
        "label": sc["label"],
        "emoji": sc.get("emoji", "🔔"),
        "rtype": rtype,
    }


def build_dingtalk(c, cfg):
    title = f"{c['emoji']} {c['label']}提醒 | {c['date_cn']}"

    parts = [
        f"### {c['emoji']} {c['label']}提醒",
        "",
        f"**{c['date_cn']}** · {c['time']}",
        "",
        "---",
        "",
        f"**⏰ 打卡截止**　{c['deadline_line']}",
    ]
    if c["weather_line"] != "—":
        parts += ["", f"**☁️ {c['city']}天气**　{c['weather_line']}"]
    if c["checklist_line"]:
        parts += ["", f"**🎒 出门清单**　{c['checklist_line']}"]

    if c["stats_line"]:
        parts += ["", "---", "", f"▸ {c['stats_line']}"]

    if c["quote"]:
        parts += ["", f"> {c['quote']}"]

    return title, "\n".join(parts)


def build_feishu(c, cfg):
    template = "blue" if c["rtype"] == "in" else "orange"
    title = f"{c['emoji']} {c['label']}提醒 | {c['date_cn']}"

    fields = [
        {"is_short": True, "text": {"tag": "lark_md", "content": f"**📅 日期**\n{c['date_cn']}"}},
        {"is_short": True, "text": {"tag": "lark_md", "content": f"**🕐 触发**\n{c['time']}"}},
        {"is_short": True, "text": {"tag": "lark_md", "content": f"**⏰ 打卡截止**\n{c['deadline_line']}"}},
    ]
    if c["weather_line"] != "—":
        fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**☁️ {c['city']}天气**\n{c['weather_line']}"}})

    elements = [{"tag": "div", "fields": fields}]

    if c["checklist_line"]:
        elements += [
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**🎒 出门清单**　{c['checklist_line']}"}},
        ]
    if c["stats_line"]:
        elements += [
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"▸ {c['stats_line']}"}},
        ]
    if c["quote"]:
        elements += [
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"<font color='grey'>{c['quote']}</font>"}},
        ]

    card = {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {"template": template, "title": {"tag": "plain_text", "content": title}},
        "elements": elements,
    }
    return title, card


# ────────────────────────── 日志 ──────────────────────────

def append_log(rtype, channels):
    log = load_json(LOG_FILE, {"history": []}) or {"history": []}
    log.setdefault("history", [])
    log["history"].append({
        "date": now_cn().strftime("%Y-%m-%d"),
        "type": rtype,
        "ts": now_cn().isoformat(timespec="seconds"),
        "channels": channels,
    })
    log["history"] = log["history"][-400:]
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ────────────────────────── 主流程 ──────────────────────────

def resolve_type(arg, now):
    if arg in ("in", "out"):
        return arg
    return "in" if now.hour < 12 else "out"


def main():
    ap = argparse.ArgumentParser(description="打卡提醒推送")
    ap.add_argument("type", nargs="?", default="auto", choices=["in", "out", "auto"])
    ap.add_argument("--dry-run", action="store_true", help="只打印不发送、不写日志")
    ap.add_argument("--force", action="store_true", help="忽略工作日判断")
    args = ap.parse_args()

    cfg = load_json(CONFIG_FILE) or {}
    now = now_cn()
    rtype = resolve_type(args.type, now)
    sc = (cfg.get("schedule") or {}).get(rtype) or {}

    print(f"🕐 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)")
    print(f"📌 提醒类型：{'上班' if rtype == 'in' else '下班'} ({rtype})")

    if not sc.get("enabled", True):
        print("⏭️ 该提醒已在 config.json 中关闭，跳过")
        return 0

    # 工作日判断
    opts = cfg.get("options", {})
    work, work_desc, src = get_workday_info(now, opts.get("skip_holidays", True))
    print(f"📅 工作日判定：{'是' if work else '否'} — {work_desc}（来源：{src}）")

    if not work and not args.force:
        print("🎉 今天不用上班，静默跳过（加 --force 可强制发送）")
        return 0

    # 迟到保护：避免定时器延迟导致「迟到的提醒」
    max_late = int(opts.get("max_late_minutes", 30))
    dl_h, dl_m = parse_hhmm(sc["deadline"])
    late_min = (now - now.replace(hour=dl_h, minute=dl_m, second=0, microsecond=0)).total_seconds() / 60
    if args.type == "auto" and late_min > max_late:
        print(f"⏰ 已超出打卡截止 {int(late_min)} 分钟（阈值 {max_late} 分钟），判定为迟到触发，跳过")
        return 0

    # 组装消息
    ctx = build_context(cfg, rtype, sc, now, work_desc)
    dt_title, dt_text = build_dingtalk(ctx, cfg)
    fs_title, fs_card = build_feishu(ctx, cfg)

    print("\n" + "─" * 46)
    print("📨 消息预览（钉钉 Markdown）")
    print("─" * 46)
    print(dt_text)
    print("─" * 46 + "\n")

    if args.dry_run:
        print("🧪 飞书卡片 JSON：")
        print(json.dumps(fs_card, ensure_ascii=False, indent=2)[:1200])
        print("\n🧪 dry-run 结束，未发送任何消息")

    # 发送
    sent = []
    ch = cfg.get("channels", {}) or {}

    dt = ch.get("dingtalk", {}) or {}
    if dt.get("enabled", True):
        wh = os.environ.get(dt.get("webhook_env", "DINGTALK_WEBHOOK"), "")
        sec = os.environ.get(dt.get("secret_env", "DINGTALK_SECRET"), "")
        if wh:
            print(f"📤 [钉钉] {dt_title}")
            if send_dingtalk(wh, sec, dt_title, dt_text, dry=args.dry_run) and not args.dry_run:
                sent.append("dingtalk")
        else:
            print(f"  ⚠️ 未配置环境变量 {dt.get('webhook_env')}，跳过钉钉")

    fs = ch.get("feishu", {}) or {}
    if fs.get("enabled", True):
        wh = os.environ.get(fs.get("webhook_env", "FEISHU_WEBHOOK"), "")
        sec = os.environ.get(fs.get("secret_env", "FEISHU_SECRET"), "")
        if wh:
            print(f"📤 [飞书] {fs_title}")
            if send_feishu(wh, sec, fs_card, dry=args.dry_run) and not args.dry_run:
                sent.append("feishu")
        else:
            print(f"  ⚠️ 未配置环境变量 {fs.get('webhook_env')}，跳过飞书")

    if sent:
        append_log(rtype, sent)
        print(f"📝 已记录日志：{', '.join(sent)}")
    elif not args.dry_run:
        print("⚠️ 没有任何通道成功发送")

    return 0


if __name__ == "__main__":
    sys.exit(main())
