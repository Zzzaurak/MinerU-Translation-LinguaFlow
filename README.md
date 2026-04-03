# MinerU Batch CLI

一个本地批处理命令行工具：把你选中的文件放进输入目录，调用 MinerU API 处理，然后输出结构化结果（manifest + markdown + 图片），方便后续程序继续消费。

---

## 1) 启动前准备

### 环境要求

- Python 3.12+（你机器上是 3.14.3）
- 已创建项目虚拟环境（本仓库使用 `./.venv`）

### 安装依赖（若还没装）

```bash
./.venv/bin/python -m pip install -U pip pytest
```

---

## 2) 配置 MinerU 参数（推荐 JSON，其次 CLI/ENV）

推荐把 API key、接口地址和运行参数统一写到项目根 `mineru.config.json`。

> 安全提示：`mineru.config.json` 含密钥，已在 `.gitignore` 中默认忽略，不会进入 Git。请基于 `mineru.config.example.json` 复制生成本地配置。

配置优先级（按字段逐项生效）：

`JSON > CLI > ENV > default`

示例（`mineru.config.json`）：

```json
{
  "api_token": "你的_MinerU_API_Key",
  "api_base_url": "https://mineru.net/api/v4",
  "model_version": "pipeline",
  "poll_interval_sec": 5,
  "max_poll_min": 30,
  "retry_max": 3,

  "translation_enabled": false,
  "translation_api_base_url": "https://api.openai.com/v1",
  "translation_api_key": "你的_翻译_API_Key",
  "translation_model": "gpt-4o-mini",
  "translation_target_language": "zh-CN",
  "translation_timeout_sec": 30,
  "translation_retry_max": 3
}
```

### 可选：开启英文→中文翻译后处理

当 `translation_enabled=true` 时，CLI 会把标准化后的 `document.md` 发送到 OpenAI-compatible 翻译 API，返回中文 Markdown 并输出 `document.zh.md`。

推荐最小配置：

```json
{
  "translation_enabled": true,
  "translation_api_base_url": "https://api.openai.com/v1",
  "translation_api_key": "你的_翻译_API_Key",
  "translation_model": "gpt-4o-mini",
  "translation_target_language": "zh-CN"
}
```

翻译失败策略：
- 不影响原 `document.md` 与 `images/` 产出。
- 在 `item.json` 与 `manifest.json` 记录翻译状态/错误。

也可以继续使用环境变量（兼容旧方式）：

```bash
export MINERU_API_TOKEN="你的_MinerU_API_Key"
```

可选环境变量（不填则使用默认值）：

- `MINERU_API_BASE_URL`（默认：`https://mineru.net/api/v4`）
- `MINERU_POLL_INTERVAL_SEC`（默认：`5`）
- `MINERU_MAX_POLL_MIN`（默认：`30`）
- `MINERU_RETRY_MAX`（默认：`3`）
- `MINERU_TRANSLATION_ENABLED`（默认：`false`）
- `MINERU_TRANSLATION_API_BASE_URL`（默认：`https://api.openai.com/v1`）
- `MINERU_TRANSLATION_API_KEY`（默认：空；仅在开启翻译时必填）
- `MINERU_TRANSLATION_MODEL`（默认：`gpt-4o-mini`）
- `MINERU_TRANSLATION_TARGET_LANGUAGE`（默认：`zh-CN`）
- `MINERU_TRANSLATION_TIMEOUT_SEC`（默认：`30`）
- `MINERU_TRANSLATION_RETRY_MAX`（默认：`3`）

---

## 3) 怎么上传“所选文件”

方式是：把你要处理的文件放到一个目录（例如 `./inbox`），然后用 `run` 指向这个目录。

### 支持的输入扩展名

`.pdf .doc .docx .ppt .pptx .png .jpg .jpeg .html`

示例：

```bash
mkdir -p inbox
# 把你选中的文件复制/移动到 inbox/
```

---

## 4) 执行批处理（上传 + 处理 + 产出）

### 一键启动（推荐）

如果你不想每次手敲长命令，可以直接使用项目脚本：

```bash
bash scripts/run-mineru.sh
```

默认参数：

- `--input inbox`
- `--output out`
- `--model-version pipeline`
- `--continue-on-error true`

你也可以显式覆盖：

```bash
bash scripts/run-mineru.sh \
  --input inbox \
  --output out \
  --model-version pipeline \
  --config mineru.config.json
```

macOS 可双击 `.command`（或终端调用）：

```bash
bash scripts/run-mineru.command --input inbox --output out
```

如果你需要把额外参数直接透传给底层 CLI，请使用 `--` 分隔：

```bash
bash scripts/run-mineru.sh --input inbox --output out -- --continue-on-error false
```

```bash
PYTHONPATH=src ./.venv/bin/python -m mineru_batch_cli run \
  --input inbox \
  --output out \
  --config mineru.config.json \
  --model-version pipeline \
  --continue-on-error true
```

说明：

- `--config` 可选；传入后会读取指定 JSON 文件。
- 不传 `--config` 时，程序会尝试读取项目根 `mineru.config.json`。
- 若显式传入 `--config` 但文件不存在，会直接报错退出。

参数说明：

- `--input`：待处理文件目录（你选中的文件放这里）
- `--output`：输出目录
- `--model-version`：`pipeline | vlm | MinerU-HTML`
- `--continue-on-error`：
  - `true`：某个文件失败也继续处理其他文件
  - `false`：遇错后停止后续处理
- `--translation-enabled`：是否开启翻译阶段（`true | false`）
- `--translation-api-base-url`：翻译 API 基地址（OpenAI-compatible）
- `--translation-api-key`：翻译 API Key（开启翻译时必填）
- `--translation-model`：翻译模型名
- `--translation-target-language`：目标语言（默认 `zh-CN`）
- `--translation-timeout-sec`：翻译请求超时秒数
- `--translation-retry-max`：翻译请求重试次数

---

## 5) 输出在哪里？长什么样？

执行后在 `--output` 目录下看到：

- `manifest.json`：整批结果汇总（总数、成功数、失败数、每个文件状态等）
- `items/<item_slug>/`：每个输入文件对应一个目录
  - `document.md`
  - `document.zh.md`（仅 `translation_enabled=true` 且翻译成功时存在）
  - `images/`（仅保留 markdown 引用到的图片）
  - `item.json`

---

## 6) 校验输出 manifest

```bash
PYTHONPATH=src ./.venv/bin/python -m mineru_batch_cli verify \
  --manifest out/manifest.json
```

成功会打印：

```text
MANIFEST_OK
```

---

## 7) 常见问题

### Q1: 提示缺少 token

```text
Error: Missing required API token: set MINERU_API_TOKEN
```

可用任一方式修复：

1. 在 `mineru.config.json` 中设置 `api_token`

2. 或设置环境变量：

```bash
export MINERU_API_TOKEN="你的key"
```

### Q1.1: `--config` 文件不存在

```text
Error: Config file not found: /your/path/mineru.config.json
```

请检查路径是否正确，或移除 `--config` 改为使用项目根默认 `mineru.config.json`。

### Q1.2: JSON 配置语法错误

```text
Error: Failed to read config file: /your/path/mineru.config.json
```

请修复 JSON 语法（例如缺少逗号、括号未闭合）。

### Q1.3: JSON 不是对象（例如数组）

```text
Error: Config file must be a JSON object: /your/path/mineru.config.json
```

请确保配置文件顶层是对象（`{ ... }`），不要使用数组或纯字符串。

### Q2: `python` 命令找不到

你的系统可能只有 `python3`，本项目建议统一使用：

```bash
./.venv/bin/python
```

### Q2.1: 一键脚本提示找不到 `.venv/bin/python`

说明虚拟环境未准备好。先执行：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip pytest
```

然后再运行：

```bash
bash scripts/run-mineru.sh
```

### Q3: 输入目录不存在

确保 `--input` 指向真实目录，且里面有支持扩展名的文件。

### Q3.1: 一键脚本报 `Input directory does not exist`

创建目录并重试：

```bash
mkdir -p inbox
bash scripts/run-mineru.sh --input inbox --output out
```

---

## 8) 最短可用示例（复制即用）

```bash
export MINERU_API_TOKEN="你的_MinerU_API_Key"

mkdir -p inbox out
# 把文件放入 inbox/

# 方式 A：使用项目根 mineru.config.json（推荐）
PYTHONPATH=src ./.venv/bin/python -m mineru_batch_cli run \
  --input inbox \
  --output out \
  --model-version pipeline \
  --continue-on-error true

# 方式 B：显式指定配置文件路径
PYTHONPATH=src ./.venv/bin/python -m mineru_batch_cli run \
  --input inbox \
  --output out \
  --config mineru.config.json \
  --model-version pipeline \
  --continue-on-error true

PYTHONPATH=src ./.venv/bin/python -m mineru_batch_cli verify --manifest out/manifest.json
```
