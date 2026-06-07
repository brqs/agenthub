# Frontend Capacitor Shell Spec

## 目标

使用 Capacitor v8 包装现有 `frontend/dist/`，生成 iOS / Android 原生壳。Web、PWA 和原生 App 继续复用同一套 React 页面、真实 API 与 SSE 客户端。

## 输入 / 输出

输入：

- `frontend/dist/`
- 构建时环境变量 `VITE_API_BASE_URL`
- 现有移动 Web 布局、PWA 与真实 API 客户端

输出：

- `frontend/capacitor.config.ts`
- `frontend/ios/`
- `frontend/android/`
- 原生壳初始化、Android 返回键和外链打开桥接
- 原生构建与同步脚本

## 边界 / 错误处理

- 原生构建必须提供完整 HTTPS `VITE_API_BASE_URL`，不能依赖 Vite `/api` 代理。
- 原生壳不缓存 API、SSE、消息或 Workspace 数据。
- Android 返回键依次关闭 Workspace / 会话 sheet、设置页、账号菜单；没有浮层时返回浏览历史；没有历史时退出 App。
- 部署地址、网页预览、文件地址和 Markdown 外链在原生端通过 Capacitor Browser 打开。
- zip 下载暂时保留现有 Blob 下载实现，必须在 iOS / Android 真机验收；若 WebView 行为不满足需求，再引入 Filesystem / File Transfer。
- 文件上传第一版优先复用 Web `<input type="file">` / multipart；只有 iOS / Android WebView 无法稳定读取文件字节或保存下载时，才引入原生 picker / Filesystem / File Transfer 桥接。
- HTTPS、CORS、公开预览和下载地址可访问性属于部署 / B1 协作项，不在 F 单独修改范围。

## 文件上传桥接规划

完整产品/后端契约见 [../../spec/next-major-modules.spec.md](../../spec/next-major-modules.spec.md)。

Web / PWA：

- 桌面端支持拖拽、粘贴图片和文件选择。
- 移动 Web 使用浏览器文件选择器，不依赖拖拽。
- 上传使用 `multipart/form-data`，发送消息只引用 `upload_id`。

iOS Capacitor：

- 优先验证 WebView 中 `<input type="file">` 对图片、文档和压缩包的表现。
- 若 WebView 读取不稳定，引入原生文档/相册选择器，将文件复制到 app cache 后上传。
- 大文件不走 base64 字符串，避免 JS 内存峰值；优先使用文件 URI 流式上传。
- 尊重相册 limited access 和系统权限提示。

Android Capacitor：

- 优先验证浏览器/ WebView 的文件选择和 Android Photo Picker / Document Provider。
- 原生桥接需要正确处理 `content://` URI，必要时申请持久读取权限。
- 大文件或压缩包应从 URI/cache 文件流式上传，不一次性读入 JS。
- 如果系统 provider 返回无法打开的虚拟文件，前端展示可理解错误并允许重新选择。

共同约束：

- 原生桥接不得复制 React 业务逻辑，只提供文件选择、读取、上传/下载能力。
- 上传后由 B1 做 MIME、大小、hash、archive safe extraction 校验；前端校验只做即时提示。
- Workspace 导入压缩包必须由用户显式确认，不能因为上传完成自动解压。

## 性能要求

- 不复制 React 业务代码。
- 原生桥接只在 Capacitor 平台初始化。
- Web 与 PWA 运行时不加载额外行为。

## 依赖

- `@capacitor/core`
- `@capacitor/cli`
- `@capacitor/ios`
- `@capacitor/android`
- `@capacitor/app`
- `@capacitor/browser`
- `@capacitor/keyboard`

## 验收标准

- `pnpm cap:add` 可生成 iOS / Android 工程。
- `VITE_API_BASE_URL=https://... pnpm cap:sync` 可构建 Web bundle 并同步原生工程。
- 未配置 HTTPS API 时，`pnpm build:native` 明确失败。
- Web 端类型检查、Lint、测试和生产构建通过。
- iOS / Android 模拟器或真机完成 HTTPS API、SSE、外链、下载、安全区、软键盘和返回键验收。
