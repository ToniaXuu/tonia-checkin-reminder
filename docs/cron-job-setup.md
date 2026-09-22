# cron-job.org 配置指南

本项目靠 cron-job.org 每 5 分钟叫醒一次 GitHub Actions，由脚本判断该不该发提醒。

> **为什么不用 GitHub 自带的 cron？**
> GitHub 原生 cron 高负载时延迟 15～60 分钟，且无法控制精度。cron-job.org 免费版准点率远高于它。

---

## 第 0 步：先准备一个 PAT

cron-job.org 需要调用 GitHub API 来触发工作流，必须带令牌。

打开 👉 https://github.com/settings/personal-access-tokens/new

| 项 | 填什么 |
|----|--------|
| Token name | `tonia-checkin-cron` |
| Expiration | 建议 90 天（到期重新生成即可） |
| Repository access | 选 **Only select repositories** → 勾 `tonia-checkin-reminder` |
| Permissions → Repository permissions | **Actions** → Read and write<br>**Contents** → Read and write<br>**Metadata** → Read-only（自动勾上） |

点 Generate token，**立刻复制**（只显示一次，形如 `github_pat_11ABC...`）。

> 这个 PAT 同时用于两处：cron-job.org 的 Authorization 头，以及本项目 `settings.html` 设置页保存配置。
> 别用 classic token（权限太粗），也别勾多余的权限。

---

## 第 1 步：注册 cron-job.org

打开 https://cron-job.org → 右上角 **Sign up** 注册（免费，只需邮箱）。

---

## 第 2 步：创建任务

登录后进入控制台，点 **Create cronjob**，按下表填写：

### 基本信息

| 字段 | 值 |
|------|-----|
| **Title** | `打卡提醒轮询` |
| **URL** | `https://api.github.com/repos/ToniaXuu/tonia-checkin-reminder/actions/workflows/checkin-reminder.yml/dispatches` |
| **Execution schedule** | 切到 **Minutes** 标签，选 **Every 5 minutes** |

> URL 里的仓库名如果改过，记得同步。

### 请求设置（展开 Advanced 或 Request settings）

| 字段 | 值 |
|------|-----|
| **Request method** | `POST` |

**Headers** —— 点 Add header，加三条：

| Key | Value |
|-----|-------|
| `Authorization` | `Bearer github_pat_11ABC...`（换成你自己的 PAT） |
| `Accept` | `application/vnd.github+json` |
| `Content-Type` | `application/json` |

**Request body**：

```json
{"ref":"main","inputs":{}}
```

> 不带参数是故意的 —— 脚本自己判断该发哪条提醒。
> 想手动强制发某一条时，把 body 改成 `{"ref":"main","inputs":{"id":"dt-1705","force":true}}`。

---

## 第 3 步：保存并测试

1. 点 **Save**
2. 在任务列表里找到它，点 **TEST RUN**（或那个 ▶ 图标）
3. **期望结果：HTTP 204**

如果返回 204，去 GitHub 仓库的 **Actions** 页面，应该能看到一次新运行。

---

## 第 4 步：确认闭环

Actions 运行日志里会打印类似：

```
🕐 当前时间：2026-09-22 15:12:03 (UTC+8)
⏭️ 当前没有提醒命中时间窗口（容差 10 分钟），退出
```

这是**正常的** —— 一天 288 次轮询里，绝大多数都会停在这一步。
只有落到 17:05 / 17:20 / 17:40 这类时间点附近时，才会看到 `🎯 命中` 并真正推送。

---

## 常见错误对照

| HTTP | 原因 | 处理 |
|------|------|------|
| `204` | 成功 | 无 |
| `401` | PAT 无效或已过期 | 重新生成 PAT，更新 Header |
| `403` | PAT 权限不足 | 补上 **Actions: Read and write** |
| `404` | 仓库名或工作流文件名写错 | 确认是 `checkin-reminder.yml` |
| `422` | body 不是合法 JSON | 检查引号是否为英文半角 |
| `204` 但 Actions 没运行 | 分支名不对 | body 里的 `ref` 要与实际分支一致（`main`） |

---

## 时区说明

cron-job.org 的调度是**固定间隔**（每 5 分钟一次），不涉及时区。真正的时间判断发生在 GitHub Actions 里，脚本统一按 **UTC+8（北京时间）** 计算。

所以：改提醒时间只需要改 `config.json`（或用 `settings.html`），**不用碰 cron-job.org**。
