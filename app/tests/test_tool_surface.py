"""M113-I336 剪枝回归锁：非功能性 stub 工具（search_web/publish_external/
run_command）已出注册表——权限面对外只暴露真实能力，deny-by-default 名副其实
（M45 权限面收窄同向）。危险档语义由 create_git_tag 真实审批流承载；V2 沙箱
承诺保留在 docs/07 roadmap。"""
import pytest

from apm.runtime.tools import PERMISSIONS, ToolContext, ToolDenied, execute


def test_pruned_stub_tools_deny_by_default():
    for name in ("search_web", "publish_external", "run_command"):
        assert name not in PERMISSIONS
        ctx = ToolContext(project_id="p_x", run_id="r_x")
        with pytest.raises(ToolDenied, match="not registered"):
            execute(name, {}, ctx)


def test_permission_surface_is_exactly_the_real_capabilities():
    assert set(PERMISSIONS) == {
        "read_artifact", "list_artifacts", "search_assets", "read_asset",
        "write_artifact", "link_asset", "create_git_tag",
    }
