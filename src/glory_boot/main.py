import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Sequence

from PySide6.QtWidgets import QMessageBox

from glory_boot.adapters.codex_runtime import (
    CodexRuntimeStore,
    refresh_runtime_store,
)
from glory_boot.adapters.skin_profiles import load_skin_profiles
from glory_boot.config import ConfigError, load_config
from glory_boot.diagnostics import StageTimer
from glory_boot.ui.application import LauncherApplication, create_qt_application


_PROCESS_START = time.perf_counter()


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _configure_logging(root: Path) -> logging.Logger:
    logger = logging.getLogger("glory_boot")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    log_dir = root / "logs"
    log_dir.mkdir(exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    file_handler = logging.FileHandler(
        log_dir / "launcher.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv)
    parser = argparse.ArgumentParser(prog="glory-boot")
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--disable-skin", action="store_true")
    options, qt_arguments = parser.parse_known_args(arguments[1:])

    root = _runtime_root()
    logger = _configure_logging(root)
    timer = StageTimer(start=_PROCESS_START, logger=logger)
    qt_app = create_qt_application([arguments[0], *qt_arguments])
    timer.mark("qt_ready")

    try:
        config = load_config(root)
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        runtime_store = CodexRuntimeStore(
            local_app_data / "GloryCodexBoot" / "codex-runtime.json"
        )
        runtime_install = refresh_runtime_store(runtime_store)
        if runtime_install is not None:
            timer.mark("codex_runtime_refreshed")
        application = LauncherApplication(
            root=root,
            config=config,
            qt_app=qt_app,
            timer=timer,
            benchmark=options.benchmark,
            skin_disabled_by_cli=options.disable_skin,
            skin_profiles=load_skin_profiles(),
            runtime_store=runtime_store,
        )
        exit_code = application.run(benchmark=options.benchmark)
        if options.benchmark:
            benchmark_path = root / "logs" / "benchmark.json"
            benchmark_path.write_text(
                json.dumps(timer.marks, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return exit_code
    except ConfigError as exc:
        logger.error("configuration_error error=%s", exc)
        QMessageBox.critical(None, "Codex 荣耀启动器", str(exc))
        return 2
    except Exception as exc:
        logger.exception(
            "top_level_failure error_type=%s",
            type(exc).__name__,
        )
        QMessageBox.critical(
            None,
            "Codex 荣耀启动器",
            "启动器遇到错误，但不会修改 Codex 数据。请查看 logs\\launcher.log。",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
