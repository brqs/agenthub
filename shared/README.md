# shared/ — 前后端共享契约

## openapi.yaml

**唯一真相源**。任何 API 变更必须先改这里。

### 前端生成 TS 类型

```bash
cd frontend
pnpm gen:types
# 会生成 src/lib/types.ts
```

底层使用 [openapi-typescript](https://github.com/openapi-ts/openapi-typescript)。

### 后端校验

后端通过 FastAPI 的 Pydantic Schema 自动生成 OpenAPI 文档（访问 `/openapi.json`）。
要保证 `shared/openapi.yaml` 与后端实际暴露的一致。

### 变更流程

1. 修改 `openapi.yaml`
2. 在 PR 描述中标注「契约变更」
3. 前端运行 `pnpm gen:types`
4. 后端的 Pydantic Schema 与之对齐
5. 至少 1 人 Review
6. 合并到 main 后，所有人 git pull + 重生类型
