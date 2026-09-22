# tonia-checkin-reminder · 每日打卡提醒

每天固定时间通过 **钉钉 + 飞书** 推送上下班打卡提醒，自动跳过周末与法定节假日，自动识别调休补班日。

**时间可以在网页上改，改完立即生效。**

零服务器、零成本 —— GitHub Actions 跑脚本，cron-job.org 提供分钟级轮询。

---

## 为什么是「轮询」而不是「定时触发」

第一版是「cron-job.org 在 08:45 精确触发」。问题是：**改 config.json 里的时间不会改变 cron-job.org 的触发时刻**，网页上改时间就变成摆设。

所以改成轮询：

```
cron-job.org 每 5 分钟 ping 一次
        │  POST workflow_dispatch（不指定 in/out，交给脚本判断）
        ▼
GitHub Actions
        │
        ├─ 时间窗口判定   当前时间落在 [设定时间, 设定时间+容差] 内才继续
        │                 否则秒退（一天 288 次轮询，绝大多数在这里退出）
        ├─ 当日去重       同一类型当天已推过 → 跳过（轮询不会重复轰炸）
        ├─ 工作日判定     timor.tech 节假日接口，含调休补班
        ├─ 消息组装       天气 + 倒计时 + 出门清单 + 本月进度 + 随机文案
        ├─ 双通道推送     钉钉 Markdown ＋ 飞书交互卡片
        └─ 日志回写       data/reminder_log.json（顺带完成去重凭据）
```

**代价**：提醒会比设定时间晚 0～5 分钟送达（取决于轮询间隔）。
**收益**：网页改时间立即生效，不用碰定时器。

---

## 一、改时间：两种方式

### 方式 A · 网页设置（推荐）

打开 `settings.html`（部署后是 `https://<用户名>.github.io/tonia-checkin-reminder/settings.html`）：

1. 填 GitHub 用户名、仓库名、分支、访问令牌 → 点「连接并加载」
2. 改时间 / 开关 / 城市 / 清单
3. 点「保存到 GitHub」—— 会以 commit 形式提交 `config.json`，下一轮轮询生效

**关于令牌**：保存配置要向仓库写文件，必须用你自己的 PAT。令牌只存在浏览器 localStorage，不上传第三方。建议在 [GitHub → Fine-grained tokens](https://github.com/settings/personal-access-tokens/new) 新建，只授予本仓库的：

- `Contents: Read and write`（读写 config.json）
- `Actions: Read and write`（用于「测试提醒」按钮手动触发工作流）

并设置较短有效期。

### 方式 B · 直接改文件

改完 `config.json` 直接 push，效果完全一样。

```json
{
  "schedule": {
    "in":  { "enabled": true, "time": "08:45", "deadline": "09:00" },
    "out": { "enabled": true, "time": "17:45", "deadline": "18:00" }
  },
  "options": { "tolerance_minutes": 10 }
}
```

- `time` —— 提醒时间
- `deadline` —— 打卡截止，用于算「还有 N 分钟」
- `tolerance_minutes` —— 时间容差。轮询间隔 5 分钟时保持 10 即可；间隔调大则同步调大

---

## 二、部署

### 1. 获取两个机器人 Webhook

**钉钉**：群设置 → 智能群助手 → 添加机器人 → 自定义 → 安全设置勾选**加签** → 复制 Webhook 和 `SEC`

**飞书**：群设置 → 群机器人 → 添加机器人 → 自定义机器人 → 安全设置勾选**签名校验** → 复制 Webhook 和密钥

### 2. 配置 GitHub Secrets

仓库 → Settings → Secrets and variables → Actions：

| Secret | 值 |
|--------|-----|
| `DINGTALK_WEBHOOK` | 钉钉 Webhook |
| `DINGTALK_SECRET` | 钉钉加签密钥 |
| `FEISHU_WEBHOOK` | 飞书 Webhook |
| `FEISHU_SECRET` | 飞书签名密钥 |

### 3. 配置 cron-job.org

注册 https://cron-job.org （免费）→ 新建任务：

- **URL**：`https://api.github.com/repos/<用户名>/tonia-checkin-reminder/actions/workflows/checkin-reminder.yml/dispatches`
- **Method**：`POST`
- **Schedule**：每 **5 分钟**（Every 5 minutes）
- **Headers**：
  ```
  Authorization: Bearer <GitHub PAT>
  Accept: application/vnd.github+json
  Content-Type: application/json
  ```
- **Body**：
  ```json
  {"ref":"main","inputs":{"type":"auto"}}
  ```

一条任务管两个提醒 —— `auto` 模式下由脚本判断该发上班还是下班。

> PAT 需 `repo` + `workflow` 权限（classic），或 fine-grained 的 `Contents: Read and write` + `Actions: Read and write`。

### 4. 启用 GitHub Pages

Settings → Pages → Source 选 `main` 分支根目录，即可访问看板与设置页。

---

## 目录结构

| 文件 | 说明 |
|------|------|
| `settings.html` | **网页设置页**，图形化改时间并提交到仓库 |
| `index.html` | 状态看板：提醒计划、本月统计、推送记录 |
| `config.json` | 配置文件（网页保存的就是它） |
| `scripts/send_reminder.py` | 主脚本：窗口判定 + 去重 + 组装 + 推送 + 记日志 |
| `scripts/workday.py` | 工作日判断（含年度节假日缓存） |
| `scripts/quotes.json` | 随机文案库 |
| `.github/workflows/checkin-reminder.yml` | Actions 工作流 |
| `data/reminder_log.json` | 推送记录（自动维护，兼作去重凭据） |
| `data/holiday_<年>.json` | 节假日表缓存（自动生成） |

---

## 本地测试

```bash
pip install requests

# 看脚本此刻会不会发（轮询模式下最常用）
python scripts/send_reminder.py auto --dry-run

# 强制补发某次提醒（忽略窗口与去重）
python scripts/send_reminder.py in --force

# 真实发送（需先设置环境变量）
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=xxx"
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
python scripts/send_reminder.py in
```

---

## 常见问题

**为什么提醒比设定时间晚了几分钟？**
轮询间隔决定的。cron-job.org 每 5 分钟触发一次，命中窗口那一刻才发。想更准就把间隔调成 1～2 分钟。

**会不会收到重复提醒？**
不会。`data/reminder_log.json` 记录当天已推送的类型，重复命中窗口会被跳过。

**手动触发工作流时怎么发？**
Actions 页 → Run workflow → `type` 选 `in` 或 `out`、勾选 `force`。或者用设置页的「测试上班提醒 / 测试下班提醒」按钮。

**节假日接口挂了会怎样？**
自动降级为「周末判断」，提醒照常发，只是调休日可能判错。

**网页保存失败怎么办？**
检查 PAT 是否有本仓库的 `Contents: Read and write` 权限，以及分支名是否填对。报错信息会直接显示在页面顶部。
