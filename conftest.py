"""项目根 conftest — 早于 ``tests/conftest.py`` 执行。

只做一件事：在 pytest 收集到任何用例之前，把 ``TMP`` / ``TEMP`` / ``TMPDIR``
三个环境变量重定向到仓库根 ``.pytest_tmp/``。

为什么：
    Windows 默认 pytest 会用 ``%TEMP%\\pytest-of-<user>\\...``，在某些受限
    账户（CI 容器、共享机器）会因权限失败。把临时目录固定到项目内部避免
    跨账号 / 跨机器的权限问题，也便于一次性 ``rm -rf .pytest_tmp`` 清理。

``tests/conftest.py`` 会在此基础上再细分 per-test 子目录（``run-<pid>-<uuid>``），
本文件只负责"根级别重定向"，不要在此加用例 hook。
"""

import os
from pathlib import Path

_workspace_tmp = (Path(__file__).resolve().parent / ".pytest_tmp").resolve()
_workspace_tmp.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(_workspace_tmp)
os.environ["TEMP"] = str(_workspace_tmp)
os.environ["TMPDIR"] = str(_workspace_tmp)
