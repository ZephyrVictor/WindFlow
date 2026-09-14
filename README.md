# flow — 多 agent CLI 编排系统

以 claude/codex CLI 为后端 agent 的轻量编排系统：YAML 声明 DAG，tmux 承载，全程可 attach 干预，markdown 共享记忆。

## 安装与启用

```bash
pip install -e .            # flow CLI
cp -r skills/flow ~/.claude/skills/   # 让任意 claude 会话学会编排 flow（agent 自编排，ADR-0007）
```

装好 skill 后，在任意 claude 会话里说"帮我编排一个 XX 流水线"，agent 会自主走 init → agent new → 写 yaml → validate → run。

开始开发前，请先阅读 [`.codex/agent.md`](./.codex/agent.md) 和 [`docs/README.md`](./docs/README.md)。项目架构、开发计划、决策和讨论记录统一维护在 [`docs/`](./docs/) 目录中。
