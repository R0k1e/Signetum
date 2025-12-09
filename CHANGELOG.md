# Changelog

本文档记录项目的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 待添加
- 新功能、修复、变更等将在发布时添加到这里

## 格式说明

每个版本条目应包含以下部分（根据需要选择）：

- **Added** - 新功能
- **Changed** - 对现有功能的变更
- **Deprecated** - 即将移除的功能
- **Removed** - 已移除的功能
- **Fixed** -  bug 修复
- **Security** - 安全相关的修复

## 示例

```markdown
## [v1.0.0] - 2024-01-01

### Added
- 添加了 XXX 功能
- 新增 YYY 支持

### Changed
- 改进了 ZZZ 性能

### Fixed
- 修复了 ABC 问题
```

## 使用说明

1. **发布新版本时**，在文件顶部添加新的版本条目
2. **版本号格式**：使用 `[v1.0.0]` 或 `[1.0.0]` 格式
3. **日期格式**：使用 `YYYY-MM-DD` 格式
4. **保持更新**：在开发过程中，可以将变更添加到 `[未发布]` 部分

## 发布流程

1. 更新本文件，添加新版本条目
2. 提交更改：`git add CHANGELOG.md && git commit -m "chore: 更新 CHANGELOG"`
3. 创建带注释的 tag：`git tag -a v1.0.0 -m "发布 v1.0.0"`
4. 推送 tag：`git push origin v1.0.0`
5. CD 工作流将自动构建并发布到 PyPI 和 GitHub Releases

**注意**：如果未在 CHANGELOG.md 中添加版本条目，也可以直接在创建 tag 时添加注释作为发布说明。

