# Git 工作流

这个仓库是“小胡聊商业热点页面”的线上发布源，GitHub Pages 从 `main` 分支根目录发布。

## 本地工作目录

后续迭代请优先在这个目录修改：

```bash
/Users/silin/Documents/自动化任务/小胡聊商业/xiaohu-business-hotspots
```

旧的外层目录和 `site/` 目录只作为历史工作区保留，避免继续从旧目录手动覆盖线上文件。

## 每次改动流程

```bash
git status --short --branch
git pull --ff-only

# 修改文件并做最小验证
git diff --check
git status --short
git add <changed-files>
git commit -m "清楚描述本次变更"
git push
```

如果本机 GitHub HTTPS 继续出现 HTTP2 或连接问题，可以先保留本地 commit，再用 GitHub CLI/API 发布同一批文件；发布后要确认远端 commit，并同步更新本地基线。

## 数据文件规则

- `insights/hotspots-data.js` 主要由 GitHub Actions 自动采集后更新。
- 页面样式、脚本或视频源改动时，不要用旧的本地 `hotspots-data.js` 覆盖线上最新数据。
- 如果必须手动改 `hotspots-data.js`，先确认线上当前采集时间，再提交。

## 发布验证

```bash
gh run list --workflow collect-hotspots.yml --limit 5
gh api repos/tomorrow140/xiaohu-business-hotspots/pages --jq '{status:.status, html_url:.html_url}'
```

线上地址：

```text
https://tomorrow140.github.io/xiaohu-business-hotspots/
```
