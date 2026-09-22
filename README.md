# tonia-checkin-reminder · 每日打卡提醒

每天固定时间通过 **钉钉 + 飞书** 推送上下班打卡提醒，自动跳过周末、法定节假日，自动识别调休补班日。

**零服务器、零成本** —— GitHub Actions 跑脚本，cron-job.org 做精确定时。

---

## 为什么需要 cron-job.org

GitHub Actions 自带 cron **不准时**，高负载时延迟 15～60 分钟。打卡提醒晚 10 分钟就失去意义，所以真正触发靠 cron-job.org（免费版支持分钟级精度），GitHub 原生 cron 只做兜底。

```
cron-job.org（08:45 / 17:45 精确触发）
        │  POST workflow_dispatch  { type: "in" | "out" }
        ▼
GitHub Actions（ubuntu-latest）
        │
        ├─ 1. 工作日判定（timor.tech 节假日接口，识别调休补班）
        ├─ 2. 迟到保护（超过截止 30 分钟的延迟触发直接丢弃）
        ├─ 3. 组装消息（天气 + 倒计时 + 出门清单 + 本月进度 + 随机文案）
        ├─ 4. 推送钉钉 Markdown + 飞书卡片
        └─ 5. 追加 data/reminder_log.json 并自动提交
```

---

## 目录结构

| 文件 | 说明 |
|------|------|
| `config.json` | **唯一需要改的配置**：提醒时间、截止时间、城市、通道开关 |
| `scripts/send_reminder.py` | 主脚本：判定 + 组装 + 推送 + 记日志 |
| `scripts/workday.py` | 工作日判断（timor.tech 节假日接口，自动降级） |
| `scripts/quotes.json` | 随机文案库（分上班 / 下班两组） |
| `.github/workflows/checkin-reminder.yml` | GitHub Actions 工作流 |
| `data/reminder_log.json` | 推送记录，自动维护 |
| `index.html` | 状态看板（GitHub Pages 可部署） |

---

## 一、配置 config.json

```json
{
  "schedule": {
    "in":  { "enabled": true, "time": "08:45", "deadline": "09:00", "label": "上班打卡" },
    "out": { "enabled": true, "time": "17:45", "deadline": "18:00", "label": "下班打卡" }
  }
}
```

- `time` —— 触发时间（用于写 cron-job.org，脚本本身不依赖它）
- `deadline` —— 打卡截止时间，用于算「还有 N 分钟」
- `enabled: false` 可单独关掉某一侧提醒
- `options.max_late_minutes` —— 迟到保护阈值，默认 30 分钟

---

## 二、获取两个机器人 Webhook

### 钉钉
1. 群设置 → 智能群助手 → 添加机器人 → **自定义**
2. 安全设置勾选 **加签**，复制 `SEC`
3. 复制 Webhook 地址

### 飞书
1. 群设置 → 群机器人 → 添加机器人 → **自定义机器人**
2. 安全设置勾选 **签名校验**，复制密钥
3. 复制 Webhook 地址

---

## 三、配置 GitHub Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret：

| Secret | 值 |
|--------|-----|
| `DINGTALK_WEBHOOK` | 钉钉 Webhook |
| `DINGTALK_SECRET` | 钉钉加签密钥 |
| `FEISHU_WEBHOOK` | 飞书 Webhook |
| `FEISHU_SECRET` | 飞书签名密钥 |

---

## 四、配置 cron-job.org

1. 注册 https://cron-job.org （免费）
2. 建两个任务：

**上班提醒**
- URL：`https://api.github.com/repos/<用户名>/tonia-checkin-reminder/actions/workflows/checkin-reminder.yml/dispatches`
- Method：`POST`
- Schedule：每天 `08:45`（时区选 Asia/Shanghai）
- Headers：
  ```
  Authorization: Bearer <GitHub PAT>
  Accept: application/vnd.github+json
  Content-Type: application/json
  ```
- Body：
  ```json
  {"ref":"main","inputs":{"type":"in"}}
  ```

**下班提醒**：同上，时间 `17:45`，Body 改为 `{"ref":"main","inputs":{"type":"out"}}`

> PAT 需勾选 `repo` + `workflow` 权限（classic PAT）。

---

## 五、本地测试

```bash
pip install requests

# 只打印消息，不发送（推荐先跑这个）
python scripts/send_reminder.py in --dry-run

# 忽略工作日判断，强制发送
python scripts/send_reminder.py out --force

# 正常发送（需先设置环境变量）
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=xxx"
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
python scripts/send_reminder.py auto
```

---

## 常见问题

**节假日接口挂了会怎样？**
自动降级为「周末判断」，提醒照常发，只是调休日可能判错。

**为什么 9:05 才收到上班提醒？**
说明是 GitHub 原生 cron 触发的（延迟）。检查 cron-job.org 任务是否正常，或看 GitHub Actions 日志确认触发来源。

**迟到保护会不会误杀？**
`--force` 可绕过。cron-job.org 精确触发时不会命中；只有 GitHub cron 严重延迟时才会被丢弃。

**推送失败怎么排查？**
GitHub Actions 日志里会明确打印 `❌ 钉钉推送失败：<原因>`，常见原因是加签密钥不匹配或关键词校验。
