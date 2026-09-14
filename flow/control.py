"""Control agent: the persistent conversation node orchestrating the run."""

from __future__ import annotations

from flow import constants as C
from flow import prompts
from flow.config import PipelineConfig
from flow.driver import BackendDriver
from flow.paths import RunPaths


def control_node_config(project, run: RunPaths, cfg: PipelineConfig):
    """Build a NodeConfig-like object for the control node."""
    from flow.config import NodeConfig

    return NodeConfig(
        name=C.CONTROL_NODE,
        agent=C.CONTROL_NODE,
        backend=cfg.control_backend,
        task="常驻总控：回答用户关于流水线进展的问题，并代为执行编排干预",
    )


def prepare_control_files(run: RunPaths, project, cfg: PipelineConfig) -> None:
    ndir = run.node_dir(C.CONTROL_NODE)
    ndir.mkdir(parents=True, exist_ok=True)
    src = project.agent_def_dir(C.CONTROL_NODE) / C.AGENT_MD
    if not src.is_file():
        raise FileNotFoundError(
            f"control agent definition missing: {src} (required when control: true)"
        )
    dst = run.node_agent_md(C.CONTROL_NODE)
    if not dst.exists():
        dst.write_text(
            src.read_text()
            + "\n\n"
            + prompts.control_system_prompt(
                pipeline_name=cfg.name,
                flow_yaml_content=project.pipeline_file.read_text(),
                run_root=str(run.root),
                status_help="运行 `flow status` 查看各节点状态。",
                cli_help="\n".join(
                    [
                        "- flow status：查看状态",
                        "- flow approve <node>：放行人工门节点",
                        "- flow retry <node>：重置节点为待运行",
                        "- flow inject <node> <message>：向运行中节点投递补充指令",
                        "- flow log <node>：查看节点完整终端记录",
                        "- flow stop：停止流水线",
                    ]
                ),
            )
        )


def launch_control(run: RunPaths, project, cfg: PipelineConfig, driver: BackendDriver) -> None:
    """Start the control window and deliver its opening prompt."""
    from flow import session as tmux

    node = C.CONTROL_NODE
    ncfg = control_node_config(project, run, cfg)
    driver.prepare(node, ncfg)
    prepare_control_files(run, project, cfg)
    if not tmux.window_exists(run, node):
        if tmux.has_session(run.tmux_session_name):
            tmux.new_window(
                run, 0, node, driver.launch_command(node, ncfg), project.workdir
            )
        else:
            tmux.new_session(
                run.tmux_session_name,
                run,
                node,
                driver.launch_command(node, ncfg),
                project.workdir,
            )
    log = run.node_tty_log(node)
    log.touch()
    tmux.pipe_pane(run, node, log)
    driver.send_prompt(
        node,
        "你好，我是本流水线的总控 agent。请先自我介绍并运行 `flow status` 汇报当前流水线状态，然后等待用户指令。",
    )
