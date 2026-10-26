"""R1 层二退役守卫（ADR 0018）。

层二把 ZWorkbench 本地 UI 实现层整体剥离：20 个 ``ui_*`` 模块、包顶层重导出与
CLI 宿主命令全部下线，产品 UI 面由 Go 后端 + React 前端承担。

这个文件只做一件事——断言它们**没有回流**。它是层二的唯一自动化证据：
新增任何 ``src/zworkbench/ui_*.py``、恢复包顶层重导出或把 CLI 宿主命令加回来，
都会在这里变红，而不是等到某天有人重新运行一个已退役的入口。
"""

from __future__ import annotations

import importlib.util
import unittest

#: 层二删除的 20 个模块（ADR 0018 Decision「层二」清单）。
RETIRED_MODULES = (
    "ui_approval",
    "ui_build",
    "ui_declare",
    "ui_home",
    "ui_host",
    "ui_live",
    "ui_manifest",
    "ui_matrix",
    "ui_reconcile",
    "ui_record_view",
    "ui_ref",
    "ui_review",
    "ui_run",
    "ui_runtime",
    "ui_scenario_state",
    "ui_script",
    "ui_style",
    "ui_task_detail",
    "ui_token",
    "ui_view_model",
)

#: 层二从 ``zworkbench`` 包顶层撤掉的重导出（每个模块各取代表符号）。
RETIRED_EXPORTS = (
    "UI_REF_SCHEMA",
    "UiRefRegistry",
    "resolve_ui_ref",
    "ReviewSession",
    "audit_rendered_html",
    "RECEIPT_SCHEMA",
    "build_receipt",
    "load_manifest",
    "TOKEN_PROTOCOL",
    "build_token",
    "parse_deep_link",
    "MATRIX",
    "coverage_report",
    "record_manifest",
    "render_task_detail",
    "HOST_SURFACES",
    "ReviewMode",
)

#: 层二从 ``zworkbench.cli`` 撤掉的宿主入口与辅助函数。
RETIRED_CLI_SYMBOLS = (
    "_ui_command",
    "_ui_host_command",
    "_ui_ref_command",
    "_ui_ref_payload",
    "_ui_build_command",
    "_announce",
)


class R1Layer2RetirementTests(unittest.TestCase):
    def test_ui_implementation_modules_are_gone(self) -> None:
        for name in RETIRED_MODULES:
            with self.subTest(module=name):
                self.assertIsNone(
                    importlib.util.find_spec("zworkbench." + name),
                    "R1 层二已退役 {0}，实现模块不得回流".format(name),
                )

    def test_package_reexports_drop_r1_symbols(self) -> None:
        import zworkbench

        for name in RETIRED_EXPORTS:
            with self.subTest(symbol=name):
                self.assertNotIn(name, zworkbench.__all__)
                self.assertFalse(
                    hasattr(zworkbench, name),
                    "zworkbench 不得再导出 {0}".format(name),
                )

    def test_cli_has_no_r1_host_handlers(self) -> None:
        from zworkbench import cli

        for name in RETIRED_CLI_SYMBOLS:
            with self.subTest(symbol=name):
                self.assertFalse(
                    hasattr(cli, name),
                    "zworkbench.cli 不得再有 {0}".format(name),
                )

    def test_product_surfaces_still_import(self) -> None:
        # 退役不能顺手把产品面带走：Go 后端契约用到的核心模块必须仍可导入。
        import zworkbench
        from zworkbench import cli  # noqa: F401
        from zworkbench.composition import CompositionOwner  # noqa: F401
        from zworkbench.worker_contract import WorkerEnvelope  # noqa: F401

        self.assertTrue(callable(cli.main))
        self.assertIn("CompositionOwner", zworkbench.__all__)


if __name__ == "__main__":
    unittest.main()
