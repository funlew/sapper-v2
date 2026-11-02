# sapper 知识库索引（Knowledge Base Index）

> `kb/` = **knowledge base**（知识库）的缩写。这里是 sapper 智能体共享的**离线**知识库：
> 随 `git clone` 一起分发，在断网的比赛机器上也能直接检索，不依赖任何外部服务。
>
> 本文件是**人工维护的索引表**：新增 / 修改条目后，请同步更新对应行。
> 统计基线：`kb001` – `kb056`，共 **56 条**（2026-11）。

---

## 1. 检索方式

```bash
sapper kb list                      # 浏览全部条目（标题 + 标签）
sapper kb search "sql 注入"          # 关键词检索（默认 top 5）
sapper kb search "提权" --tag linux  # 标签过滤
sapper kb show kb012                # 打印完整条目（detail + commands）
sapper kb root                      # 打印当前知识库根目录
```

检索机制（见 [lib/kb.py](../lib/kb.py)）：把 query 与每条 `title` / `description` / `tags` 做 token 重叠打分，**标题权重 ×2**，无 embedding、无外部依赖；中文按单字切分，因此中文标题与标签直接影响命中率。

条目文件：`entries/kbNNN.json`，一条一个文件，字段为 `id` / `title` / `description` / `detail` / `commands` / `tags` / `source` / `created_at`。

---

## 2. 全量索引（56 条）

| ID | 标题 | 概要 | 标签 | 来源 |
|---|---|---|---|---|
| `kb001` | Web 信息收集工作流 | 打点上手顺序：指纹→目录→泄露→参数 | web, recon | 经验/hacktricks |
| `kb002` | SQL 注入 — 确认、绕过与提数据 | 手工确认优先，WAF 绕过空间变换，分库提数据 | web, sqli | 经验/sqlmap |
| `kb003` | 文件上传绕过 | 黑名单 / 白名单 / 解析 / 竞争四类打法 | web, upload | 经验 |
| `kb004` | SSTI 模板注入 | Jinja2 / Twig / Smarty 检测三元组与利用 | web, ssti | 经验/PayloadsAllTheThings |
| `kb005` | PHP 反序列化与 POP 链 | 入口识别→链构造→phar 变体 | web, deser, php | 经验/phpggc |
| `kb006` | SSRF 利用 | 协议升级 gopher 打内网 + 云元数据拿凭据 | web, ssrf | 经验/hacktricks |
| `kb007` | 命令注入与 RCE 绕过 | 无回显走外带，关键字用变量拼接 | web, rce, cmd | 经验 |
| `kb008` | XXE | 有回显直读，无回显 OOB 外带 | web, xxe | PayloadsAllTheThings |
| `kb009` | JWT 攻击 | none / 弱密钥 / kid 三板斧 | web, jwt, auth | 经验 |
| `kb010` | 弱口令与默认凭据清单 | 后台 / 数据库 / 中间件管理台默认口令速查 | cred, recon | 经验 |
| `kb011` | 凭据复用方法论 | 每个新凭据按固定顺序喷洒 | cred, lateral | 经验 |
| `kb012` | Linux 提权套路 | sudo / SUID / cron / 内核 顺序排查 | privesc, linux | GTFOBins/linpeas |
| `kb013` | Windows 提权套路 | 服务 / 令牌 / UAC / 内核 | privesc, windows | 经验/winpeas |
| `kb014` | 容器 / K8s 逃逸 | privileged / socket / cap / k8s token | container, privesc, cloud | 经验 |
| `kb015` | 内网横向与代理链 | 先通路后扫描，工具走代理 | lateral, pivot, network | 经验 |
| `kb016` | 常见 CVE 速查（web 入口向） | 按指纹命中即试的公开漏洞清单 | cve, web | 经验/nuclei-templates |
| `kb017` | git 泄露利用 | `.git` 目录恢复源码与历史凭据 | web, leak, recon | 经验 |
| `kb018` | 数据库后利用速查 | 各库拿数据 / 拿 shell / 读文件 | db, post | 经验 |
| `kb019` | CTF flag 常见藏点 | 拿 shell 后按清单翻 | flag, method | 经验 |
| `kb020` | 比赛策略与卡壳协议 | 时间分配 / 提示纪律 / 双保险 | meta, strategy | 往届复盘 |
| `kb021` | 往届冠军架构经验（TCH/Cairn，唯一 AK） | 黑板+DAG 两层调度、极简协议、并行同质 Worker、最强模型全速 | meta, architecture | l3yx.github.io TCH 复盘 |
| `kb022` | 上下文管理与防膨胀（三编译器） | 审题编译 / 进度编译 / 重试续作——不让打题 Agent 自己记笔记 | meta, memory, architecture | CHYing-agent 复盘 |
| `kb023` | 停损与防沉迷机制 | 三层检测打转 + 强制换向 + 调用签名去噪 | meta, control | CHYing-agent/l3yx |
| `kb024` | 成本、并发与模型选择策略 | 速度即分数；并发限制是隐形杀手；贵模型早期、便宜模型后期 | meta, strategy | TCH/CHYing |
| `kb025` | 平台赛制与 API 流程（往届参考） | 每日挑战次数、阶梯解锁阈值、比赛/调试时段结构 | meta, arena | 官方规则页/往届复盘 |
| `kb026` | 多智能体社交博弈经验（零界/对抗场） | 合作是纳什均衡；密钥可复制则免费送；Tit-for-Tat 策略 | meta, strategy, multiagent | CHYing-agent 零界复盘 |
| `kb027` | AI 渗透 Agent 通用架构模式（六大派） | 层级多 Agent / 协作式 / 意图超个体 / 受监控黑盒 / CS-MCP / 人机制衡 | meta, architecture | yzddmr6.com |
| `kb028` | 执行环境与工具链清单（往届实战） | Kali 容器、每任务独立 tmp、base64 传码、结果标注本地/远端 | meta, environment | TPT-Agent/enoch |
| `kb029` | AI 基础设施攻击面 | Ollama / Langflow / LLM API 网关常见漏洞 | ai, cve, web | Wiz/Oligo/Sysdig 公开报告 |
| `kb030` | 云安全攻击清单 | AK/SK、元数据、Bucket、容器仓库 | cloud, cve | 经验/hacktricks-cloud |
| `kb031` | CVE 速查卷二（按产品） | 中间件 / 组件类第二梯队清单 | cve, web | 经验/nuclei-templates |
| `kb032` | 反弹 shell 与升级交互 | 一句话反弹汇总 + 伪终端升级 | post, shell | PayloadsAllTheThings |
| `kb033` | 隧道与代理配置速查 | frp / chisel / ssh 三件套常用配置 | pivot, network | 经验 |
| `kb034` | 字典与 wordlist 位置 | 常用字典路径与生成 | recon, bruteforce | 经验 |
| `kb035` | Windows 域渗透入门（比赛向） | 四赛区铸剑·止戈方向基础 | ad, windows, lateral | 经验/impacket |
| `kb036` | 协议与服务弱配置攻击 | 非 HTTP 服务的常见突破口 | network, recon | 经验/hacktricks |
| `kb037` | 逻辑漏洞与越权清单 | 改包思维：横向越权 / 纵向越权 / 流程破坏 | web, logic | 经验 |
| `kb038` | 请求头与来源绕过技巧 | XFF / Host / Referer 三板斧 + 方法绕过 | web, bypass | 经验 |
| `kb039` | Cookie/Session 攻击 | 伪造 / 固定 / 解密 / 注入四路 | web, auth | 经验 |
| `kb040` | Misc 隐写与杂项速查 | 文件头 / 字符串 / 隐写三板斧 | misc | CTF wiki 思路 |
| `kb041` | Crypto 常见套路（比赛速查） | 古典 / 编码 / 常见数学陷阱 | crypto | CTF wiki 思路 |
| `kb042` | Pwn 二进制方向速查 | 栈溢出到 libc 三步与常见保护绕过 | pwn | CTF wiki 思路 |
| `kb043` | 爆破与验证码处理 | hydra / burp 验证码场景打法 | bruteforce, web | 经验 |
| `kb044` | 应急与反制面发现（靶机侦察向） | 拿下机器后先看有没有监控 / 蜜罐 | recon, post | 往届经验 |
| `kb045` | vm2/JS 沙箱逃逸套路 | JS 沙箱题通用打法：版本先行，再选逃逸 | sandbox, js, rce | 实战/BCTF2026 测试 |
| `kb046` | ComfyUI 漏洞组合拳 | ComfyUI 实例的已知攻击面清单 | comfyui, ai, rce, unauth | 实战/BCTF2026 测试 |
| `kb047` | initcode / 代码注入类靶机 | 运行用户提交代码的靶机通用思路 | codeexec, sandbox, misc | 实战/BCTF2026 测试 |
| `kb048` | LDAP 服务攻击面 | 遇到 LDAP(389/636) 的题怎么打 | ldap, enum, injection | 实战/BCTF2026 测试 |
| `kb049` | 多 flag 靶机的穷举位 | 一题多旗时旗子都藏哪 | flag-hunt, post-exploit | 实战/BCTF2026 测试 |
| `kb050` | 中间件 RCE 速查（版本→CVE→nuclei） | 指纹命中即打的最高频中间件漏洞表 | cve, rce, middleware | 实战沉淀/CVE速查 |
| `kb051` | 反序列化利用速查 | Java / PHP / Python 序列化特征的标准流程 | deser, rce | 实战沉淀 |
| `kb052` | 版本指纹方法论 | 一切 CVE 打击的前置：先把版本钉死 | recon, fingerprint | 实战沉淀 |
| `kb053` | nuclei 高效打法 | 把镜像内几千个模板当武器库用 | nuclei, scan | 实战沉淀 |
| `kb054` | 比赛高频 CVE 二代清单（2024-2026） | 近年攻防赛常客与国产面板套件 | cve, panel, chinese | 实战沉淀 |
| `kb055` | 高频 CVE 字面 payload（可直接粘贴） | 一击必杀的完整命令——不用现场回忆 | cve, payload, rce | 审计补强 |
| `kb056` | 靶机不出网的 RCE 后利用 | JNDI 失效、无回连时怎么把数据带出来 | post-exploit, blind | 审计补强 |

---

## 3. 按主题速查

| 主题 | 条目 | 适用时刻 |
|---|---|---|
| **侦察与指纹** | `kb001` `kb017` `kb034` `kb036` `kb052` | 刚拿到靶标，先定攻击面与版本 |
| **Web 利用与注入** | `kb002` `kb003` `kb004` `kb005` `kb006` `kb007` `kb008` `kb037` `kb038` `kb045` `kb047` `kb051` | 有 HTTP 入口，逐个参数试 |
| **认证与凭据** | `kb009` `kb010` `kb011` `kb039` `kb043` `kb048` | 看到登录框 / token / 目录服务 |
| **提权与横向** | `kb012` `kb013` `kb014` `kb015` `kb033` `kb035` | 已有立足点，往上/往里走 |
| **CVE、中间件与工具** | `kb016` `kb029` `kb030` `kb031` `kb046` `kb050` `kb053` `kb054` `kb055` | 指纹命中后查现成 payload |
| **后利用与取 flag** | `kb018` `kb019` `kb032` `kb044` `kb049` `kb056` | 拿到命令执行之后 |
| **其他赛题方向** | `kb040` `kb041` `kb042` | Misc / Crypto / Pwn |
| **策略、架构与平台** | `kb020` `kb021` `kb022` `kb023` `kb024` `kb025` `kb026` `kb027` `kb028` | 开局定策略、卡壳、控上下文、算成本 |

---

## 4. 维护规范

### 4.1 新增条目

```bash
sapper kb add "标题（写清场景）" \
  -d "一句话：遇到什么情况就打什么" \
  --detail-file notes.md \
  -t web -t sqli \
  -c "可直接粘贴的命令" \
  --source "经验/来源"
```

- ID 自动分配为 `kbNNN`（当前最大 + 1），文件落在 `entries/kbNNN.json`
- 写完**必须回来更新本文件**：第 2 节表格新增一行，第 3 节挂到对应主题
- 批量导入现成 Markdown：`sapper kb import --path <文件或目录>`

### 4.2 字段约定

| 字段 | 要求 |
|---|---|
| `id` | 形如 `kb001`，与文件名一致，只增不改 |
| `title` | 写**触发场景**而不是概念名（如"靶机不出网的 RCE 后利用"），检索权重最高 |
| `description` | 一句话说明"什么时候用、能拿到什么"，权重次之 |
| `detail` | Markdown 正文：方法、payload、坑、边界条件 |
| `commands` | 可直接粘贴的命令数组，避免需要现场回忆 |
| `tags` | 小写，匹配 `^[a-z0-9][a-z0-9_-]*$`，优先复用已有标签 |
| `source` | 来源（经验 / 写题 / 报告 / 往届复盘），便于回溯可信度 |
| `created_at` | 由 CLI 自动写入 UTC 时间，勿手改 |

### 4.3 标签一览

高频标签（优先复用）：

| 标签 | 条目数 | 含义 |
|---|---|---|
| `web` | 17 | HTTP 侧攻击面 |
| `meta` | 9 | 方法论、策略、架构（非具体漏洞） |
| `cve` | 7 | 具体 CVE / 产品漏洞 |
| `recon` | 7 | 信息收集与指纹 |
| `rce` | 6 | 远程命令执行 |
| `network` `privesc` `lateral` `post` `architecture` `strategy` | 各 3 | 网络 / 提权 / 横向 / 后利用 / 架构 / 策略 |
| `cloud` `pivot` `bruteforce` `ai` `misc` `sandbox` `windows` `cred` `deser` `auth` `post-exploit` | 各 2 | 云 / 隧道 / 爆破 / AI / 杂项 / 沙箱 / Windows / 凭据 / 反序列化 / 认证 / 后利用 |

其余为细分标签（`sqli` `ssti` `ssrf` `xxe` `jwt` `upload` `logic` `bypass` `ldap` `ad` `container` `panel` `middleware` `nuclei` `fingerprint` `codeexec` `blind` `flag` `flag-hunt` `crypto` `pwn` `js` `php` `cmd` `shell` `leak` `db` `environment` `arena` `multiagent` `memory` `control` `method` `chinese` `payload` `comfyui` `unauth` `injection` `enum` `scan` 等），新增时按需取用。

### 4.4 自检

```bash
sapper kb list                     # 条目总数与标题是否齐全
sapper kb search "<新条目的关键词>"  # 能否被检索到（验证 title/description 写法）
sapper kb show kbNNN               # 字段是否完整、命令是否可直接跑
```

> 提示：检索只做词面重叠，**标题里的关键词就是命中率**。若某条搜不到，优先改标题与 `description`，而不是加更多标签。
