# 法考刷题网站（飞书 + GitHub Pages + Cloudflare）

这个项目把飞书多维表格当作题库后台，通过 GitHub Actions 自动生成静态刷题网站，并部署到 GitHub Pages。可选搭配 Cloudflare 自定义域名和 CDN 加速。

## 项目结构

```
.
├── .github/workflows/build.yml   # GitHub Actions 自动构建
├── build.py                      # 构建脚本：从飞书/本地生成 HTML
├── template.html                 # 单套试卷页面模板
├── requirements.txt              # Python 依赖
├── docs/                         # GitHub Pages 发布目录
│   ├── index.html                # 首页
│   └── quiz/                     # 各套试卷页面
└── *_quiz.json                   # 本地 JSON 题库（作为飞书不可用时的 fallback）
```

## 方案概述

1. **飞书多维表格**：存放试卷信息和具体题目。
2. **GitHub Actions**：定时调用飞书 API 拉取数据，生成 HTML 页面并推回仓库。
3. **GitHub Pages**：从 `docs/` 目录发布网站。
4. **Cloudflare**（可选）：绑定自定义域名并开启 CDN。

## 第一步：准备飞书多维表格

### 1. 创建试卷表

在飞书多维表格里创建一张表，建议命名为 `quizzes`，包含以下字段：

| 字段名 | 字段类型 | 说明 |
|--------|----------|------|
| quiz_id | 文本 | 唯一标识，例如 `minfa-1-100` |
| title | 文本 | 页面标题，例如 `民法真金题 1-100` |
| source | 文本 | 来源说明（可选） |
| slug | 文本 | 输出文件名，例如 `minfa-1-100`（留空则使用 quiz_id） |
| enabled | 复选框 | 是否启用 |

### 2. 创建题目表

再创建一张表，建议命名为 `questions`，包含以下字段：

| 字段名 | 字段类型 | 说明 |
|--------|----------|------|
| quiz_id | 文本 | 对应试卷表的 quiz_id |
| id | 数字 | 题号 |
| type | 文本 | 题型：`single_choice`（单选）、`multi_choice`（多选）、`true_false`（判断）、`fill_blank`（填空） |
| stem | 文本 | 题干 |
| options | 文本 | 选项，每行一个，例如：<br>`A. 自愿原则`<br>`B. 公平原则` |
| answer | 文本 | 正确答案，例如 `D` |
| explanation | 文本 | 解析 |

> 提示：`options` 字段也可以拆成 `option_A`、`option_B`、`option_C` 等多个独立字段；脚本会优先读取这些独立字段。

### 3. 获取多维表格链接

打开你的多维表格，复制浏览器地址栏里的 URL，类似：

```
https://xxx.feishu.cn/base/XXXXXXXXX?table=YYYYYYY&view=ZZZZZZZ
```

- `XXXXXXXXX` 就是 **App Token**（`FEISHU_APP_TOKEN`）。
- `YYYYYYY` 就是表的 **Table ID**（分别对应 `FEISHU_QUIZ_TABLE` 和 `FEISHU_QUEST_TABLE`）。

如果 URL 里没有 `table=` 参数，可以点击表头右侧的「...」→「复制表 ID」。

## 第二步：创建飞书应用并授权

1. 打开 [飞书开放平台](https://open.feishu.cn/)。
2. 点击「开发者后台」→「创建企业自建应用」。
3. 填写应用名称，例如「刷题网站同步」。
4. 进入应用详情页：
   - 在「凭证与基础信息」里复制 **App ID** 和 **App Secret**。
   - 在「权限管理」里添加以下权限：
     - `bitable:app:readonly`（读取多维表格）
     - `bitable:app`（如果需要写入，本项目只读）
5. 进入你的多维表格 → 右上角「...」→「添加应用」→ 选择刚才创建的应用 → 授权。

## 第三步：创建 GitHub 仓库并上传代码

1. 在 GitHub 新建一个 Public 仓库，例如 `fakao-quiz`。
2. 把本项目所有文件 push 到仓库：

```bash
git init
git remote add origin https://github.com/你的用户名/fakao-quiz.git
git add .
git commit -m "init quiz site"
git push -u origin main
```

## 第四步：配置 GitHub Secrets

1. 进入 GitHub 仓库 → Settings → Secrets and variables → Actions。
2. 点击「New repository secret」，添加以下 secrets：

| Secret 名称 | 值 |
|-------------|-----|
| `FEISHU_APP_ID` | 飞书应用的 App ID |
| `FEISHU_APP_SECRET` | 飞书应用的 App Secret |
| `FEISHU_APP_TOKEN` | 多维表格的 App Token |
| `FEISHU_QUIZ_TABLE` | 试卷表的 Table ID |
| `FEISHU_QUEST_TABLE` | 题目表的 Table ID |

## 第五步：开启 GitHub Pages

1. 进入仓库 → Settings → Pages。
2. Source 选择「Deploy from a branch」。
3. Branch 选择 `main`，文件夹选择 `/docs`。
4. 保存后等待 1-2 分钟，访问 `https://你的用户名.github.io/fakao-quiz/`。

## 第六步：触发首次构建

1. 进入仓库 → Actions → 选择「Build and Deploy Quiz Site」工作流。
2. 点击「Run workflow」→「Run workflow」手动触发。
3. 等待构建完成，刷新 Pages 页面即可看到最新试卷。

构建任务默认每天 UTC 02:00（北京时间 10:00）自动运行一次，也会在有 push 到 `main` 分支时自动运行。

## 第七步：Cloudflare 自定义域名（可选）

1. 登录 [Cloudflare](https://dash.cloudflare.com/)。
2. 添加你的域名，按提示修改 DNS 服务器。
3. 在 DNS 记录里添加一条 CNAME：
   - Name: `quiz`（或你想要的子域名）
   - Target: `你的用户名.github.io`
4. 在 GitHub Pages 的 Custom domain 里填入 `quiz.你的域名.com`。
5. 勾选 Enforce HTTPS。
6. Cloudflare 的 SSL/TLS 加密模式建议选「Full (strict)」。

完成后即可通过 `https://quiz.你的域名.com` 访问。

## 本地测试

如果你暂时不想接飞书，可以直接用本地 JSON 运行：

```bash
pip install -r requirements.txt
python build.py
```

脚本会自动从当前目录下的 `*_quiz.json` 文件生成 `docs/` 目录。

## 常见问题

### Q: 飞书 API 返回权限错误？
A: 请确认：
- 应用已经添加到多维表格并授权。
- 应用的权限里包含 `bitable:app:readonly`。
- Secret 里的 App Token 和 Table ID 没有复制错。

### Q: 构建成功但 Pages 没更新？
A: GitHub Pages 部署可能有 1-2 分钟延迟。可以在仓库的 Actions 里查看 Pages 部署状态。

### Q: 想增加新的试卷？
A: 在飞书试卷表添加一行，在题目表添加对应 `quiz_id` 的题目，下次构建时就会自动生成新页面。

### Q: 想改页面样式？
A: 修改 `template.html` 里的 CSS，然后 push 到 main 分支即可触发重新构建。
