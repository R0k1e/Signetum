# RepoSeal 仓库起步模板

[English](README.md)

这个仓库克隆后即可用于 Agent Team 开发。RepoSeal 把每一项需求连成可检查的闭环：
评审清单、规格、计划、实现、行为验收、批次组装，以及显式交付。

## 开始使用

1. 在 `docs/ARCHITECTURE.md` 中填写产品的真实架构。
2. 在 `changes/<change>/review.yaml` 中记录本次需求。
3. 规格经人工确认后再实现。
4. 运行 `just workspace-open <branch> <base>` 创建隔离工作树。

八个公开生命周期操作见
[`docs/development-lifecycle.md`](docs/development-lifecycle.md)。它们由仓库自带的标准库运行时执行；
克隆后不需要安装 RepoSeal 包，也不会带入 RepoSeal 的引擎源码和维护历史。

## 这个模板保证什么

- 需求必须进入 review → spec 的可检查关系，不能静默丢失。
- Agent 先理解仓库自己的架构和验证入口，减少用户反复检查。
- 多个 Agent 在独立 worktree 中并行开发，并以显式批次交付。
- 测试面向可观察行为，冻结批次只做一次完整验证。
- 每次交付都有证据说明具体交付了什么。

业务代码、技术框架和部署方式仍由你的项目自行决定。
