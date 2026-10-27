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
4. 在 `artifact.config.json` 填写 `r2Bucket` 和 `mediaBaseUrl`；测试时使用控制台的 `https://pub-….r2.dev`，正式发布使用 `https://media.example.com` 等自定义域名。
5. 创建本地 Python 环境并安装可选依赖，再预览上传计划：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-r2.txt
.venv/bin/python scripts/upload_videos.py
# 配置完成后显式上传；会准备 H.264/AAC MP4 并开启 faststart。
.venv/bin/python scripts/upload_videos.py --execute
python3 scripts/process.py build
```

上传成功后元数据才标记为 `uploaded`；原件变化后重新标记为待上传。对象名包含内容哈希，旧视频不会自动删除。现有两段视频已上传 R2。首页仅在点击播放后加载视频，不在首次访问时下载视频。

## Git 与后续发布

```sh
git status --short
git add .
git diff --cached --stat
git commit -m "Set up artifact processing and slide viewers"
git push -u origin main
```

`sources/`、视频、原始 PPTX、缓存、凭证和 `dist/` 均不提交。Pages 使用 `python3 scripts/process.py build` 构建、发布 `dist`；云端无需 LibreOffice，直接使用已经提交的 JPG。只在本地运行 `process`。云端构建不读取 `.env`，不需要 R2 上传凭证。

官方说明：[R2 开通](https://developers.cloudflare.com/r2/get-started/)、[公开域名](https://developers.cloudflare.com/r2/buckets/public-buckets/)、[R2 定价](https://developers.cloudflare.com/r2/pricing/)。

脚本回归检查：`python3 -m unittest discover -s scripts -p "test_*.py"`。macOS 转换会自动加入系统 CJK 字体目录，字体缓存仅保存在本机 `.cache/`。

## Cloudflare Pages 部署

在 Cloudflare 控制台进入 Workers & Pages，创建 Pages 项目并连接 GitHub 仓库 `sungitly/offworld`。选择 Git 集成后填写：

| 设置 | 值 |
| --- | --- |
| Production branch | `main` |
| Framework preset | `None` |
| Root directory | 仓库根目录，留空 |
| Build command | `python3 scripts/process.py build` |
| Build output directory | `dist` |

保存并部署后使用 Cloudflare 分配的 `*.pages.dev` 地址访问。以后推送到 `main` 会自动重新构建；这里只准备部署所需的源文件，尚未创建 Pages 项目。`site/_headers` 和 `site/404.html` 会随构建复制到发布根目录。

首页在构建时读取清单，把所有作品输出为真实 HTML，浏览时无需请求清单 API；JavaScript 只增强类型筛选和视频弹窗。新增作品后运行处理与上传脚本，再运行 `build` 即可自动接入；已上传的视频链接不需要云端密钥。展示文案可在 `site/content.json` 中按作品 ID 覆盖，新作品没有覆盖时使用原始标题。

视频目前使用 R2 `r2.dev` 开发入口，有访问限流；正式开放给大量访客前绑定媒体自定义域名，再更新配置及视频元数据地址。不要把 R2 API 凭证填进 Pages 构建环境。

部署参考：[静态 HTML](https://developers.cloudflare.com/pages/framework-guides/deploy-anything/)、[构建配置](https://developers.cloudflare.com/pages/configuration/build-configuration/)。
