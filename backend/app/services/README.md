# Service Package

`app.services` 按领域组织平台 service。根目录只保留被 API、stream 或多个领域直接依赖的主要入口；辅助实现放入领域 package。

## 根目录主入口

- `model_gateway.py`：模型网关与 compression provider 配置。
- `context_builder.py`：conversation context 构建入口。
- `orchestrator_memory.py`：Orchestrator memory 稳定兼容门面。
- `orchestrator_platform_tools.py`：Orchestrator 平台工具入口。
- `workspace_service.py`：workspace 文件访问边界。
- `workspace_preview.py`：workspace preview 生命周期入口。
- `workspace_deployment.py`：workspace deployment 生命周期入口。
- `workspace_workflow_runtime.py`：workspace workflow runtime 入口。

## 领域 Package

- `artifacts/`：artifact manifest 与 metadata。
- `context/`：context compression 等辅助实现。
- `workspace/`：preview verifier、container release、deployment workers、janitor 与 static snapshot/release/server。
- `_orchestrator_memory/`：`orchestrator_memory.py` 门面后的私有实现。

新增 service 时，优先放入已有领域 package；只有跨领域主要入口或需要稳定导入门面的 service 才放在根目录。

领域辅助模块使用新的 package 路径，旧的平铺辅助模块路径不保留 facade；仓库内调用方应直接导入所属领域模块。
