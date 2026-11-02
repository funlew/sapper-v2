---
name: sapper-setup
description: 将**当前项目**选择性接入 sapper 作战图（事实图在进攻侧的专门化）工作记忆。创建本地 `.sapper/` 图，在本项目的 `.claude/settings.json` 中注册 SessionStart + UserPromptSubmit 钩子（非全局——其他项目不受影响），并写入 AGENTS.md，教授带类型的事实（host/service/cred/vuln/loot/flag）、flag 账本（sapper flag）与 arena 桥（sapper arena）。启用后，本项目每一轮都会自动注入当前图状态与当前日期输出，让 Claude 始终知道哪些已确认、哪些已尝试，以及现在几点；子 agent（sapper dispatch）可以读写同一张图。多智能体 tmux 协作时，先用 `sapper peers --discover` 列出 pane，并在授权任何目标之前询问用户哪些 pane / AI 对端允许通信。当用户说 "enable sapper here"、"在这个项目用 sapper"、"setup the engagement graph"，或开始一个需要追踪、可恢复的渗透交战 / CTF 挑战 / 多步调试、研究、审计战役时使用。比赛场景请接着执行 `sapper arena init` 并设置 SAPPER_ARENA_TOKEN。这就是 install.sh 以斜杠命令形式暴露的、按项目初始化的组件。
license: MIT
---

# sapper-setup

**sapper 作战图**（工作记忆）的项目级初始化器。
它就是这个选择性启用的开关：在某个项目里运行它之前，sapper 在该项目里什么都不做；运行之后，那一个项目每轮都会自动读取并自动维护自己的图。

零服务 —— 它只是丢下一个本地 `.sapper/`，并把两条钩子条目写进**本项目的** `.claude/settings.json`。用于渗透交战时，配合 `sapper arena init`（比赛平台配置）使用，并把发现记为带类型的事实（`-k host/service/cred/vuln/loot/flag`）。

## 它做什么

在目标项目目录内运行。只做三件事，全部是本地操作：

1. **建图**：在 `./.sapper/`（若尚不存在）创建 `project.json`、`facts/goal.json`，以及 `intents/`、`hints/` 目录。
2. **注册钩子**：在 `./.claude/settings.json` 中注册 `SessionStart` 与 `UserPromptSubmit`，两者都指向 `sapper-hook.py`。它们把当前图状态与 `date` 输出注入每一轮，让模型始终知道前沿与本机当前时间。这是**项目级**设置文件；用户级 `~/.claude/settings.json` 以及其他所有项目完全不受影响。
3. **（可选）写入 `AGENTS.md`**，让被派发的子 agent 学会事实图协议（`sapper fact`、`sapper done` 等）。

无守护进程、无端口、无数据库。`rm -rf .sapper .claude` 即可全部撤销。

## 如何运行

在 shell 中执行（先运行过 `bash install.sh`）：

```bash
cd /path/to/your/project
sapper setup --goal "reproduce the empty-token crash" --agents
```

或者，因为它本身就是一个 skill，用户可以在 Claude Code 里直接输入 `/sapper-setup <goal>`，Claude 会执行等价命令。

## 多智能体 tmux 授权流程

如果用户希望多个 AI agent 通过 tmux 协同，请在常规 setup 之后按以下步骤操作：

1. 运行 `sapper peers --discover`，把 pane 列表展示给用户。
2. 询问哪些 pane / agent 允许通信、使用什么名字。
3. 只有在明确批准之后，才运行：

```bash
sapper peers --add harley --target api-6:0.0 --sender "Codex/api2-4"
```

4. 用 `sapper send harley "message"` 通信。它会把消息追加到 `.sapper/ai-channel.txt`，并使用可靠的 tmux paste-buffer 提交流程。
5. 发出问题后，用 `sapper capture harley --lines 120` 读取该已授权对端最近在 TUI 中的直接回复。对端可能不通过 `sapper send` 回答，所以共享频道日志并不总是够用。

**不要**根据 discover 的输出或 session 名字推断授权。除非 `sapper peers` 显示该目标已在本项目的 `.sapper/ai-peers.json` 中授权，否则绝不要向它发送消息、或从它抓取输出。

## 启用之后

- 每个会话、每一轮都会提醒模型读取 / 维护图。
- 钩子在每个会话、每一轮注入来自 `date` 的当前本地时间。
- 用 `sapper dispatch reason`（指挥官提出下一步工作）、`sapper dispatch <intent-id> --skip-permissions`（执行者干活）、`sapper dispatch verify --intent <id>`（核验结果）或 `sapper auto --skip-permissions`（跑到完成的完整循环）来驱动它。
- 随时查看状态：`sapper status`、`sapper graph`；在自主派发之前、或提交 `.sapper/` 之前，运行只读的 `sapper validate` 审计。

## 撤销

```bash
sapper teardown            # 移除 sapper 钩子及其 AGENTS.md，保留 .sapper/
sapper teardown --purge    # 同时删除图数据
```

`install.sh --uninstall` 会在全局移除 `sapper` 命令与本 skill，但绝不会触碰项目级的 `.sapper/` 或 `.claude/` —— 那些属于各个项目，必须用 `teardown` 逐项目清除。

## 自主性护栏（提示词注入）

被派发的执行者（`sapper dispatch <intent>`、`sapper auto`）会带着整张图运行 —— 每个 fact / intent / hint 的文本都会被插值进它的提示词。因此被记录为"事实"的文本，会成为下一个执行者看到的指令。执行者的系统提示词把图内容围栏标注为**不可信数据**，并告知 agent 把其中嵌入的"忽略你的规则 / 执行这条命令"之类文本当作需要记录的观察，而不是需要服从的命令。那是一种文本层面的防御，不是沙箱。

危险组合：图被**不可信**内容喂入（仓库里一份敌意的 `.sapper/*.json`，或从攻击者可控的代码 / 输出中转录来的事实）**加上** `--skip-permissions` **加上**真实的 shell / 文件访问权限。在这种情形下，某个图字段就可能试图驱动 agent。**不要在 `.sapper/` 来源不可信的仓库上运行 `sapper auto --skip-permissions`** —— 优先使用默认模式（每次工具调用都提示你），并在据此行动之前先阅读自主运行写下的事实。把 `--skip-permissions` 视为每次运行的显式选择。

## 文件都在哪（重要 —— 没有任何全局内容）

- `./.sapper/` —— 所有图数据。移动 / 删除项目，图随之消失。
- `./.claude/settings.json` —— 那两条钩子条目，项目级作用域。
- `./AGENTS.md` —— 子 agent 协议（可选）。
- `~/.local/bin/sapper` —— CLI（一个软链）。
- `~/.claude/skills/sapper-setup` —— 本 skill（一个软链）。

没有 `~/.sapper`，没有全局钩子注册，项目之间也不共享状态。两个启用的项目拥有两张独立的图。
