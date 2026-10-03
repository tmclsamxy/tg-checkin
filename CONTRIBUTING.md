# 贡献指南

感谢你愿意为 TG Checkin 做贡献。

## 开发流程

1. Fork 本仓库并新建分支：`git checkout -b feat/your-feature`
2. 完成修改并确保测试通过
3. 提交 PR，描述清楚改动动机与验证方式

## 本地开发

```bash
# 后端
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && pytest -q                 # 单元测试
cd .. && uvicorn backend.app.main:app --reload --port 8000

# 前端（自带代理到 :8000，支持热更新）
cd frontend && npm install && npm run dev
```

调试模式下建议设置 `DEBUG=true`，可以打开 `/api/docs`。

## 代码约定

**后端（Python）**

- 目标 Python 3.11+，类型注解齐全
- 格式化与静态检查：`ruff format` / `ruff check`（若已安装）
- 新增接口要在 `backend/tests/` 中补测试
- 任何密钥都不允许明文落库，统一走 `app/security.py` 的 `encrypt_secret`
- 数据库改动要考虑旧库升级（`app/database.py` 里的轻量列迁移）

**前端（Vue 3）**

- 使用 `<script setup>` 组合式 API
- 样式统一写在 `src/styles.css` 的 CSS 变量体系下，不引入额外 UI 框架
- 组件保持单一职责，通用组件放 `src/components/`

**提交信息**

使用 Conventional Commits 风格，例如：

```
feat(tasks): 支持按回调数据点击按钮
fix(telegram): 修复两步验证登录失败
docs(readme): 补充反代配置示例
```

## 提交 Issue

请附上：

- 系统 / Docker 版本、Python 版本
- 复现步骤
- 后端日志（`./scripts/deploy.sh logs`）
- 已脱敏的配置信息（**不要贴 API Hash、Bot Token、手机号**）

## 安全漏洞

请勿在公开 Issue 中披露安全问题，请通过 GitHub Security Advisory 私下联系维护者。
