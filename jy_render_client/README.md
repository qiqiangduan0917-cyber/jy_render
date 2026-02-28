# 剪映渲染客户端（MVP）

基于 Python 3.10+ 与 PySide6 的 Windows 桌面客户端。

## 1. 安装与启动

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 2. 配置方式（发布锁定模式）

客户端启动后会在当前用户目录自动创建配置文件：

`%APPDATA%\JYRenderClient\config.json`

说明：
- 前台不展示 `Base URL`、`API Key`、`Jobs Endpoint`、`Health Endpoint`、`poll_interval_seconds`。
- 所有服务连接参数与轮询间隔仅通过 `config.json` 配置。
- 首次启动会自动写入默认配置。
- 示例模板见仓库文件：`config.example.json`。

## 3. 运行数据目录

所有运行数据写入：

`%APPDATA%\JYRenderClient\`

包含：
- `config.json`：服务配置
- `tasks.json`：任务持久化
- `logs/app.log`：日志
- `output/`：默认下载目录

## 4. 使用流程

1. 首次启动后，编辑 `%APPDATA%\JYRenderClient\config.json`。
2. 选择草稿目录与输出目录，点击“开始上传并渲染”。
3. 在任务列表观察状态，完成后下载结果文件。
