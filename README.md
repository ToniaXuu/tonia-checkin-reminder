# tonia-checkin-reminder · 打卡提醒

按你设定的多个时间点，通过 **钉钉 / 飞书** 推送打卡提醒。每条提醒有独立的时间、通道和文案，自动跳过周末与法定节假日。

**时间与文案都能在网页上改，改完立即生效。**

零服务器、零成本 —— GitHub Actions 跑脚本，cron-job.org 提供分钟级轮询。

---

## 当前配置

| 提醒 ID | 时间 | 通道 | 文案 |
|---------|------|------|------|
| `dt-1705` | 17:05 | 钉钉 | 五点零五了，顺手把卡打了吧，别留到最后一刻。 |
| `dt-1720` | 17:20 | 钉钉 | 提醒一下，还没打卡的话现在就去。 |
| `dt-1740` | 17:40 | 钉钉 | 最后一次提醒 —— 今天要是还没打卡，现在就补。 |
| `fs-1715` | 17:15 | 飞书 | 该打卡了，别忘了。 |
| `fs-1730` | 17:30 | 飞书 | 再提醒一次，记得打卡。 |
| `fs-1800` | 18:00 | 飞书 | 六点了，最后确认一下有没有打卡。 |

飞书三条已配置好但**待接入** —— 配好 `FEISHU_WEBHOOK` / `FEISHU_SECRET` 两个 Secret 即自动生效，不用改配置。

---

## 为什么是「轮询」而不是「定时触发」

如果让 cron-job.org 在 17:05 精确触发，那么**改 config.json 里的时间不会改变触发时刻** —— 网页上改时间就成了摆设。

所以驱动方式反过来：

```
cron-job.org 每 5 分钟 ping 一次
        │  POST workflow_dispatch（不带参数，交给脚本自己判断）
        ▼
GitHub Actions
        │
        ├─ 时间窗口判定   当前时间落在某条提醒的 [设定时间, +容差] 内才继续
        │                 否则秒退（一天 288 次轮询，绝大多数在这里退出）
        ├─ 当日去重       按提醒 ID 去重，同一条当天最多推一次
        ├─ 工作日判定     timor.tech 节假日接口，含调休补班
        ├─ 消息组装       自定义文案 + 可选天气 / 月度进度
        ├─ 通道分发       按每条提醒自己的 channels 发往钉钉 / 飞书
        └─ 日志回写       data/reminder_log.json
```

**代价**：提醒会比设定时间晚 0～5 分钟送达。
**收益**：网页改时间立即生效，不用碰定时器。

---

## 一、改提醒：两种方式

### 方式 A · 网页设置（推荐）

打开 `settings.html`：

1. 填 GitHub 用户名、仓库名、分支、访问令牌 → 「连接并加载」
2. 增删提醒、改时间、切通道（钉钉/飞书可同时选）、改文案
3. 「保存到 GitHub」→ 提交 `config.json`，下一轮轮询生效

每条提醒卡片上有「测试」按钮，可立即触发一次真实推送。

**关于令牌**：保存配置要向仓库写文件，必须用你自己的 PAT。令牌只存在浏览器 localStorage，不上传第三方。建议在 [GitHub → Fine-grained tokens](https://github.com/settings/personal-access-tokens/new) 新建，只授予**本仓库**的：

- `Contents: Read and write`
- `Actions: Read and write`

并设置较短有效期。

### 方式 B · 直接改 config.json

```json
{
  "reminders": [
    {
      "id": "dt-1705",
      "enabled": true,
      "channels": ["dingtalk"],
      "time": "17:05",
      "label": "下班打卡",
      "emoji": "🕔",
      "message": "五点零五了，顺手把卡打了吧。"
    }
  ],
  "options": { "tolerance_minutes": 10 }
}
```

| 字段 | 说明 |
|------|------|
| `id` | 唯一标识，**用于当日去重**。改 ID 会导致当天可能重复推送，非必要别改 |
| `enabled` | 单条开关，`false` 时跳过 |
| `channels` | `["dingtalk"]` / `["feishu"]` / 两者都要 |
| `time` | 提醒时间，`HH:MM` |
| `label` / `emoji` | 标题与图标 |
| `message` | 提示文案，留空则只显示标题+时间（或按 `include_quote` 用随机句） |

---

## 二、部署

### 1. 机器人 Webhook

**钉钉**：群设置 → 智能群助手 → 添加机器人 → 自定义 → 安全设置勾选**加签** → 复制 Webhook 和 `SEC` 开头密钥

**飞书**：群设置 → 群机器人 → 添加机器人 → 自定义机器人 → 安全设置勾选**签名校验** → 复制 Webhook 和密钥

### 2. GitHub Secrets

仓库 → Settings → Secrets and variables → Actions：

| Secret | 状态 |
|--------|------|
| `DINGTALK_WEBHOOK` | 必填 |
| `DINGTALK_SECRET` | 必填（加签模式） |
| `FEISHU_WEBHOOK` | 接入飞书时填 |
| `FEISHU_SECRET` | 接入飞书时填 |

### 3. cron-job.org

> 需要逐步操作 + 错误对照表？见 [`docs/cron-job-setup.md`](docs/cron-job-setup.md)。

注册 https://cron-job.org （免费）→ 新建任务：

- **URL**：`https://api.github.com/repos/<用户名>/tonia-checkin-reminder/actions/workflows/checkin-reminder.yml/dispatches`
- **Method**：`POST`
- **Schedule**：每 **5 分钟**
- **Headers**：
  ```
  Authorization: Bearer <GitHub PAT>
  Accept: application/vnd.github+json
  Content-Type: application/json
  ```
- **Body**：
  ```json
  {"ref":"main","inputs":{}}
  ```

一条任务管所有提醒 —— 脚本自己判断该发哪条。

### 4. GitHub Pages

Settings → Pages → Source 选 `main` 分支根目录，即可访问看板与设置页。

---

## 目录结构

| 文件 | 说明 |
|------|------|
| `settings.html` | 网页设置页：提醒列表编辑器 |
| `index.html` | 状态看板：提醒列表、本月统计、推送记录 |
| `config.json` | 配置文件（网页保存的就是它） |
| `scripts/send_reminder.py` | 主脚本：窗口判定 + 去重 + 组装 + 分发 + 记日志 |
| `scripts/workday.py` | 工作日判断（含年度节假日缓存） |
| `scripts/quotes.json` | 随机文案库（仅在文案留空且开启选项时使用） |
| `.github/workflows/checkin-reminder.yml` | Actions 工作流 |
| `data/reminder_log.json` | 推送记录（兼作去重凭据） |
| `data/holiday_<年>.json` | 节假日表缓存（自动生成） |

---

## 本地测试

```bash
pip install requests

# 看有哪些提醒、哪条正在窗口内
python scripts/send_reminder.py --list

# 模拟一次轮询（当前时间不在窗口内就会退出）
python scripts/send_reminder.py

# 看某条提醒的消息长什么样（不发送）
python scripts/send_reminder.py --id dt-1705 --dry-run

# 真的发一条（忽略窗口与去重）
python scripts/send_reminder.py --id dt-1705 --force

# 不带 --id 时需先设置环境变量才会真正发送
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=xxx"
export DINGTALK_SECRET="SECxxxx"
python scripts/send_reminder.py
```

---

## 常见问题

**为什么提醒比设定时间晚了几分钟？**
轮询间隔决定的。cron-job.org 每 5 分钟触发一次，命中窗口那一刻才发。想更准就把间隔调成 1～2 分钟。

**会不会收到重复提醒？**
不会。`reminder_log.json` 按提醒 ID 记录当天已推送过的条目，重复命中窗口会被跳过。

**17:05 和 17:15 两条提醒会串吗？**
不会。容差 10 分钟时窗口边界恰好相接，但去重保证了 17:05 那条在 17:05 那轮就发掉，17:15 那轮不会重复。

**想临时加一条怎么办？**
设置页点「+ 添加提醒」，改完保存。或者手动往 `config.json` 的 `reminders` 数组里加一项。

**怎么手动触发某一条？**
Actions 页 → Run workflow → `id` 填提醒 ID（如 `dt-1705`）、勾选 `force`。或用设置页每条卡片上的「测试」按钮。

**节假日接口挂了会怎样？**
自动降级为「周末判断」，提醒照常发，只是调休日可能判错。

**手动改了 `id` 会怎样？**
去重是按 ID 匹配的，改 ID 后当天可能再推一次。除了这个副作用没有别的影响。
