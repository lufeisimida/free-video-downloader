# 🚀 AI 万能视频下载总结器 - 生产环境部署指南

> 适用服务器：Ubuntu 24.04 | 2核 CPU | 2GB 内存 | 40G 系统盘 | 15Mbps 带宽 | 1 个公网 IP
> 项目：`free-video-downloader`（FastAPI + Vue 3 + yt-dlp + faster-whisper + OpenAI 兼容 LLM）

---

## 📋 部署架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                      公网 IP (15Mbps)                        │
│                           │                                 │
│                    ┌──────┴──────┐                           │
│                    │   Nginx     │  端口 80/443              │
│                    │  反向代理    │  静态文件 / SSL 终结      │
│                    └──────┬──────┘                           │
│           ┌──────────────┼──────────────┐                    │
│           ▼              ▼              ▼                    │
│      ┌─────────┐   ┌───────────┐  ┌──────────┐              │
│      │ Frontend│   │  Backend  │  │  SQLite  │              │
│      │  (Nginx)│   │ (Gunicorn)│  │ (app.db) │              │
│      │  静态站  │   │  :8000    │  │  文件库  │              │
│      └─────────┘   └───────────┘  └──────────┘              │
│                        │                                     │
│                 ┌──────┴──────┐                              │
│                 │  yt-dlp /   │                              │
│                 │  Whisper    │                              │
│                 │  (本地二进制) │                              │
│                 └─────────────┘                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🖥️ 服务器资源规划（2C2G 关键决策）

| 组件 | 内存占用 | 说明 |
|------|----------|------|
| **系统基础** | ~300 MB | Ubuntu 24.04 最小安装 |
| **Nginx** | ~20 MB | 静态文件 + 反向代理 |
| **Gunicorn (2 workers)** | ~400 MB | `2 workers × ~200MB`，避免 OOM |
| **Python (FastAPI + yt-dlp)** | ~150 MB | 运行时 + 依赖 |
| **faster-whisper (small, int8, beam=10)** | ~550 MB | 模型加载到内存，**最大单块**，含 beam search 缓冲 |
| **ffmpeg 临时缓冲** | ~100 MB | 音视频合并时 |
| **剩余缓冲** | ~500 MB | 留给 OS 缓存、网络缓冲 |
| **合计** | **~1.55 GB** | **安全 margin ~450 MB** |

> ⚠️ **关键限制**：2GB 内存**跑不了** `WHISPER_MODEL=medium` 或 `large`，必须用 `small` 或 `base`；Gunicorn workers 设为 **2**，不要贪多。

---

## 📦 第一阶段：服务器基础环境准备

### 1.1 更新系统 & 安装基础包
```bash
# 以 root 或 sudo 用户执行
apt update && apt upgrade -y

# 安装必须工具
apt install -y \
    git curl wget unzip \
    python3 python3-venv python3-pip \
    nginx \
    ffmpeg \
    htop net-tools ufw \
    logrotate
```

### 1.2 配置防火墙
```bash
# 仅开放必要端口
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP
ufw allow 443/tcp     # HTTPS
ufw --force enable
ufw status
```

### 1.3 创建部署用户（不使用 root 运行应用）
```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
# 切换到 deploy 用户后续操作
su - deploy
```

### 1.4 配置时区 & 语言
```bash
sudo timedatectl set-timezone Asia/Shanghai
sudo locale-gen zh_CN.UTF-8
```

---

## 🐍 第二阶段：后端部署

### 2.1 克隆代码 & 创建虚拟环境
```bash
cd /home/deploy
git clone https://gitee.com/luffywj/free-video-downloader.git
cd free-video-downloader/backend

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
# 额外安装生产级 WSGI 服务器
pip install gunicorn
```

### 2.2 创建生产环境配置文件
```bash
cp .env.example .env
```

**编辑 `/home/deploy/free-video-downloader/backend/.env`**：

```env
# ============ 必填：LLM 配置 ============
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
LLM_MODEL=gpt-4o-mini

# ============ Whisper 语音转写（2G 内存最优配置） ============
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_LANGUAGE=zh
WHISPER_BEAM_SIZE=10
# 国内服务器建议配置镜像加速
WHISPER_HF_ENDPOINT=https://hf-mirror.com

# ============ 业务开关 ============
DISABLE_SUMMARY_PAYWALL=false
SUPERUSER_EMAILS=admin@yourdomain.com
PAYMENT_ENABLED=true
REGISTRATION_ENABLED=true

# ============ 安全：必须修改 ============
JWT_SECRET=your-super-strong-random-string-64-chars-minimum

# ============ Stripe（可选） ============
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRICE_ID_MONTHLY=price_xxx

# ============ 前端域名（支付回跳用） ============
FRONTEND_URL=https://yourdomain.com

# ============ 文件上传限制 ============
MAX_LOCAL_UPLOAD_BYTES=2147483648
```

> 💡 生成强 JWT_SECRET：`openssl rand -base64 48`

### 2.3 创建数据目录 & 初始化数据库
```bash
mkdir -p /home/deploy/free-video-downloader/backend/data
mkdir -p /home/deploy/free-video-downloader/backend/downloads
mkdir -p /home/deploy/free-video-downloader/backend/logs

# 初始化数据库（会自动建表）
cd /home/deploy/free-video-downloader/backend
source venv/bin/activate
python -c "from database import init_db; init_db(); print('DB initialized')"
```

### 2.4 编写 Gunicorn 启动配置
创建 `/home/deploy/free-video-downloader/backend/gunicorn.conf.py`：
```python
# gunicorn.conf.py
import multiprocessing

bind = "127.0.0.1:8000"
workers = 2                    # 2C2G 核心设置：2 workers
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 100
max_requests = 1000
max_requests_jitter = 50
timeout = 120                  # yt-dlp 下载可能较慢
graceful_timeout = 30
keepalive = 5

# 内存管理
preload_app = True             # 预加载减少内存占用
worker_tmp_dir = "/dev/shm"    # 使用内存盘加速临时文件

# 日志
accesslog = "/home/deploy/free-video-downloader/backend/logs/access.log"
errorlog = "/home/deploy/free-video-downloader/backend/logs/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 进程管理
pidfile = "/home/deploy/free-video-downloader/backend/gunicorn.pid"
daemon = False                 # systemd 管理守护，此处 False
user = "deploy"
group = "deploy"

# 安全
limit_request_fields = 100
limit_request_field_size = 8190
limit_request_line = 4094
```

### 2.5 创建 systemd 服务文件
```bash
sudo tee /etc/systemd/system/video-downloader-backend.service > /dev/null <<'EOF'
[Unit]
Description=Video Downloader Backend (FastAPI + Gunicorn)
After=network.target

[Service]
Type=notify
User=deploy
Group=deploy
WorkingDirectory=/home/deploy/free-video-downloader/backend
Environment=PATH=/home/deploy/free-video-downloader/backend/venv/bin
ExecStart=/home/deploy/free-video-downloader/backend/venv/bin/gunicorn -c gunicorn.conf.py main:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=30
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=video-downloader-backend

# 资源限制（防止内存溢出）
MemoryLimit=1600M
CPUQuota=180%

# 安全加固
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/home/deploy/free-video-downloader/backend/data
ReadWritePaths=/home/deploy/free-video-downloader/backend/downloads
ReadWritePaths=/home/deploy/free-video-downloader/backend/logs
ReadWritePaths=/dev/shm

[Install]
WantedBy=multi-user.target
EOF
```

### 2.6 启动并验证后端
```bash
sudo systemctl daemon-reload
sudo systemctl enable video-downloader-backend
sudo systemctl start video-downloader-backend
sudo systemctl status video-downloader-backend

# 验证 API
curl http://127.0.0.1:8000/api/health
# 应返回 {"status":"ok","message":"万能视频下载器服务运行中"}
```

---

> 创建用户
>
> curl -X POST http://127.0.0.1:8000/api/auth/register \
>   -H "Content-Type: application/json" \
>   -d '{"email":"2823629661@qq.com","username":"testuser","password":"Lufeil224!!","confirm_password":"Lufeil224!!"}'



## 🌐 第三阶段：前端构建 & Nginx 配置

### 3.1 构建前端生产包
```bash
cd /home/deploy/free-video-downloader/frontend

# 创建生产环境变量
cat > .env.production <<'EOF'
VITE_API_BASE_URL=/api
VITE_PAYMENT_ENABLED=true
EOF

# 安装依赖 & 构建
npm config set registry https://registry.npmmirror.com
npm install
npm run build

# 构建产物在 dist/ 目录
ls -la dist/
```

> 好的，现在您已经是 `root` 用户，可以自由安装软件了。当前的问题是 `npm` 未安装，直接执行 `apt install npm` 即可解决。
>
> ### 完整步骤（推荐）
>
> 1. **更新软件包列表并安装 Node.js 和 npm**（同时安装，避免版本不匹配）：
>    ```bash
>    apt update
>    apt install -y nodejs npm
>    ```
>
> 2. **验证安装**：
>    ```bash
>    node -v   # 查看 Node.js 版本
>    npm -v    # 查看 npm 版本
>    ```
>
> 3. **在项目目录安装依赖**（您已经在 `/home/deploy/free-video-downloader/frontend`，直接运行）：
>    ```bash
>    npm install
>    ```
>
> 4. **如果项目需要构建（比如 React/Vue 等）**，通常还需要执行：
>    ```bash
>    npm run build
>    ```
>    这会生成静态文件（如 `dist/` 或 `build/` 目录），用于后续部署到 Web 服务器。
>
> ---
>
> ### 版本说明
> - Ubuntu/Debian 默认仓库的 Node.js 版本可能较旧（如 v12），若您的项目需要更高版本（如 v16+），建议使用 **NodeSource** 或 **nvm** 安装。  
>   如果需要最新版，可以改用以下方式（可选）：
>   ```bash
>   curl -fsSL https://deb.nodesource.com/setup_18.x | bash -   # 以 Node.js 18 为例
>   apt install -y nodejs   # 此命令会自动安装 npm
>   ```
>
> ---
>
> ### 后续建议
> - 安装完成后，如果您打算通过 Systemd 启动前端服务（比如用 `serve` 或 `pm2` 等），可以另行配置。
> - 如果只是构建静态文件，构建完成后将 `build/` 目录内容复制到 Nginx/Apache 的网站根目录即可。
>
> 现在您可以直接运行上述命令，继续您的前端部署工作了。

> 明白了，您当前 Node.js 版本（18.19.1）不满足 Vite 的要求（需要 20.19+ 或 22.12+）。由于您已是 `root`，可以轻松升级。
>
> ---
>
> ### 推荐方案：使用 NodeSource 安装 Node.js 20 LTS（最稳定）
>
> 1. **卸载旧版本（可选，但推荐避免冲突）**：
>    ```bash
>    apt remove -y nodejs npm
>    apt autoremove -y
>    ```
>
> 2. **添加 NodeSource 的 Node.js 20 仓库并安装**：
>    ```bash
>    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
>    apt install -y nodejs
>    ```
>    > 该脚本会自动配置 apt 源，并安装 Node.js 20 及配套的 npm。
>
> 3. **验证版本**：
>    ```bash
>    node -v   # 应显示 v20.x.x
>    npm -v    # 应显示对应版本
>    ```
>
> ---
>
> ### 如果您想使用 Node.js 22（最新稳定版）：
> 将上述命令中的 `setup_20.x` 改为 `setup_22.x` 即可。
>
> ---
>
> ### 升级后重新构建前端
>
> 因为版本跨度较大，建议清理旧依赖并重新安装，以防缓存问题：
>
> ```bash
> cd /home/deploy/free-video-downloader/frontend
> rm -rf node_modules package-lock.json   # 删除旧依赖
> npm install                              # 重新安装
> npm run build                            # 构建生产版本
> ```
>
> ---
>
> ### 补充说明
> - **如果您的项目使用 `pnpm` 或 `yarn`**，同样需要检查其版本兼容性，但最稳妥的是使用 npm。
> - 构建完成后，生成的静态文件通常在 `dist/` 或 `build/` 目录，您后续可以将其部署到 Nginx 等 Web 服务器。
>
> 现在执行上述命令即可解决问题。如果还有任何报错，请将错误信息发给我，我会协助排查。

### 3.2 配置 Nginx（反向代理 + 静态托管 + SSL）

```bash
sudo tee /etc/nginx/sites-available/video-downloader > /dev/null <<'NGINX_CONF'
# HTTP -> HTTPS 强制跳转
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS 主站点
server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL 证书路径（Certbot 自动生成）
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # 安全头
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy strict-origin-when-cross-origin;

    # 前端静态文件
    root /home/deploy/free-video-downloader/frontend/dist;
    index index.html;

    # 静态资源长期缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    # SPA 路由回退
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 后端 API 代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # SSE / 长连接支持
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;

        # 客户端上传大小限制（本地视频上传）
        client_max_body_size 2G;
    }

    # 健康检查端点（不走代理）
    location /api/health {
        proxy_pass http://127.0.0.1:8000/api/health;
        access_log off;
    }

    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
}
NGINX_CONF

# 启用站点
sudo ln -sf /etc/nginx/sites-available/video-downloader /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# 测试配置
sudo nginx -t
```

### 3.3 申请 SSL 证书
```bash
# 安装 Certbot
sudo apt install -y certbot python3-certbot-nginx

# 申请证书（需域名已解析到服务器 IP）
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com \
    --non-interactive --agree-tos --email admin@yourdomain.com \
    --redirect

# 验证自动续期
sudo certbot renew --dry-run
```

### 3.4 重载 Nginx
```bash
sudo systemctl reload nginx
```

---

> 好的，既然您希望基于 `deploy` 用户来部署，我们最稳妥的做法是**保持 Nginx 以 `www-data` 用户运行，但赋予其对 `deploy` 用户目录下前端文件的读取权限**。这样既安全又符合标准实践，而且您的所有应用文件都归属于 `deploy`，方便日后管理。
>
> 下面是一套**最终方案**，您直接复制执行即可（全程以 `root` 身份执行，但操作围绕 `deploy` 用户展开）。
>
> ---
>
> ## 最终方案（基于 deploy 用户 + Nginx 权限修复）
>
> ### 步骤 1：修复前端文件及父目录权限
> Nginx 进程（`www-data`）需要能够**进入** `/home/deploy` 及其子目录，并**读取** `dist/` 下的所有文件。执行以下命令：
>
> ```bash
> # 给 deploy 的家目录添加执行权限（允许 www-data 进入）
> chmod o+x /home/deploy
> 
> # 给项目目录添加执行权限
> chmod o+x /home/deploy/free-video-downloader
> chmod o+x /home/deploy/free-video-downloader/frontend
> 
> # 将 dist 目录及其所有文件的属组改为 www-data（或直接设为 755）
> chown -R deploy:www-data /home/deploy/free-video-downloader/frontend/dist
> chmod -R 755 /home/deploy/free-video-downloader/frontend/dist
> ```
>
> > 解释：
> > - `chmod o+x` 让其他用户（即 `www-data`）能够进入这些目录。
> > - `chown deploy:www-data` 将 `dist` 目录的所属组改为 `www-data`，这样 `www-data` 用户就有读权限（因为权限是 755，组和其他都有读和执行）。
> > - 如果您希望更严格，也可以将所有权完全留给 `deploy`，只给 `www-data` 读权限，但上述方式最简单且安全。
>
> ---
>
> ### 步骤 2：确认 Nginx 配置正确（HTTP 版本）
> 您的配置文件 `/etc/nginx/sites-available/video-downloader` 应该还是之前 HTTP 版本的内容。为了确保万无一失，我再次给出完整的 HTTP 配置（注意 `server_name` 已设为 `_`，匹配所有请求）：
>
> ```bash
> cat > /etc/nginx/sites-available/video-downloader <<'NGINX_CONF'
> server {
>     listen 80;
>     server_name _;
> 
>     root /home/deploy/free-video-downloader/frontend/dist;
>     index index.html;
> 
>     location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
>         expires 1y;
>         add_header Cache-Control "public, immutable";
>         try_files $uri =404;
>     }
> 
>     location / {
>         try_files $uri $uri/ /index.html;
>     }
> 
>     location /api/ {
>         proxy_pass http://127.0.0.1:8000;
>         proxy_http_version 1.1;
>         proxy_set_header Host $host;
>         proxy_set_header X-Real-IP $remote_addr;
>         proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
>         proxy_set_header X-Forwarded-Proto $scheme;
>         proxy_set_header Upgrade $http_upgrade;
>         proxy_set_header Connection "upgrade";
>         proxy_buffering off;
>         proxy_cache off;
>         proxy_read_timeout 300s;
>         proxy_send_timeout 300s;
>         client_max_body_size 2G;
>     }
> 
>     location /api/health {
>         proxy_pass http://127.0.0.1:8000/api/health;
>         access_log off;
>     }
> 
>     gzip on;
>     gzip_vary on;
>     gzip_min_length 1024;
>     gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
> }
> NGINX_CONF
> ```
>
> ---
>
> ### 步骤 3：启用站点并测试配置
>
> ```bash
> # 确保软链接存在
> ln -sf /etc/nginx/sites-available/video-downloader /etc/nginx/sites-enabled/
> 
> # 移除默认站点（如果存在）
> rm -f /etc/nginx/sites-enabled/default
> 
> # 测试 Nginx 语法
> nginx -t
> ```
>
> 如果输出 `test is successful`，继续下一步；否则根据错误信息调整。
>
> ---
>
> ### 步骤 4：重载 Nginx 并验证
>
> ```bash
> systemctl reload nginx
> ```
>
> ---
>
> ### 步骤 5：验证访问
>
> 在浏览器中访问 `http://您的服务器IP`，现在应该能正常显示前端页面，不再出现 500 错误。
>
> 如果还是 500，查看详细错误日志：
>
> ```bash
> tail -30 /var/log/nginx/error.log
> ```
>
> 把输出发给我，我会进一步诊断。
>
> ---
>
> ### 额外的后手：如果仍然权限不足
> 有时候 SELinux 或 AppArmor 会限制，但 Ubuntu 默认未启用。若上述仍不行，可以暂时将 Nginx 的用户改为 `deploy`（不推荐，但可作为最后手段）：
>
> ```bash
> # 编辑 /etc/nginx/nginx.conf，将 user 改为 deploy
> sed -i 's/^user www-data;/user deploy;/' /etc/nginx/nginx.conf
> systemctl restart nginx
> ```
>
> 但**我更建议先通过权限调整解决问题**，因为修改 Nginx 运行用户可能引起日志目录权限等其他问题。
>
> ---
>
> ## 总结
> 您只需要按顺序执行“步骤1”中的权限命令，然后确保配置文件正确，重载 Nginx 即可。整个过程均以 `root` 执行，但文件归属仍是 `deploy`，日后更新代码时 `deploy` 用户仍可自由操作 `dist` 目录（因为 `deploy` 拥有写权限）。
>
> 现在执行吧，如果遇到问题随时反馈。

## ⚙️ 第四阶段：系统级优化 & 监控

### 4.1 系统参数调优（针对 2G 内存）
```bash
sudo tee -a /etc/sysctl.d/99-video-downloader.conf > /dev/null <<'EOF'
# 减少 swap 激进度，保护内存
vm.swappiness = 10
vm.vfs_cache_pressure = 50

# 网络缓冲优化（15Mbps 带宽）
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
EOF

sudo sysctl --system
```

### 4.2 配置 logrotate（防止日志撑爆磁盘）
```bash
sudo tee /etc/logrotate.d/video-downloader > /dev/null <<'EOF'
/home/deploy/free-video-downloader/backend/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 deploy deploy
    sharedscripts
    postrotate
        systemctl reload video-downloader-backend > /dev/null 2>&1 || true
    endscript
}

/var/log/nginx/*video-downloader*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload nginx > /dev/null 2>&1 || true
    endscript
}
EOF
```

### 4.3 创建健康检查脚本
```bash
cat > /home/deploy/health_check.sh <<'EOF'
#!/bin/bash
set -e

API_URL="http://127.0.0.1:8000/api/health"
FRONTEND_URL="https://yourdomain.com"

# 检查后端
if curl -sf --max-time 5 "$API_URL" | grep -q '"status":"ok"'; then
    echo "✅ Backend healthy"
else
    echo "❌ Backend unhealthy"
    systemctl restart video-downloader-backend
fi

# 检查前端
if curl -sf --max-time 5 -I "$FRONTEND_URL" | grep -q "200 OK"; then
    echo "✅ Frontend healthy"
else
    echo "❌ Frontend unhealthy"
    systemctl reload nginx
fi

# 检查磁盘空间
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 85 ]; then
    echo "⚠️ Disk usage: ${DISK_USAGE}%"
fi

# 检查内存
MEM_USAGE=$(free | awk '/Mem:/ {printf "%.0f", $3/$2 * 100}')
if [ "$MEM_USAGE" -gt 85 ]; then
    echo "⚠️ Memory usage: ${MEM_USAGE}%"
fi
EOF

chmod +x /home/deploy/health_check.sh

# 加入 crontab（每 5 分钟检查）
(crontab -l 2>/dev/null; echo "*/5 * * * * /home/deploy/health_check.sh >> /home/deploy/health_check.log 2>&1") | crontab -
```

---

## 🔧 第五阶段：常用运维操作

### 5.1 服务管理
```bash
# 后端
sudo systemctl status video-downloader-backend
sudo systemctl restart video-downloader-backend
sudo journalctl -u video-downloader-backend -f --lines=100

# 前端（Nginx）
sudo systemctl status nginx
sudo systemctl reload nginx
sudo nginx -t

# 查看实时日志
tail -f /home/deploy/free-video-downloader/backend/logs/error.log
tail -f /var/log/nginx/access.log
```

### 5.2 代码更新部署
```bash
cd /home/deploy/free-video-downloader
git pull origin master

# 后端更新
cd backend
source venv/bin/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
# 如有数据库迁移：python -c "from database import migrate; migrate()"
sudo systemctl restart video-downloader-backend

# 前端更新
cd ../frontend
npm install
npm run build
sudo systemctl reload nginx
```

### 5.3 数据库备份 & 恢复
```bash
# 备份
sqlite3 /home/deploy/free-video-downloader/backend/data/app.db ".backup /home/deploy/backups/app_$(date +%F).db"

# 定时备份（每天凌晨 3 点）
(crontab -l 2>/dev/null; echo "0 3 * * * sqlite3 /home/deploy/free-video-downloader/backend/data/app.db \".backup /home/deploy/backups/app_\$(date +\\%F).db\" && find /home/deploy/backups -name 'app_*.db' -mtime +30 -delete") | crontab -

# 恢复
sqlite3 /home/deploy/free-video-downloader/backend/data/app.db ".restore /home/deploy/backups/app_2024-01-15.db"
```

### 5.4 清理临时下载文件
```bash
# 手动清理
rm -rf /home/deploy/free-video-downloader/backend/downloads/*

# 定时清理（每天凌晨 4 点清理 24h 前的文件）
(crontab -l 2>/dev/null; echo "0 4 * * * find /home/deploy/free-video-downloader/backend/downloads -type f -mtime +1 -delete") | crontab -
```

---

## 🔀 第五点五阶段：切换 Git 远程地址并更新代码

> 适用场景：已用旧地址（如 GitHub `liyupi/free-video-downloader`）克隆并部署，现需切换到 Gitee 仓库 `https://gitee.com/luffywj/free-video-downloader.git` 并拉取最新代码。**无需重新克隆**。

### 5.5.1 进入项目目录并查看当前远程地址
```bash
cd /home/deploy/free-video-downloader
git remote -v
# 旧地址会显示：origin  https://github.com/liyupi/free-video-downloader.git (fetch/push)
```

### 5.5.2 切换远程地址到 Gitee
```bash
git remote set-url origin https://gitee.com/luffywj/free-video-downloader.git

# 确认修改成功
git remote -v
# 应显示：origin  https://gitee.com/luffywj/free-video-downloader.git
```

### 5.5.3 拉取最新代码
```bash
git pull origin master
```

> ⚠️ **若提示冲突**（通常是服务器上改过的 `.env` 被误纳入 git 管理）：
> ```bash
> # 先备份你的生产配置
> cp backend/.env backend/.env.backup
> git stash                              # 暂存本地改动
> git pull origin master                 # 拉取最新代码
> cp backend/.env.backup backend/.env    # 恢复你的配置
> ```
> 正常情况下 `.env` / `data/` / `downloads/` 已被 `.gitignore` 排除，不会冲突。

### 5.5.4 重新部署使更新生效
```bash
# 后端更新
cd /home/deploy/free-video-downloader/backend
source venv/bin/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
sudo systemctl restart video-downloader-backend

# 前端更新（前端代码有变化时执行）
cd ../frontend
npm install
npm run build
sudo systemctl reload nginx
```

### 5.5.5 验证服务正常
```bash
curl http://127.0.0.1:8000/api/health
# 返回 {"status":"ok","message":"万能视频下载器服务运行中"} 即成功
```

> 💡 **核心三步**：`git remote set-url origin 新地址` → `git pull origin master` → `systemctl restart 后端`。
> 后端代码变更**必须重启**才生效；前端变更需 `npm run build` 后 `reload nginx`。

---

## 🚨 第六阶段：常见问题排查

| 现象 | 可能原因 | 排查命令 / 解决 |
|------|----------|-----------------|
| **后端启动失败** | 端口占用 / 依赖缺失 | `ss -tlnp \| grep 8000`、`journalctl -u video-downloader-backend -n 50` |
| **内存 OOM Kill** | Whisper 模型过大 / workers 过多 / MemoryLimit 过低 | `dmesg \| grep -i oom` → 改 `WHISPER_MODEL=base`、workers=1、调大 MemoryLimit=1800M |
| **视频解析超时** | yt-dlp 版本旧 / 网络受限 | `pip install --upgrade yt-dlp`、检查服务器出站连通性 |
| **前端白屏** | 构建产物路径错 / Nginx root 错 | `ls /home/deploy/.../frontend/dist/`、检查 Nginx `root` 指令 |
| **SSL 证书过期** | Certbot 自动续期失败 | `certbot renew --force-renewal`、检查 `/var/log/letsencrypt/` |
| **上传大文件失败** | Nginx `client_max_body_size` 太小 | 确认配置 `client_max_body_size 2G;` 并 `nginx -t && systemctl reload nginx` |
| **抖音解析失败** | 服务器 IP 被风控 / yt-dlp 需更新 | 更换服务器 IP 或使用代理、升级 yt-dlp |
| **Whisper 首次极慢** | 模型下载中 / HF 连接慢 / beam_size 过大导致首次推理慢 | 设置 `WHISPER_HF_ENDPOINT=https://hf-mirror.com`、预热下载、`beam_size=10` 属正常 |

### 预热 Whisper 模型（避免首次请求超时）
```bash
cd /home/deploy/free-video-downloader/backend
source venv/bin/activate
python -c "
from faster_whisper import WhisperModel
model = WhisperModel('small', device='cpu', compute_type='int8', download_root='data/whisper-models', cpu_threads=2)
print('Model loaded:', model.model_size_or_path)
# 可选：做一次空推理预热（触发模型权重完全加载到内存）
import numpy as np
dummy_audio = np.zeros(16000, dtype=np.float32)  # 1秒静音
segments, info = model.transcribe(dummy_audio, language='zh', beam_size=10)
print('Warmup done, language:', info.language)
"
```

---

## 📊 监控建议（轻量级）

### 6.1 基础监控：Netdata（一键安装，可视化）
```bash
bash <(curl -Ss https://my-netdata.io/kickstart.sh) --dont-wait
# 访问 http://yourdomain.com:19999 （建议 Nginx 代理或 SSH 隧道访问）
```

### 6.2 关键指标告警（可选：Prometheus + Alertmanager，或直接用健康检查脚本 + 企业微信/钉钉 Webhook）
```bash
# 在 health_check.sh 中添加告警
WEBHOOK_URL="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
curl -X POST -H 'Content-Type: application/json' \
  -d '{"msgtype":"text","text":{"content":"⚠️ 视频下载器服务异常，请检查"}}' \
  "$WEBHOOK_URL"
```

---

## ✅ 部署清单（上线前逐项核对）

- [ ] 服务器 SSH 密钥登录，禁用密码登录
- [ ] 防火墙仅开放 22/80/443
- [ ] 域名已解析到服务器公网 IP
- [ ] SSL 证书有效，HTTPS 访问正常
- [ ] `.env` 所有敏感配置已填写（JWT_SECRET、LLM_API_KEY、Stripe 等）
- [ ] `WHISPER_MODEL=small`、`WHISPER_LANGUAGE=zh`、`WHISPER_BEAM_SIZE=10`、CPU/Int8 配置正确
- [ ] Gunicorn workers=2，systemd MemoryLimit=1600M
- [ ] Nginx `client_max_body_size 2G`、代理超时 300s
- [ ] 前端构建产物 `dist/` 存在且 Nginx root 指向正确
- [ ] 数据库初始化成功，`/api/health` 返回 ok
- [ ] 定时任务：健康检查、日志轮转、下载文件清理、数据库备份已加入 crontab
- [ ] 手动测试：解析 B 站/YouTube/抖音视频 → 下载 → AI 总结全流程跑通

---

## 📞 遇到问题？

1. **查看日志优先**：`journalctl -u video-downloader-backend -f` + `tail -f backend/logs/error.log`
2. **资源不够用**：`htop` 看内存/CPU、`df -h` 看磁盘
3. **网络不通**：`curl -v https://api.openai.com/v1/models` 测试 LLM 连通性
4. **yt-dlp 失效**：`pip install --upgrade yt-dlp` 通常能解决 90% 解析问题

---

> 文档版本：v1.1 | 适配 free-video-downloader 主分支 | 服务器规格：2C2G Ubuntu 24.04 | Whisper: small + int8 + beam=10 + lang=zh
> 如有改动请同步更新此文档