# offworld

公开作品库。原件放在本机 `sources/`，Git 管理整理后的展示文件。首页源文件在 `site/`，构建后输出到 `dist/`。

## 日常处理

```sh
python3 scripts/process.py process
python3 scripts/process.py build
python3 -m http.server 8000 --bind 127.0.0.1 --directory dist
```

打开 `http://localhost:8000/` 浏览首页，可按类型筛选、进入 slides 或在页内播放 R2 视频。也可直接打开 `artifacts.json` 中的 `path`。播放器支持方向键、空格、Home/End、页码输入、手机左右滑动；`#3` 可直达第三页。

- `sources/`：原件，整个目录被 Git 忽略，不会进入构建产物。
- `htmls/<作品>/`：自包含 HTML 或整套静态页面资源。
- `slides/<作品>/`：1920 像素长边 JPG、HTML 播放器、元数据。
- `videos/<作品>/`：封面和 R2 元数据，视频文件不进 Git。
- `artifacts.json`：由处理脚本生成的作品清单，构建时用于生成完整首页。
- `site/`：首页模板、样式、脚本和自托管字体；`site/content.json` 可定制作品标题、描述和分类。
- `.cache/`：转换缓存、临时 PDF 和待上传 MP4，Git 忽略。
- `dist/`：只包含展示产物，Git 忽略；未来 Pages 的发布目录。

PPTX 先通过 LibreOffice 渲染 PDF，再用 Poppler 生成 JPG；会核对原稿与输出页数。首次运行需要 `python3`、`soffice`、`pdfinfo`、`pdftoppm`；视频封面另需 `ffmpeg`、`ffprobe`。macOS 可安装 LibreOffice，运行时将其程序路径加入 PATH，或设置 `SOFFICE=/Applications/LibreOffice.app/Contents/MacOS/soffice`；Poppler/FFmpeg 可通过 `brew install poppler ffmpeg` 安装。

相同原稿自动跳过渲染。修改原稿后重跑即可；`--force` 强制重渲染。图片保留静态版式，不包含 PPT 动画、讲师备注或嵌入媒体；字体取决于本机环境，发布前应检查页面。删除原稿不会自动删除旧作品，需手动删除对应展示目录，再执行 `catalog` 或 `build`。

单文件 HTML 放 `sources/<名称>.html`，带本地资源的页面请放成 `sources/<名称>/index.html`，资源放在同目录中并使用相对路径。HTML bundle 不接受软链接、隐藏文件、PPT/PDF 和视频原件；请使用 HTTPS 外部视频地址。原有 HTML/JS 将直接执行，只放你信任的作品。

## R2 视频

1. 注册 [Cloudflare](https://dash.cloudflare.com/)，在 Storage & databases → R2 → Overview 开通 R2。
2. 创建 `offworld` bucket。暂时没有域名时，可启用 Public Development URL 并使用 `https://pub-….r2.dev` 做开发测试；该入口有限流，正式发布时绑定媒体自定义域名。开启公开访问后，bucket 内对象可公开读取。
3. 创建仅可读写此 bucket 的 R2 S3 API 凭证，在本机设置 `.env.example` 中的环境变量。不要把 Secret 发到聊天或提交到 Git。可把这三项配置填写到本机 `.env`，上传时脚本自动读取；终端已导出的变量优先。
4. 在 `artifact.config.json` 填写 `r2Bucket` 和 `mediaBaseUrl`；当前 bucket 为 `offworld`，正式视频域名为 `https://media.sunlei.page`。
5. 创建本地 Python 环境并安装可选依赖，再预览上传计划：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-r2.txt
.venv/bin/python scripts/upload_videos.py
# 配置完成后显式上传；会准备 H.264/AAC MP4 并开启 faststart。
.venv/bin/python scripts/upload_videos.py --execute
python3 scripts/process.py build
```

上传成功后元数据才标记为 `uploaded`；原件变化后重新标记为待上传。现有两段视频已上传 R2。首页仅在点击播放后加载视频，不在首次访问时下载视频。

### 视频链接命名

公开链接采用短英文名称和发布版本号，例如：

```text
https://media.sunlei.page/videos/ai-intro-astra-v1.mp4
https://media.sunlei.page/videos/ai-intro-claude-v1.mp4
```

在 `artifact.config.json` 的 `videoNames` 中，以作品 ID 为键填写短名（不带扩展名），例如 `ai-intro-astra-v1`。只使用小写英文字母、数字和连字符，每个作品名称唯一。发布版本号与原始 PPT/视频文件的修改编号独立；v1 表示首次以此短链接发布。

新增视频后可先运行 `process` 查看作品 ID，再填写短名并重跑 `process`，然后执行上传。为兼容既有素材，没有配置短名的视频仍使用旧的哈希路径。

内容校验哈希保存在元数据 `sourceSha256` 和本机缓存中，不出现在新公开文件名里。替换视频内容时，把短名升级为 `-v2` 等新版本；上传脚本会拒绝用不同内容覆盖已有的版本名，避免长期缓存返回旧画面。仅修改域名并重新处理时，已上传状态会保留，链接会刷新到新域名。

本次迁移使用 R2 服务端复制，旧对象保留，旧链接仍可访问；没有重新上传原始视频。新旧对象并存会暂时占用两份存储。

## Git 与后续发布

```sh
git status --short
git add .
git diff --cached --stat
git commit -m "Set up artifact processing and slide viewers"
git push -u origin main
```

`sources/`、视频、原始 PPTX、缓存、凭证和 `dist/` 均不提交。Workers Static Assets 使用 `python3 scripts/process.py build` 构建、发布 `dist`；云端无需 LibreOffice，直接使用已经提交的 JPG。只在本地运行 `process`。云端构建不读取 `.env`，不需要 R2 上传凭证。

官方说明：[R2 开通](https://developers.cloudflare.com/r2/get-started/)、[公开域名](https://developers.cloudflare.com/r2/buckets/public-buckets/)、[R2 定价](https://developers.cloudflare.com/r2/pricing/)。

脚本回归检查：`python3 -m unittest discover -s scripts -p "test_*.py"`。macOS 转换会自动加入系统 CJK 字体目录，字体缓存仅保存在本机 `.cache/`。

## Cloudflare Workers Static Assets 部署

正式地址为 **https://offworld.sunlei.page/**，视频域名为 **https://media.sunlei.page**。使用 Workers Static Assets 发布纯静态网站，不需要编写 Worker 请求处理代码。仓库根目录的 `wrangler.json` 指定 `assets.directory` 为 `./dist`，并使用站内 `404.html` 处理不存在的页面。

在 Cloudflare 的 Workers & Pages 创建应用，连接 GitHub 仓库 `sungitly/offworld`，填写：

| 设置 | 值 |
| --- | --- |
| Project name / Worker name | `offworld` |
| Production branch | `main` |
| Root directory | 仓库根目录，留空或 `/` |
| Build command | `python3 scripts/process.py build` |
| Deploy command | `npx wrangler deploy` |

Cloudflare 的 Git 集成负责部署身份授权，不能用本机 R2 的对象读写凭证替代部署凭证。R2 密钥不需要进入构建环境。推送到 `main` 后，已连接的 Cloudflare 项目会自动重新构建部署；以控制台部署日志为准。

部署成功后，在应用的 Domains / Settings → Domains & Routes 中绑定 `offworld.sunlei.page`，按控制台提示完成 DNS 与证书配置。如果域名已绑定到旧应用，需要先解除旧绑定；不要删除 R2 的 `media.sunlei.page` 绑定。静态资源、`_headers` 和 `404.html` 均从 `dist` 发布。

如需继续用传统 Pages，仍可通过创建页面底部的 Continue to Pages 进入，构建命令相同，Build output directory 填 `dist`，不使用 Worker 的 Deploy command。本仓库默认按 Workers Static Assets 部署。

首页在构建时读取清单，把所有作品输出为真实 HTML，浏览时无需请求清单 API；JavaScript 只增强类型筛选和视频弹窗。新增作品后运行处理与上传脚本，再运行 `build` 即可自动接入；已上传的视频链接不需要云端密钥。展示文案可在 `site/content.json` 中按作品 ID 覆盖，新作品没有覆盖时使用原始标题。

旧 `r2.dev` 入口目前保留以兼容旧链接；确认不再需要后可在 R2 控制台关闭。不要把 R2 API 凭证填进 Cloudflare 构建环境。

部署参考：[Workers Static Assets](https://developers.cloudflare.com/workers/static-assets/)、[Wrangler 配置](https://developers.cloudflare.com/workers/wrangler/configuration/)、[自定义域名](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/)。
