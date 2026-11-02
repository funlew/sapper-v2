# sapper —— 完整示例

## 示例 1 —— 一次调试战役（fgc 经典场景）

目标是找出 `python reproduce.py` 为什么会段错误。

```bash
# 0. 准备工作目录
mkdir -p /tmp/sapper-demo && cd /tmp/sapper-demo
cat > reproduce.py <<'EOF'
import sys
print("loading module X")
# …… 想象这里在某个 C 扩展深处发生段错误
raise SystemExit("segfault would happen here in the real case")
EOF

# 1. 建图
sapper init --origin "user report: segfault" --goal "find root cause of segfault in reproduce.py"

# 2. 看一眼
sapper status
sapper graph                    # 以文本形式输出完整图

# 3. 指挥官提出第一批意图（先 dry-run 看提示词）
sapper dispatch reason --dry-run

# 4. 正式执行 —— sonnet 读图，并把意图写进 .sapper/
sapper dispatch reason

# 5. 完成第一个被提出的意图
sapper pick                       # -> i001
sapper dispatch i001

# 6. 核验它声称的结果
sapper dispatch verify --intent i001

# 7. 循环：reason -> explore -> verify，直到指挥官返回 {"complete":...}
sapper dispatch reason

# 8. 收工
sapper complete --from f003 --note "C extension double-free, patched in v2.1"

sapper status                     # status: completed
```

## 示例 2 —— 一次渗透交战 / CTF 题（sapper 原生场景）

```bash
mkdir -p runs/c01 && cd runs/c01
sapper init --goal "break target c01 and submit the flag"

# 可选：接上比赛平台 API（端点按官方文档填写）
sapper arena init
export SAPPER_ARENA_TOKEN=...

# 侦察结果以带类型的事实落图
sapper fact "10.0.2.15 alive, ports 22,80,3306" -t "主机存活" -k host -d ip=10.0.2.15 -d os=linux
sapper fact "80/tcp nginx 1.18 + php 7.2" -k service -d host=10.0.2.15 -d port=80 -d product=nginx -d version=1.18
sapper fact "admin:admin123 logs into /admin" -k cred -d username=admin -d password=admin123

# 利用，然后在看到 flag 的那一刻：
sapper flag "flag{s0me_pr00f}" -c c01 --submit
sapper status
#   kinds:  1 hosts, 1 services, 1 creds, 1 flag(s)
#   flag:   f005 status=submitted challenge=c01 value=flag{s0me_pr00f}

# 受比赛时钟约束的自主运行
sapper auto --skip-permissions --deadline "2026-10-17T13:00:00"

# 整个题板轮转
cd .. && sapper sweep --root runs --minutes-per 20 --deadline "2026-10-17T13:00:00" --skip-permissions
```

## 断点续跑

图就在磁盘上。关掉终端，明天再回来：

```bash
cd runs/c01
sapper status      # 刚好从你离开的地方接上
sapper graph       # 事实 + 意图的完整历史
```
