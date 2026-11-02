"""
test_sapper-note.py —— tests/test_sapper.py 的「带详细注释」副本。

用途
    * 供人阅读 / 代码评审 / 教学：每个测试类说明「测的是哪个模块的哪条契约」，
      每个测试方法说明「构造了什么异常场景、断言在防什么回归」。

重要约定
    * 本文件的断言与调用逻辑与原文件**逐字一致**，只新增注释，不改行为。
    * 原文件里 `if __name__ == "__main__": unittest.main()` 位于文件中部，
      这会导致「直接运行该文件」时只执行它上面的测试类；本文件保留该结构
      并就地注明，避免阅读时误以为后面的类没有被执行。

运行方式
    python tests/test_sapper-note.py
    （若用 pytest / unittest discover 批量收集，文件名含 '-' 不是合法模块名，
      可能无法导入；批量场景请用原文件 tests/test_sapper.py。）

整体覆盖范围
    1. GraphIntegrityTests      图节点读写、校验、并发/租约、模板替换、HTML 转义
    2. SettingsPatchTests       .claude/settings.json 的幂等增删与格式校验
    3. PeerConfigTests          tmux 对端配置校验、setup 的前置校验顺序
    4. TypedFactTests           带类型事实（kind/data）的写入、渲染与校验
    5. FlagLedgerTests          flag 账本的去重、状态机与类型保护
    6. DeadlineTests            --minutes / --deadline 解析与时间预算文案
    7. ArenaClientTests         TSecBench API 契约（header/路径/参数/错误信封）
    8. ArenaErrorBridgeTests    平台 409 不得击穿 bench 的错误桥接
    9. CommanderTests           command 子命令的 JSON 解析与题板渲染
   10. FleetTests               fleet 配置的 pane 命令生成与初始化
   11. HireFireTests           hire/fire 解析、活跃 worker 探测、题板 worker 列
   12. KeyRotationTests        配额错误识别与 Key 池轮换
"""

# 标准库导入：全部是测试自身需要的工具，被测代码 lib/sapper.py 本身零依赖。
import contextlib   # 用于捕获被重定向的 stdout / stderr，检查 CLI 输出
import io           # StringIO：把打印输出接进内存，便于断言
import importlib.util  # 以「文件路径」动态加载模块（绕开包结构），用于加载 _settings_patch.py / arena.py
import json         # 读写节点 JSON，构造/篡改磁盘上的测试数据
import sys          # 修改 sys.path，让测试能 import lib/ 下的模块
import tempfile     # 每个用例一个独立临时目录，避免相互污染
import unittest     # 测试框架基类与断言
from unittest import mock  # 打桩：替换 _tmux / run_claude 等外部副作用
from pathlib import Path   # 统一路径操作

# ROOT = 仓库根目录（tests/ 的上一级）。后续用它定位 lib/ 与 templates/。
ROOT = Path(__file__).resolve().parents[1]
# 把 lib/ 加入模块搜索路径，才能 `import sapper`（CLI 主模块）。
sys.path.insert(0, str(ROOT / "lib"))

import sapper  # noqa: E402  （必须在 sys.path 调整之后导入，故忽略 E402）

# _settings_patch.py 不是标准模块名（下划线开头、非包内文件），用 importlib 按路径加载。
SETTINGS_PATH = ROOT / "lib" / "_settings_patch.py"
_spec = importlib.util.spec_from_file_location("settings_patch_for_tests", SETTINGS_PATH)
settings_patch = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader  # 防御：路径写错时立刻失败，而不是抛晦涩的 AttributeError
_spec.loader.exec_module(settings_patch)


class GraphIntegrityTests(unittest.TestCase):
    """图完整性核心契约。

    覆盖 Store 的「宁可拒绝也不写坏数据」行为：
    残缺节点不炸渲染、init 不覆盖既有目录、校验能发现元数据漂移、
    写边界强制确认、id 不可路径穿越、计数器陈旧不覆盖、关单原子性、
    租约互斥、模板替换不二次展开、HTML 输出转义。
    """

    def setUp(self):
        # 每个用例一个独立临时目录：测试间零共享状态。
        self.tmp = tempfile.TemporaryDirectory()
        self.store = sapper.Store(Path(self.tmp.name) / ".sapper")
        # init 会创建 project.json / facts/goal.json / intents / hints
        self.store.init("test", "ship it")

    def tearDown(self):
        # 显式清理临时目录（Windows 上句柄未释放时会失败，故放在最后）
        self.tmp.cleanup()

    def test_corrupt_node_is_skipped_and_reported_by_validate(self):
        """残缺节点（缺 description）必须被跳过并上报，而不是让整张图炸掉。

        现实中：别的 agent 并发写坏一个文件、或人工编辑失误。
        期望：渲染仍然成功（保留合法节点），stderr 有告警，validate 能定位文件。
        """
        # 直接往 facts 目录写一个只有 id 的坏 JSON，绕过 Store 的写入校验
        (self.store.facts_dir / "f001.json").write_text('{"id":"f001"}\n', encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rendered = sapper.render_graph_text(self.store)
        # 图仍能渲染出目标节点 → 渲染器容错
        self.assertIn("goal: ship it", rendered)
        # 告警写到了 stderr（说明不是静默忽略）
        self.assertIn("missing string 'description'", stderr.getvalue())
        # 只读校验能指出具体坏文件，方便人工修复
        errors = sapper.validate_graph(self.store)
        self.assertTrue(any("f001.json" in error for error in errors))

    def test_init_refuses_non_empty_directory(self):
        """init 只允许在空目录建图，绝不覆盖用户已有文件。

        这是防「误在仓库根目录跑 init 把项目文件当图目录」的关键保护。
        """
        root = Path(self.tmp.name) / "new-store"
        root.mkdir()
        (root / "unrelated.txt").write_text("keep", encoding="utf-8")
        # 断言抛出 FGError 且信息里含 "non-empty directory"
        with self.assertRaisesRegex(sapper.FGError, "non-empty directory"):
            sapper.Store(root).init("", "goal")
        # 失败后原文件必须还在（拒绝了就要一点都没动）
        self.assertTrue((root / "unrelated.txt").exists())

    def test_validate_detects_goal_metadata_drift(self):
        """goal 事实的 description 必须与 project.json 的 goal 一致。

        漂移意味着有人手改了图，或迁移时版本不一致；validate 要能发现。
        """
        goal = self.store.facts_dir / "goal.json"
        data = json.loads(goal.read_text(encoding="utf-8"))
        data["description"] = "different goal"      # 人为制造漂移
        goal.write_text(json.dumps(data), encoding="utf-8")
        errors = sapper.validate_graph(self.store)
        self.assertIn("goal fact description does not match project goal", errors)

    def test_validate_detects_intent_state_mismatch(self):
        """intent 的 status 与结构必须自洽：标记 done 却没有 to（产出事实）。

        状态被设计成「编码在图结构里」，所以单独改 status 字段就是非法状态。
        """
        seed = self.store.add_fact("seed", "test", None)
        intent = self.store.add_intent([seed["id"]], "work", "test")
        path = self.store.intents_dir / f"{intent['id']}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "done"                     # 只改状态，不补 to 边
        path.write_text(json.dumps(data), encoding="utf-8")
        errors = sapper.validate_graph(self.store)
        self.assertTrue(any("completed status requires a target" in error for error in errors))

    def test_confirmation_is_enforced_at_write_boundary(self):
        """带 --confirm 的意图在「写入边界」被强制拦截，而不是只靠提示词。

        同时验证租约归属：不是认领者就不能关单。
        """
        fact = self.store.add_fact("starting point", "test", None)
        intent = self.store.add_intent(
            [fact["id"]], "delete data", "test", requires_confirmation=True
        )
        # 未确认前，写入产出事实必须失败
        with self.assertRaisesRegex(sapper.FGError, "requires confirmation"):
            self.store.conclude_with_new_fact(intent["id"], "must not run", "test")
        # 人工确认后放行
        self.store.confirm_intent(intent["id"])
        self.store.claim_intent(intent["id"], "owner")
        # 已认领给 owner，其他人（other）不能代替关单
        with self.assertRaisesRegex(sapper.FGError, "claimed by owner"):
            self.store.conclude_with_new_fact(intent["id"], "wrong worker", "other")
        # 认领者本人可以正常结单，且 to 指向新产出的事实
        result, concluded = self.store.conclude_with_new_fact(
            intent["id"], "approval was recorded", "owner"
        )
        self.assertEqual(concluded["to"], result["id"])

    def test_lookup_ids_cannot_escape_store(self):
        """id 参数不能做路径穿越（../../outside），否则可读写图目录之外的文件。"""
        with self.assertRaisesRegex(sapper.FGError, "invalid fact id"):
            self.store.get_fact("../../outside")

    def test_stale_counter_never_overwrites_existing_node(self):
        """计数器被回拨/陈旧时，分配 id 必须跳过已存在文件，绝不覆盖。

        场景：手工改 project.json、或多进程恢复快照后再次写入。
        """
        first = self.store.add_fact("first", "test", None)
        project = self.store.load_project()
        project["counters"]["fact"] = 0             # 人为把计数器调回 0
        self.store.save_project(project)
        second = self.store.add_fact("second", "test", None)
        self.assertEqual(first["id"], "f001")
        self.assertEqual(second["id"], "f002")      # 跳过已存在的 f001
        # 原事实内容未被覆盖（这是「绝不覆盖」的直接证据）
        self.assertEqual(self.store.get_fact("f001")["description"], "first")

    def test_fact_from_intent_closes_the_intent_atomically(self):
        """sapper fact --from-intent 必须原子地「写事实 + 关意图」。

        不允许出现「事实写了但意图还开着」的中间态。
        """
        seed = self.store.add_fact("seed", "test", None)
        intent = self.store.add_intent([seed["id"]], "observe", "test")
        fact = self.store.add_fact("observed", "test", intent["id"])
        self.assertEqual(self.store.get_intent(intent["id"])["to"], fact["id"])
        # 关单后整张图必须通过校验（没有悬空边）
        self.assertEqual(sapper.validate_graph(self.store), [])

    def test_linking_existing_fact_sets_its_source_edge(self):
        """把已存在的事实作为结果关联到意图时，要回填该事实的 source_intent。

        否则图上会缺一条「这个事实由哪个意图产出」的反向可追溯边。
        """
        seed = self.store.add_fact("seed", "test", None)
        result = self.store.add_fact("already observed", "test", None)
        intent = self.store.add_intent([seed["id"]], "link result", "test")
        self.store.conclude_intent(intent["id"], result["id"], "test")
        self.assertEqual(self.store.get_fact(result["id"])["source_intent"], intent["id"])
        self.assertEqual(sapper.validate_graph(self.store), [])

    def test_pick_claim_skips_another_workers_lease(self):
        """pick --claim 必须跳过别人已认领的意图，避免两个 agent 抢同一件事。"""
        seed = self.store.add_fact("seed", "test", None)
        first = self.store.add_intent([seed["id"]], "first", "test")
        second = self.store.add_intent([seed["id"]], "second", "test")
        self.store.claim_intent(first["id"], "other-worker")
        # 手工构造 argparse 的 Namespace（只带 cmd_pick 需要的字段）
        args = type("Args", (), {
            "store": str(self.store.root), "claim": True,
            "worker": "my-worker", "any": False,
        })()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            sapper.cmd_pick(args)
        # 输出应是第二件事（第一件被别人租走了）
        self.assertEqual(output.getvalue().strip(), second["id"])

    def test_static_view_escapes_script_terminators(self):
        """静态 HTML 视图必须转义 </script>，否则事实文本可以注入脚本。

        攻击面：图内容来自靶标/不可信来源，一旦原样内联进 <script> 就能 XSS。
        """
        self.store.add_fact("</script><script>alert(1)</script>", "test", None)
        html = sapper._render_static_html(self.store)
        # 原始闭合标签不得出现；应被转成 \u003c 形式
        self.assertNotIn("</script><script>", html)
        self.assertIn(r"\u003c/script\u003e", html)

    def test_prompt_substitution_does_not_rewrite_inserted_braces(self):
        """模板替换必须是「一次性」的：图内容里的 {goal} 不能被二次展开。

        场景：某条事实正文恰好写着 "{goal}"，若实现用循环 replace，
        它会吞掉真正的占位符或造成内容错乱。
        """
        self.store.add_fact("literal {goal} marker", "test", None)
        prompt = sapper.render_prompt(self.store, "{graph_yaml}\nGOAL={goal}")
        # 插入内容里的字面量原样保留
        self.assertIn("literal {goal} marker", prompt)
        # 模板末尾的占位符被正确替换
        self.assertTrue(prompt.endswith("GOAL=ship it"))

    def test_brainstorm_template_token_does_not_rewrite_graph_text(self):
        """brainstorm 的 {max_options} 同理：不能污染图文本里的同名字面量。"""
        self.store.add_fact("literal {max_options} marker", "test", None)
        args = type("Args", (), {
            "max_options": 2, "dry_run": True,
        })()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            # dry-run：只渲染提示词并打印，不调用模型
            sapper._dispatch_brainstorm(
                self.store, ROOT / "templates", "sonnet", 10, False, ROOT, args
            )
        self.assertIn("literal {max_options} marker", output.getvalue())

    def test_verify_payload_requires_actionable_issues_on_failure(self):
        """核验结果的语义约束：失败必须说清问题，成功必须没有 issue。

        防止核验者返回「不通过」却给不出可执行信息，让上游无法修正。
        """
        # verified=false 却 issues 为空 → 拒绝（要求解释）
        with self.assertRaisesRegex(sapper.FGError, "explain"):
            sapper._parse_verify_payload({"verified": False, "issues": ""})
        # verified=true 却带 issues → 拒绝（成功不该有告警）
        with self.assertRaisesRegex(sapper.FGError, "leave 'issues' empty"):
            sapper._parse_verify_payload({"verified": True, "issues": "warning"})

    def test_dispatch_verify_returns_failure_status(self):
        """核验失败时命令要返回非零退出码，才能被上层循环感知并停止。"""
        seed = self.store.add_fact("seed", "test", None)
        intent = self.store.add_intent([seed["id"]], "check", "test")
        result, _ = self.store.conclude_with_new_fact(intent["id"], "result", "test")
        args = type("Args", (), {
            "intent": intent["id"], "dry_run": False,
        })()
        # 打桩引擎调用：伪造「核验不通过」的模型返回，避免真实网络/费用
        with mock.patch.object(
            sapper,
            "run_claude",
            return_value={"result": '{"accepted": true, "data": {"verified": false, "issues": "mismatch"}}'},
        ):
            rc = sapper._dispatch_verify(
                self.store, ROOT / "templates", "sonnet", 10, False, ROOT, args
            )
        self.assertEqual(rc, 1)   # 1 = 失败退出码

    def test_completed_graph_validates_and_duplicate_completion_is_rejected(self):
        """项目完成后的图仍要合法；重复 complete 必须报错（幂等边界）。"""
        fact = self.store.add_fact("evidence", "test", None)
        self.store.complete_project([fact["id"]], "finish", "test")
        self.assertEqual(self.store.load_project()["status"], "completed")
        self.assertEqual(sapper.validate_graph(self.store), [])
        with self.assertRaisesRegex(sapper.FGError, "already completed"):
            self.store.complete_project([fact["id"]], "finish again", "test")

    def test_brainstorm_batches_are_unique(self):
        """同一批 brainstorm 产出的意图要带批次标记，且两次调用批次不同。

        否则 brainstorm-pick 会把历史批次误当成本批次的兄弟一起淘汰。
        """
        seed = self.store.add_fact("seed", "test", None)
        payload = {
            "accepted": True,
            "data": {
                "options": [
                    {"from": [seed["id"]], "title": "one", "description": "first"}
                ]
            },
        }
        sapper._apply_brainstorm(self.store, payload)
        sapper._apply_brainstorm(self.store, payload)   # 第二次同一 payload
        docs = [i["doc"] for i in self.store.list_intents()]
        self.assertEqual(len(docs), 2)
        # 每条 doc 里都有一行 "[brainstorm batch: ...]" 标记，且两组标记不同
        tags = [line for doc in docs for line in doc.splitlines() if line.startswith("[brainstorm batch:")]
        self.assertEqual(len(set(tags)), 2)

    def test_brainstorm_pick_preserves_abandoned_edges(self):
        """brainstorm-pick 只确认选中项、把其余标记为放弃，但图仍要自洽。

        关键：被放弃的意图不能被「删边」到非法状态，validate 必须仍然通过。
        """
        seed = self.store.add_fact("seed", "test", None)
        payload = {
            "accepted": True,
            "data": {"options": [
                {"from": [seed["id"]], "title": "one", "description": "first"},
                {"from": [seed["id"]], "title": "two", "description": "second"},
            ]},
        }
        sapper._apply_brainstorm(self.store, payload)
        picked = self.store.list_intents()[0]
        args = type("Args", (), {"store": str(self.store.root), "id": picked["id"], "purge": False})()
        sapper.cmd_brainstorm_pick(args)
        intents = self.store.list_intents()
        # 一个仍处于未关闭（被选中、待执行），另一个已结单（被放弃）
        self.assertEqual(sum(i["to"] is None for i in intents), 1)
        self.assertEqual(sum(i["to"] is not None for i in intents), 1)
        self.assertEqual(sapper.validate_graph(self.store), [])


class SettingsPatchTests(unittest.TestCase):
    """.claude/settings.json 的幂等修补。

    这是 sapper 唯一会改动「用户既有配置文件」的地方，所以契约很硬：
    只加自己的 hook、绝不动别人的、重复执行不重复写、删只删自己的、
    非对象 JSON 直接拒绝（宁可报错也不覆盖成空配置）。
    """

    def test_settings_patch_is_atomic_and_preserves_unrelated_hooks(self):
        """add 后：自己的 2 条 hook 在，别人的 hook 也在；remove 后：只剩别人的。

        「原子」体现在实现用临时文件 + os.replace，测试这里观察的是结果一致性。
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            # 预置一个用户原有的 SessionStart hook（echo keep）
            path.write_text(
                json.dumps({"hooks": {"SessionStart": [{"matcher": "x", "hooks": [
                    {"type": "command", "command": "echo keep"
                    }
                ]}]}}),
                encoding="utf-8",
            )
            # 返回值第一个元素是「是否有改动」，第二次调用应为 False（幂等）
            changed, _ = settings_patch.add(path, "/tmp/sapper-hook.py")
            self.assertTrue(changed)
            data = json.loads(path.read_text(encoding="utf-8"))
            # 摊平取全部 command，便于断言「既有别人的、也有我们的两条」
            commands = [
                h["command"]
                for groups in data["hooks"].values()
                for group in groups
                for h in group.get("hooks", [])
            ]
            self.assertIn("echo keep", commands)
            # SessionStart + UserPromptSubmit 各一条，共 2 条
            self.assertEqual(sum("sapper-hook.py" in command for command in commands), 2)
            # 移除后，用户原有 hook 必须原样保留
            settings_patch.remove(path, "/tmp/sapper-hook.py")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["hooks"]["SessionStart"][0]["hooks"][0]["command"], "echo keep")

    def test_settings_patch_rejects_non_object_json(self):
        """settings.json 是数组（非对象）时必须拒绝，而不是覆盖/丢弃用户配置。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON object"):
                settings_patch.add(path, "/tmp/sapper-hook.py")
            with self.assertRaisesRegex(ValueError, "JSON object"):
                settings_patch.remove(path, "/tmp/sapper-hook.py")

    def test_settings_validation_catches_malformed_event_shape(self):
        """hooks.SessionStart 必须是数组；写成对象时校验要给出精确路径。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"hooks": {"SessionStart": {}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hooks.SessionStart"):
                settings_patch.validate(path)


class PeerConfigTests(unittest.TestCase):
    """多智能体通信的安全边界与 setup 的前置校验顺序。"""

    def test_malformed_peer_config_is_rejected(self):
        """非法对端名（含空格）必须拒绝：它会被拼进 tmux target，先校验再使用。"""
        with tempfile.TemporaryDirectory() as tmp:
            store = sapper.Store(Path(tmp) / ".sapper")
            store.init("", "peers")
            (store.root / sapper.PEERS_FILE).write_text(
                json.dumps({"version": 1, "channel": "x", "peers": {"bad name": {"target": "x"}}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(sapper.FGError, "invalid peer name"):
                sapper._load_peers(store)

    def test_setup_preflights_invalid_settings_before_creating_graph(self):
        """setup 必须先校验 settings.json，再建图。

        否则会出现「图建了一半、hook 没写成功」的半启用状态，
        用户既没真正接入，又留下了 .sapper/ 需要手工清理。
        """
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / ".claude").mkdir()
            (project / ".claude" / "settings.json").write_text("[]", encoding="utf-8")
            old_cwd = Path.cwd()
            try:
                import os
                os.chdir(project)     # setup 以「当前目录」为项目根
                args = type("Args", (), {
                    "store": ".sapper", "goal": "should not initialize",
                    "origin": "", "agents": False, "force": False,
                })()
                with self.assertRaisesRegex(sapper.FGError, "JSON object"):
                    sapper.cmd_setup(args)
            finally:
                os.chdir(old_cwd)     # 任何情况下都要恢复工作目录
            # 关键断言：失败后没有留下 .sapper/project.json（没有半成品）
            self.assertFalse((project / ".sapper" / "project.json").exists())


# 注意：原文件的 unittest.main() 位于此处（文件中部）。
# 直接 `python test_sapper.py` 时，unittest 只会收集「上面已定义」的测试类，
# 因此 TypedFactTests / FlagLedgerTests / DeadlineTests / Arena* / Commander* /
# Fleet* / HireFire* / KeyRotation* 在「单独运行本文件」时不会被执行。
# 这是原文件的既有行为，本注释副本不做改动，仅在此说明以免误判覆盖率。
if __name__ == "__main__":
    unittest.main()


class TypedFactTests(unittest.TestCase):
    """带类型事实（kind + data）的写读与渲染。

    类型化是渗透场景的关键：指挥官靠 kind/data 做凭据复用、CVE 关联、flag 计数。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = sapper.Store(Path(self.tmp.name) / ".sapper")
        self.store.init("test", "capture the flag")

    def tearDown(self):
        self.tmp.cleanup()

    def test_typed_fact_roundtrip_and_render(self):
        """写入 → 落盘归一化 → 文本 / YAML 渲染都要带上类型与结构化字段。"""
        fact = self.store.add_fact(
            "nginx 1.18 at 10.0.2.15:80", "user",
            kind="service", data={"host": "10.0.2.15", "port": 80},
        )
        self.assertEqual(fact["kind"], "service")
        # data 值统一转成字符串（port 传的是 int 80）
        self.assertEqual(fact["data"]["port"], "80")
        text = sapper.render_graph_text(self.store)
        self.assertIn("<service>", text)
        self.assertIn("port=80", text)
        # 提示词用的 YAML-like 视图也必须带类型与数据
        yaml = sapper._to_yaml_like(sapper.build_graph_view(self.store))
        self.assertIn("<service>", yaml)
        # prompt rendering scrubs braces so flag{...} cannot eat placeholders
        # 注释：渲染时会清理花括号，避免 flag{...} 被当成模板占位符
        self.assertIn("port=80", yaml)

    def test_unknown_kind_and_bad_data_rejected(self):
        """未知 kind 与非法 data 键都必须拒绝（写入即失败，不落脏数据）。"""
        with self.assertRaises(sapper.FGError):
            self.store.add_fact("x", "user", kind="exploit")
        # 键名含空格/感叹号，不匹配 DATA_KEY_RE
        with self.assertRaises(sapper.FGError):
            self.store.add_fact("x", "user", kind="cred", data={"bad key!": "1"})

    def test_validate_rejects_invalid_kind_on_disk(self):
        """磁盘上被手工改坏的 kind，validate 必须能发现（读侧也校验）。"""
        fact = self.store.add_fact("x", "user", kind="cred")
        p = self.store.facts_dir / f"{fact['id']}.json"
        node = json.loads(p.read_text(encoding="utf-8"))
        node["kind"] = "exploit"          # 绕过写侧校验，直接改盘上文件
        p.write_text(json.dumps(node), encoding="utf-8")
        errors = sapper.validate_graph(self.store)
        self.assertTrue(any("kind" in e for e in errors))

    def test_explore_payload_carries_kind_and_data(self):
        """执行者返回的 JSON 要把 kind/data 透传到事实，而不是丢掉只留描述。"""
        payload = {"accepted": True, "data": {
            "description": "RCE confirmed",
            "kind": "vuln",
            "data": {"cve": "CVE-2021-41773"},
        }}
        title, desc, doc, kind, data = sapper._parse_explore_payload(payload)
        self.assertEqual(kind, "vuln")
        self.assertEqual(data, {"cve": "CVE-2021-41773"})


class FlagLedgerTests(unittest.TestCase):
    """flag 账本：去重、状态机、类型保护。

    比赛场景下 flag 是唯一产出，账本必须「先记录后提交」且不可被误改类型。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = sapper.Store(Path(self.tmp.name) / ".sapper")
        self.store.init("test", "capture the flag")

    def tearDown(self):
        self.tmp.cleanup()

    def test_flag_record_and_dedupe(self):
        """同一个 flag 值只能有一条账本记录（按 value 查重）。"""
        fact = self.store.add_fact(
            "flag captured: flag{a}", "agent",
            kind="flag", data={"value": "flag{a}", "challenge": "c01", "status": "recorded"},
        )
        dup = sapper._find_flag_fact(self.store, "flag{a}")
        self.assertEqual(dup["id"], fact["id"])       # 命中已有记录
        self.assertIsNone(sapper._find_flag_fact(self.store, "flag{b}"))  # 新值不命中

    def test_flag_status_lifecycle_and_type_guard(self):
        """状态机 recorded → submitted/rejected；非 flag 事实不得改状态。

        第三个断言是关键：防止把普通事实「升级」成 flag 记录来伪造战绩。
        """
        fact = self.store.add_fact(
            "flag captured: flag{a}", "agent",
            kind="flag", data={"value": "flag{a}", "status": "recorded"},
        )
        updated = self.store.update_flag_fact(fact["id"], "submitted", '{"ok":true}')
        self.assertEqual(updated["data"]["status"], "submitted")
        self.assertEqual(updated["data"]["result"], '{"ok":true}')   # 平台回执留存
        plain = self.store.add_fact("just text", "agent")            # 非 flag 类型
        with self.assertRaises(sapper.FGError):
            self.store.update_flag_fact(plain["id"], "submitted", None)
        # 非法状态值也必须拒绝（状态机白名单）
        with self.assertRaises(sapper.FGError):
            self.store.update_flag_fact(fact["id"], "hacked-status", None)

    def test_status_shows_flag_ledger(self):
        """sapper status 要直接呈现 flag 账本：状态 + 所属题目。"""
        self.store.add_fact(
            "flag captured: flag{z}", "agent",
            kind="flag", data={"value": "flag{z}", "challenge": "c09", "status": "submitted"},
        )
        text = sapper.render_status(self.store)
        self.assertIn("flag(s)", text)
        self.assertIn("status=submitted", text)
        self.assertIn("challenge=c09", text)


class DeadlineTests(unittest.TestCase):
    """--minutes / --deadline 解析与预算文案。

    比赛有时间窗，预算解析错一秒都可能多跑或少跑；三种入参（只给分钟、
    只给 ISO 时间、两者都给）必须有确定语义。
    """

    def test_minutes_and_iso_and_conflict(self):
        """- --minutes N → 当前时间 + N 分钟
        - --deadline ISO → 解析为该时刻
        - 两者同时给 → 视为参数冲突直接报错（不做「谁优先」的猜测）
        - 非法日期 → 报错；都不给 → None（无截止）
        """
        import time as _t
        a = type("A", (), {"deadline": None, "minutes": 5})()
        d = sapper.deadline_from_args(a)
        self.assertGreater(d, _t.time())          # 将来的时间戳
        b = type("B", (), {"deadline": "2026-10-17T13:00:00", "minutes": None})()
        self.assertIsNotNone(sapper.deadline_from_args(b))
        c = type("C", (), {"deadline": "2026-10-17T13:00:00+08:00", "minutes": 5})()
        with self.assertRaises(sapper.FGError):   # 冲突：不允许暧昧
            sapper.deadline_from_args(c)
        bad = type("D", (), {"deadline": "not-a-date", "minutes": None})()
        with self.assertRaises(sapper.FGError):   # 解析失败就失败，不静默忽略
            sapper.deadline_from_args(bad)
        self.assertEqual(sapper.deadline_from_args(type("E", (), {"deadline": None, "minutes": None})()), None)

    def test_format_time_budget(self):
        """预算文案：无截止 = 空串；已过时 = 明确 TIME IS UP；未来 = 剩余时间。"""
        self.assertEqual(sapper.format_time_budget(None), "")
        self.assertIn("TIME IS UP",
                      sapper.format_time_budget(0))  # 0 -> epoch 1970, always past
        self.assertIn("remaining", sapper.format_time_budget(_t.time() + 600))


import time as _t  # noqa: E402  (DeadlineTests)
# 说明：上面这行模块级导入放在此处，是为了服务 test_format_time_budget；
# 因为 DeadlineTests 类体在模块加载时只「定义」不「执行」，所以不影响运行。


class ArenaClientTests(unittest.TestCase):
    """TSecBench Challenges API 的契约测试。

    不靠真实平台，而是用本地 HTTPServer 复刻平台行为，确保：
    header 名、路径、query/body 形状、错误信封字段 一旦改错就能立刻发现。
    """

    def _arena(self):
        # 每次重新按路径加载 arena.py，拿到干净模块（避免测试间状态污染）
        import importlib.util
        spec = importlib.util.spec_from_file_location("_arena_test", ROOT / "lib" / "arena.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_client_contract_against_local_server(self):
        """用本地 mock 服务验证五个端点 + 鉴权头 + 参数/包体。

        seen 列表记录服务端收到的一切，事后逐条比对，比只断言「调用成功」更严。
        """
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        arena = self._arena()
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass                                  # 关掉测试里的访问日志噪声

            def _reply(self, obj, code=200):
                # 统一的 JSON 回复助手：包含 Content-Length，避免客户端挂着等
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _record(self):
                # 记下（方法, 路径, 鉴权头, 包体）供后续断言
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                seen.append((self.command, self.path, self.headers.get("BENCHMARK_TOKEN"), body))

            def do_GET(self):
                self._record()
                if self.path.startswith("/openapi/v1/challenges/hint"):
                    return self._reply({"unique_code": "c1", "hint": "h"})
                # 默认当作题目列表（字段按官方 SDK 的 Challenge 结构）
                return self._reply([{"unique_code": "c1", "difficulty": "easy", "level": "1",
                                     "total_score": 100, "flag_count": 2, "correct_flag_count": 0,
                                     "is_completed": False, "description": "d",
                                     "container_status": "stopped", "container_addr": []}])

            def do_POST(self):
                self._record()
                if self.path.startswith("/openapi/v1/challenges/submit"):
                    return self._reply({"correct": True, "awarded": 50, "cumulative_score": 50,
                                        "correct_flag_count": 1, "total_flag_count": 2,
                                        "matched_flag_index": 0})
                if self.path.startswith("/openapi/v1/challenges/close"):
                    return self._reply({"unique_code": "c1", "closed": True})
                # 其余 POST 视为 start
                return self._reply({"unique_code": "c1", "container_addr": ["10.0.0.9:80"]})

        # 端口传 0：由系统分配空闲端口，避免 CI 上的端口冲突
        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            client = arena.ArenaClient(f"http://127.0.0.1:{server.server_address[1]}", "tok-x")
            chs = client.list_challenges()
            self.assertEqual(chs[0]["unique_code"], "c1")
            started = client.start_challenge("c1")
            self.assertEqual(started["container_addr"], ["10.0.0.9:80"])
            self.assertEqual(client.get_hint("c1")["hint"], "h")
            res = client.submit_flag("c1", "flag{a}")
            self.assertTrue(res["correct"])
            self.assertTrue(client.close_challenge("c1")["closed"])
        finally:
            server.shutdown()                         # 无论如何关闭 mock 服务

        # 每一次请求都必须带 BENCHMARK_TOKEN 头（不能漏掉鉴权）
        self.assertTrue(all(entry[2] == "tok-x" for entry in seen), seen)
        # 精确校验路径与参数/包体形状（一旦改字段名就挂）
        submit = [e for e in seen if e[1] == "/openapi/v1/challenges/submit"][0]
        self.assertEqual(submit[3], {"unique_code": "c1", "flag": "flag{a}"})
        start = [e for e in seen if "start" in e[1]][0]
        self.assertIn("unique_code=c1", start[1])     # query 参数，非 body
        hint = [e for e in seen if "hint" in e[1]][0]
        self.assertIn("unique_code=c1", hint[1])
        close = [e for e in seen if "close" in e[1]][0]
        self.assertIn("unique_code=c1", close[1])

    def test_error_envelope_surfaces_code(self):
        """平台错误信封 {code,message,detail} 必须被解析成结构化异常。

        上层需要 code == "invalid_state" 才能判定是「实例已满」而不是网络错误。
        """
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        arena = self._arena()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                data = json.dumps({"code": "invalid_state", "message": "max active", "detail": {}}).encode()
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            client = arena.ArenaClient(f"http://127.0.0.1:{server.server_address[1]}", "t")
            with self.assertRaises(arena.ArenaError) as ctx:
                client.start_challenge("c1")
            # 异常对象要同时携带平台 code 与 HTTP 状态码
            self.assertEqual(ctx.exception.code, "invalid_state")
            self.assertEqual(ctx.exception.status, 409)
        finally:
            server.shutdown()

    def test_config_resolution_env_and_file(self):
        """配置解析优先级：arena.json 提供 base_url、token 可引用环境变量。

        覆盖：纯环境变量、文件 + ENV: 引用、两者都缺、以及 token 为空字符串。
        """
        arena = self._arena()
        # 场景 1：无配置文件，直接读环境变量
        with mock.patch.dict("os.environ", {"BENCHMARK_BASE_URL": "http://env-base",
                                            "BENCHMARK_TOKEN": "env-tok"}):
            c = arena.ArenaClient.load(None)
            self.assertEqual(c.base_url, "http://env-base")
            self.assertEqual(c.token, "env-tok")
        with tempfile.TemporaryDirectory() as tmp:
            # 场景 2：文件给出 base_url，token 用 "ENV:BENCHMARK_TOKEN" 间接引用
            (Path(tmp) / "arena.json").write_text(json.dumps(
                {"base_url": "http://file-base", "token": "ENV:BENCHMARK_TOKEN"}), encoding="utf-8")
            with mock.patch.dict("os.environ", {"BENCHMARK_TOKEN": "env-tok"}):
                c = arena.ArenaClient.load(Path(tmp))
                self.assertEqual(c.base_url, "http://file-base")
                self.assertEqual(c.token, "env-tok")
        # 场景 3：什么都没有 → 必须报错（不静默连到某个默认地址）
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(arena.ArenaError):
                arena.ArenaClient.load(None)
        # 场景 4：空 token 构造时就拒绝
        with self.assertRaises(arena.ArenaError):
            arena.ArenaClient("http://x", "")

    def test_rejects_unsafe_unique_code(self):
        """unique_code 会被拼进 URL，必须白名单校验，防路径/参数注入。"""
        arena = self._arena()
        client = arena.ArenaClient("http://x", "t")
        with self.assertRaises(arena.ArenaError):
            client.start_challenge("../etc/passwd")


class ArenaErrorBridgeTests(unittest.TestCase):
    """平台 409 不得击穿 bench 的回归测试。

    真实事故：平台返回 "max active challenge instances reached (3)" 时，
    arena.py 抛的是自己的 ArenaError，而 _bench_parallel 只 catch FGError，
    于是异常直接冒出去、把整个 bench 循环打死。
    修复方式：通过 sapper._load_arena_module() 加载的 arena 模块，其
    ArenaError 必须继承 FGError，才能被统一的异常处理接住。
    """

    def test_loaded_arena_error_subclasses_fgerror(self):
        """核心契约：动态加载出来的 ArenaError 必须是 FGError 的子类。"""
        arena = sapper._load_arena_module()
        self.assertTrue(issubclass(arena.ArenaError, sapper.FGError))

    def test_409_max_active_caught_as_fgerror(self):
        """端到端：mock 一个 409「实例已满」，调用方用 except FGError 能接住。"""
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        arena = sapper._load_arena_module()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                # 复刻平台真实报文（包含 max active 文案）
                data = json.dumps({
                    "code": "invalid_state",
                    "message": "max active challenge instances reached (3), "
                               "please close an existing challenge before starting a new one",
                    "detail": {},
                }).encode()
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            client = arena.ArenaClient(
                f"http://127.0.0.1:{server.server_address[1]}", "t")
            # 注意 catch 的是 sapper.FGError（父类），而不是 arena.ArenaError
            with self.assertRaises(sapper.FGError) as ctx:
                client.start_challenge("c1")
            self.assertIn("max active", str(ctx.exception).lower())
        finally:
            server.shutdown()


class CommanderTests(unittest.TestCase):
    """command 子命令（LLM 分配工时）的输入解析与题板渲染。"""

    def test_parse_command_payload(self):
        """合法动作要能提取；越界值必须拒绝，避免把离谱工时/未知动作当真。"""
        ok = {"accepted": True, "data": {"action": "work", "target": "c03", "minutes": 25, "note": "close"}}
        self.assertEqual(sapper._parse_command_payload(ok), ("work", "c03", 25, "close"))
        # stop 不需要 target/minutes，全部归零/置空
        stop = {"accepted": True, "data": {"action": "stop", "reason": "all done"}}
        self.assertEqual(sapper._parse_command_payload(stop), ("stop", "", 0, "all done"))
        # 模型拒答 → 归一化成 reject 动作，由上层决定如何重试
        rej = {"accepted": False, "reason": "bad board"}
        self.assertEqual(sapper._parse_command_payload(rej)[0], "reject")
        # 以下三种都是非法输入
        with self.assertRaises(sapper.FGError):
            sapper._parse_command_payload({"accepted": True, "data": {"action": "hack"}})
        with self.assertRaises(sapper.FGError):
            sapper._parse_command_payload({"accepted": True, "data": {"action": "work", "minutes": 10}})
        with self.assertRaises(sapper.FGError):
            sapper._parse_command_payload({"accepted": True, "data": {"action": "work", "target": "c1", "minutes": 0}})

    def test_board_summary_and_render(self):
        """_board_summary 按目录扫描各题图，聚合 flag 计数；render_board 输出人类可读表。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 造两道题的图目录
            for name in ("c01", "c02"):
                store = sapper.Store(root / name / ".sapper")
                store.init("t", f"flag {name}")
            # 只给 c01 记一面已提交的 flag
            sapper.Store(root / "c01" / ".sapper").add_fact(
                "flag captured: flag{a}", "agent",
                kind="flag", data={"value": "flag{a}", "challenge": "c01", "status": "submitted"})
            rows = sapper._board_summary(root)
            # 行按名称排序，稳定输出便于比对/测试
            self.assertEqual([r["name"] for r in rows], ["c01", "c02"])
            by_name = {r["name"]: r for r in rows}
            self.assertEqual(by_name["c01"]["flags_submitted"], 1)
            self.assertEqual(by_name["c02"]["flags_submitted"], 0)
            board = sapper.render_board(rows)
            self.assertIn("c01", board)
            self.assertIn("flags(sub/rec)", board)


class FleetTests(unittest.TestCase):
    """fleet 子命令：把「一个 session 多个 pane」的编队配置翻译成可执行命令。"""

    def test_fleet_pane_commands(self):
        """不同 pane 类型（command / auto:<题目> / shell）生成的命令行必须准确。

        这里不真的开 tmux，只验证字符串拼接——包括 deadline 透传、
        base_dir 前缀、未知类型与缺命令的报错。
        """
        cfg = {"session": "s", "root": "runs", "deadline": "2026-10-17T13:00:00",
               "panes": []}
        # 用绝对路径调用 CLI，避免 tmux pane 里 PATH 不包含 ~/.local/bin
        engine = sapper._sapper_engine_prefix()
        self.assertEqual(
            sapper._fleet_pane_command(cfg, {"type": "command"}),
            f"{engine} command --root runs --deadline 2026-10-17T13:00:00")
        # auto:<name> 会拼出单题 store 路径 + extra_args
        self.assertEqual(
            sapper._fleet_pane_command(cfg, {"type": "auto:c02", "extra_args": "--verify"}),
            f"{engine} --store runs/c02/.sapper auto --deadline 2026-10-17T13:00:00 --verify")
        # 给了 base_dir 就前置 cd
        self.assertEqual(
            sapper._fleet_pane_command(cfg, {"type": "auto:c02"}, base_dir=Path("/w")),
            f"cd /w && {engine} --store runs/c02/.sapper auto --deadline 2026-10-17T13:00:00")
        # shell 类型原样返回用户命令
        self.assertEqual(
            sapper._fleet_pane_command({"root": "runs", "panes": []}, {"type": "shell", "command": "top"}),
            "top")
        # 未知类型 / shell 缺 command 都必须报错
        with self.assertRaises(sapper.FGError):
            sapper._fleet_pane_command(cfg, {"type": "warp"})
        with self.assertRaises(sapper.FGError):
            sapper._fleet_pane_command(cfg, {"type": "shell"})

    def test_fleet_init_and_load(self):
        """fleet init 写模板且不覆盖已有配置（第二次调用必须报错）。"""
        with tempfile.TemporaryDirectory() as tmp:
            old = Path.cwd()
            try:
                import os
                os.chdir(tmp)                     # init 写相对路径 fleet.json
                args = type("A", (), {"action": "init", "file": "fleet.json"})()
                self.assertEqual(sapper.cmd_fleet(args), 0)
                cfg = sapper._fleet_load(Path("fleet.json"))
                self.assertTrue(cfg["panes"])     # 模板自带 pane 示例
                args2 = type("A", (), {"action": "init", "file": "fleet.json"})()
                with self.assertRaises(sapper.FGError):
                    sapper.cmd_fleet(args2)
            finally:
                os.chdir(old)


class HireFireTests(unittest.TestCase):
    """hire / fire 动作的解析、活跃 worker 探测与题板 worker 列。"""

    def test_parse_command_payload_hire_fire(self):
        """hire/fire 与 work 共用同一解析器，但字段要求不同。"""
        hire = {"accepted": True, "data": {"action": "hire", "target": "c07", "minutes": 30}}
        self.assertEqual(sapper._parse_command_payload(hire), ("hire", "c07", 30, ""))
        fire = {"accepted": True, "data": {"action": "fire", "target": "c07", "note": "stuck"}}
        self.assertEqual(sapper._parse_command_payload(fire), ("fire", "c07", 0, "stuck"))
        # 未知动作 / hire 缺 target / 负数工时都不接受
        with self.assertRaises(sapper.FGError):
            sapper._parse_command_payload({"accepted": True, "data": {"action": "warp", "target": "c"}})
        with self.assertRaises(sapper.FGError):
            sapper._parse_command_payload({"accepted": True, "data": {"action": "hire", "minutes": 10}})
        with self.assertRaises(sapper.FGError):
            sapper._parse_command_payload({"accepted": True, "data": {"action": "hire", "target": "c", "minutes": -1}})

    def test_active_workers_parsing(self):
        """从 tmux 窗口名反推「哪些题已有 worker」：只认 w-<题目> 前缀。

        tmux 不可用（returncode != 0）时必须返回空集合，而不是抛异常
        —— 指挥官在无 tmux 环境下仍应能跑完一次决策。
        """
        with mock.patch.object(sapper, "_tmux") as tm:
            tm.return_value = mock.Mock(returncode=1)      # 模拟 tmux 不可用
            self.assertEqual(sapper._active_workers("nope"), set())
            tm.return_value = mock.Mock(returncode=0, stdout="commander\nw-c01\nw-c07\nboard\n")
            self.assertEqual(sapper._active_workers("s"), {"c01", "c07"})

    def test_board_render_worker_column(self):
        """题板要显示 worker 列，并附一行图例解释 yes 的含义。"""
        rows = [
            {"name": "c01", "status": "active", "flags_submitted": 1, "flags_recorded": 0,
             "kinds": "1 flag", "open_intents": 2, "last_activity": "t", "goal": "g", "worker": "yes"},
            {"name": "c02", "status": "active", "flags_submitted": 0, "flags_recorded": 0,
             "kinds": "-", "open_intents": 0, "last_activity": "t", "goal": "g", "worker": "-"},
        ]
        board = sapper.render_board(rows)
        self.assertIn("worker", board)
        self.assertIn("worker=yes means", board)


import os  # noqa: E402  (KeyRotationTests)
# 说明：模块级导入放在此处是原文件写法，供下方 KeyRotationTests 使用。


class KeyRotationTests(unittest.TestCase):
    """配额/鉴权错误识别与 Key 池轮换。

    比赛环境的现实：Key 会突然欠费/限流，系统必须自动换 Key 继续跑，
    而不是整场停摆。识别不准会造成「误轮换」或「死等」。
    """

    def test_quota_matcher(self):
        """正例：余额不足、401、欠费；反例：网络超时、参数错误。"""
        self.assertTrue(sapper._is_quota_error("insufficient balance (quota exceeded)"))
        self.assertTrue(sapper._is_quota_error("Error 401: Unauthorized"))
        self.assertTrue(sapper._is_quota_error("账户欠费，请充值"))
        self.assertFalse(sapper._is_quota_error("connection timed out"))
        self.assertFalse(sapper._is_quota_error("claude exited 2: bad args"))

    def test_pool_load_and_rotate(self):
        """轮换语义：多组凭据依次切换（base_url/token/model 一起换）；
        坏 JSON 返回空池；空池不轮换；单元素池轮换但不改值。
        """
        pool_json = json.dumps([
            {"base_url": "http://a", "token": "t1", "model": "m1"},
            {"base_url": "http://b", "token": "t2", "model": "m2"},
        ])
        with mock.patch.dict("os.environ", {
            "SAPPER_KEY_POOL": pool_json, "ANTHROPIC_AUTH_TOKEN": "t1",
            "ANTHROPIC_BASE_URL": "http://a", "SAPPER_MODEL": "m1"}):
            self.assertTrue(sapper._rotate_key())
            # 三项一起切到池中下一组（不能只换 token 却留着旧 base_url）
            self.assertEqual(os.environ["ANTHROPIC_AUTH_TOKEN"], "t2")
            self.assertEqual(os.environ["ANTHROPIC_BASE_URL"], "http://b")
            self.assertEqual(os.environ["SAPPER_MODEL"], "m2")
        # 池配置非法 → 当作空池，不抛异常
        with mock.patch.dict("os.environ", {"SAPPER_KEY_POOL": "not json"}):
            self.assertEqual(sapper._load_key_pool(), [])
        # 空池 → 不轮换
        with mock.patch.dict("os.environ", {"SAPPER_KEY_POOL": ""}):
            self.assertFalse(sapper._rotate_key())
        # single-entry pool: rotate returns True but keeps the key
        # 注释：单元素池视为「轮换成功但值不变」，避免调用方误判为失败后反复重试
        with mock.patch.dict("os.environ", {
            "SAPPER_KEY_POOL": json.dumps([{"base_url": "http://a", "token": "t1"}]),
            "ANTHROPIC_AUTH_TOKEN": "t1"}):
            self.assertTrue(sapper._rotate_key())
            self.assertEqual(os.environ["ANTHROPIC_AUTH_TOKEN"], "t1")
