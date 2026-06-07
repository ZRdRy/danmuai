"""Shared provider HTTP constants (avoid circular imports with ai_client).

独立模块原因：``THINKING_DISABLED`` 同时被 ``ai_client`` 与 ``providers/adapters`` 引用，
将其放在最底层（不导入 PyQt、不导入 ai_client）可避免循环依赖。
"""

# 固定思考关闭 payload：所有请求都发此 body，确保不会回传 reasoning_content。
# 详见 docs/ai-project-context.md「思考模式」一节。
THINKING_DISABLED = {"type": "disabled"}
