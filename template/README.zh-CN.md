# RepoSeal

[English](README.md)

**让每一次 Agent 改动都可追踪、可验证、可并行，并且说得清交付了什么。**

RepoSeal 是语言无关的仓库开发基座，默认提供开箱即用的 Python 配置。它把编码
Agent 周围的开发流程变成仓库自己的系统，使交付不再依赖聊天记录，也不依赖某个
Agent 记得之前发生过什么。

它防止需求静默丢失、Agent 让用户重新解释仓库、并行工作覆盖交付分支、每个成员
重复跑整套测试，以及最后只有绿色提交却说不清交付内容。

## 开发流程

```text
Review → Specification → Plan → 隔离 worktree
       → 成员 ready → 命名批次 → 冻结后的最终验证
       → 显式交付 → 人工验收或重新打开
```

RepoSeal 把需求记录为稳定 Clause，对照计划影响与真实 Git diff，选择具名验证门禁，
隔离并行工作，只验证一个冻结批次，并把交付绑定到精确 Git 身份。

## 多语言 Profile

生命周期本身不理解产品使用什么语言。Profile 负责提供带命名空间的工具、影响规则、
门禁和测试分片。一个仓库可以启用一个 Profile，也可以组合多个：

```toml
[profiles]
enabled = ["python-default@1", "typescript-local@1"]
```

模板默认启用 `python-default@1`，其中包含 uv、Ruff、ty、单元测试、集成测试、依赖
审计和凭据检查。你可以替换它，也可以增加 TypeScript、Rust 或仓库自有 Profile，
而不需要修改八个生命周期操作。

## 机器保证什么

- 每项需求都有合法处置和 Specification owner；
- deferred 工作指向真实且已批准的 Specification；
- Plan 覆盖每个归属 Clause；
- 实际改动能解析到可解释的 Profile、Gate 和 Shard；
- 收据绑定代码、配置、锁文件、工具和实际执行的检查；
- 只有显式点名且 ready 的 worktree 才能进入交付批次；
- 并行决策提案只在批次中领取正式 ADP 编号；
- 交付和人工验收始终是两个不同事实。

RepoSeal 保证需求账目和执行边界。产品架构、行为契约以及测试是否充分，仍由你的
仓库负责。

## 开始使用

1. 使用 GitHub 的 **Use this template** 创建仓库。
2. 运行 `mise install`。
3. 在 `docs/ARCHITECTURE.md` 中填写产品的真实架构。
4. 运行 `just change-open <短横线名称>`，再填写生成的 Review。
5. 人工确认 Specification 后，运行 `just workspace-open <branch> <base>` 开始隔离实现。

进一步阅读 [`docs/development-lifecycle.md`](docs/development-lifecycle.md)、
[`docs/agent-team-delivery.md`](docs/agent-team-delivery.md) 和
[`docs/customizing.md`](docs/customizing.md)。

RepoSeal 不是 Agent runtime、编码模型、托管 CI 服务或 Specification 生成器。复制后
的运行时归仓库自己所有，也不会安装 RepoSeal 包。当前模板版本：`v0.2.0`。
