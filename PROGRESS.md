# PROGRESS

## 当前任务目标
回滚“硬性多信源门槛”导致页面只剩一条热点的问题，恢复可用热点数量，同时继续过滤早报、合集、正文观点句等不适合直接作为热点主题的内容。

## 已完成事项
- 已移除采集脚本里的 `MIN_MEDIA_CHANNELS = 2` 硬门槛。
- 已将 GitHub Actions 质量门槛从至少 1 条恢复为至少 3 条。
- 已恢复 2026-07-23 的页面数据候选池，并过滤 `AI早报`、`8点1氪`、观点句标题。
- 当前页面数据恢复为 13 条热点。
- 已为两条采集路径加入正文观点句标题过滤规则。

## 正在处理的文件
- `.github/workflows/collect-hotspots.yml`
- `automation/collect_business_hotspots.py`
- `automation/collect_free_news.py`
- `insights/hotspots-data.js`
- `PROGRESS.md`
- `TODO.md`

## 已做出的关键决策
- 单信源报道不再作为硬性排除条件。
- 多信源报道应作为置信度和排序加分信号，后续再完善。
- 早报、合集、正文观点句继续过滤，避免把多个主题混成一条热点。

## 尚未完成事项
- 需要提交本轮改动。
- 需要通过 GitHub API 发布到线上页面。
- 后续需要重构聚类逻辑，让同一主题自动汇总多家媒体报道。

## 下一步最小可执行动作
提交本轮改动并通过 `gh api` 更新 GitHub 仓库文件。

## 当前是否有未提交改动
有。

## 如何验证当前结果
- `python3 -m py_compile automation/collect_free_news.py automation/collect_business_hotspots.py`
- 检查 `insights/hotspots-data.js` 中热点数量为 13。
- 检查页面中无 `AI早报`、`8点1氪`、`36氪早报` 等合集标题。
