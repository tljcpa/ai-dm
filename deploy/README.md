# 部署说明（Day 5 实际执行的步骤）

本项目以 `aidm.zdwktlj.top` 上线，部署在自有 Ubuntu 20.04 服务器。
本目录记录实际生效的配置文件副本（服务器上 /etc/... 的原件），便于面试官查阅完整部署链路。

## 服务器现状（部署前探测，仅作记录）

- Ubuntu 20.04.6 LTS，Python 3.8.10，Node 20.20.2，Nginx + Postgres + snapd 已装
- 内存仅 1.0G 可用——必须轻量部署
- 服务器上已跑 4+ 个其他业务项目（cad-agent / aihub / hr-* / partner-cashier），**避免影响**

## 端口与路径分配

- 后端 uvicorn：`127.0.0.1:9001`（不暴露公网）
- 前端静态：`/var/www/ai-dm/`（Vite build dist）
- 后端代码：`/root/ai-dm/`（venv 在 `venv/`）
- 数据库：SQLite `/root/ai-dm/app.db`（不占用现有 Postgres）
- RAG 索引：`/root/ai-dm/data/rag_index.pkl`（首次启动构建，pickle 持久化）

## 部署步骤（按时间顺序）

1. **本机** 前端 `npm run build` 生成 dist/
2. **本机** rsync 后端代码到服务器 `/root/ai-dm/`
3. **本机** rsync 前端 dist 到服务器 `/var/www/ai-dm/`
4. **本机** scp 生产 `.env` 到服务器 `/root/ai-dm/.env`（chmod 600）
   - 新 SECRET_KEY 用 `openssl rand -hex 32` 生成
   - DEEPSEEK_API_KEY / ZHIPU_API_KEY 复用开发期 key（demo 项目不严格隔离）
5. **服务器** 创建 venv + `pip install -r requirements.txt`
6. **服务器** 写 `/etc/systemd/system/ai-dm.service`（本目录的 `ai-dm.service`）
   - `systemctl daemon-reload && systemctl enable --now ai-dm`
7. **服务器** 写 `/etc/nginx/sites-available/ai-dm`（本目录的 `ai-dm.nginx`）
   - `ln -sf .../sites-available/ai-dm .../sites-enabled/`
   - `nginx -t && systemctl reload nginx`
8. **服务器** 配 DNS A 记录 `aidm.zdwktlj.top → 154.89.153.171`
9. **服务器** 装 certbot（Ubuntu 20.04 仓库版有兼容性 bug，**用 snap**）：
   ```
   snap install --classic certbot
   ln -sf /snap/bin/certbot /usr/bin/certbot
   ```
10. **服务器** 申请 HTTPS：
    ```
    certbot --nginx -d aidm.zdwktlj.top --non-interactive --agree-tos --email <email> --redirect
    ```

## 部署期间踩的两个坑（也是 Day 5 决策的来源）

### 坑 1：Python 3.8 兼容性（D-022）

本机 Python 3.10 写代码不假思索用了 PEP 604 / PEP 585 语法（`list[str]` / `Annotated`），
部署到服务器 Python 3.8 直接 ImportError。

**修复**：
- `Annotated` 改从 `typing_extensions` 导入（pydantic 已带这个依赖）
- `list[X]` / `tuple[X,Y]` 全改成 `List[X]` / `Tuple[X,Y]`（PEP 585 lowercase 3.9+ 才支持）
- numpy 约束 `>=1.21,<2`（Python 3.8 最高拿到 1.24.x）

### 坑 2：certbot 旧版 OpenSSL API 不兼容（D-023）

Ubuntu 20.04 `apt install certbot` 装的是 0.40.0（2019 年的），
与新版 cryptography 库 API 不兼容，跑 `certbot --nginx` 直接 AttributeError。

**修复**：用 snap 装最新 certbot（5.6.0）。
**教训**：Ubuntu 20.04 仓库的 certbot 别用，certbot 官方明确推荐 snap 装法。

## 验证清单

- `systemctl is-active ai-dm.service` → active
- `systemctl is-active nginx` → active
- `curl https://aidm.zdwktlj.top/` → 返回 index.html
- `curl https://aidm.zdwktlj.top/api/health` → `{"status":"ok"}`
- HTTPS 证书：`/etc/letsencrypt/live/aidm.zdwktlj.top/fullchain.pem`，2026-08-13 到期
- 自动续期：`systemctl list-timers | grep certbot` → certbot.timer

## 资源占用（生产实测）

- `ai-dm.service` 内存 ~80 MB（uvicorn 单 worker + RAG 索引）
- 单回合延迟：3.5-5s（含 RAG 嵌入 + LLM + Nginx 转发）
- 不动现有 Postgres / 不和其他 systemd 服务冲突 / 不占用 80 端口（共享 Nginx）
