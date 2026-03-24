# Magic Debug

**AI 驱动的调试器** - 支持 Vim/Neovim 插件和 AI 接口

Magic Debug 是一个基于 DAP (Debug Adapter Protocol) 协议的调试器，专为 Vim/Neovim 设计，同时提供 HTTP API 供 AI 工具调用。

## 架构

AI
  │
  ▼
Magic Debug Core
  ├── Session Manager  (进程控制)
  ├── DAP Client       (协议通信)
  ├── State Model      (状态管理)
  ├── Controller       (调度核心)
  │
  ├── RPC Server       (Vim 通信)
  └── HTTP Server      (AI 接口)
        │
        ▼
    lldb-dap

## 功能特性

- 完整的 DAP 协议实现
- LLDB 调试适配器支持
- Vim/Neovim 插件 (Lua)
- HTTP REST API (供 AI 调用)
- Unix Socket RPC (低延迟)
- 断点管理
- 调用栈查看
- 变量查看和修改
- 表达式求值
- 多线程支持

## 安装

### 1. 安装 LLDB

**macOS:**
```bash
xcode-select --install
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install lldb
```

### 2. 安装 Magic Debug Python 后端

```bash
cd magic-debug
pip install -e .
```

安装后，`magic-debug` 命令将可用。

### 3. 安装 Neovim 插件

#### 使用插件管理器

**lazy.nvim**（推荐）：
在 `~/.config/nvim/lua/plugins/magic-debug.lua` 中添加：
```lua
return {
    {
        dir = "/path/to/magic-debug/vim-plugin",  -- 替换为实际路径
        config = function()
            require('magic-debug').setup({
                socket = "/tmp/magic-debug.sock",
                auto_start_server = true,  -- 自动启动后端
            })
        end,
    }
}
```
然后运行 `:Lazy sync`。

**packer.nvim**：
在 `~/.config/nvim/lua/plugins.lua` 中添加：
```lua
use {
    "/path/to/magic-debug/vim-plugin",
    config = function()
        require('magic-debug').setup()
    end
}
```
执行 `:PackerSync`。

**vim-plug**（需确保 Neovim 支持）：
在 `init.vim` 或 `init.lua` 中添加：
```vim
Plug '/path/to/magic-debug/vim-plugin'
```
然后执行 `:PlugInstall`。

#### 手动安装（无插件管理器）

将 `vim-plugin` 目录复制到 Neovim 的 `runtimepath` 中，例如 `~/.config/nvim/pack/magic-debug/start/`：
```bash
mkdir -p ~/.config/nvim/pack/magic-debug/start
cp -r /path/to/magic-debug/vim-plugin ~/.config/nvim/pack/magic-debug/start/
```
然后创建或编辑 `~/.config/nvim/init.lua`，添加配置：
```lua
require('magic-debug').setup({
    socket = "/tmp/magic-debug.sock",
    auto_start_server = true,
})
```

#### 验证插件安装

重启 Neovim 后，执行命令 `:MagicDebugStart`，如果看到提示信息且无报错，则插件加载成功。

## 快速开始

### 1. 启动后端服务器

**方式一：手动启动**
```bash
magic-debug
```
可后台运行：
```bash
nohup magic-debug &
```

**方式二：由插件自动启动**（推荐）
在插件配置中设置 `auto_start_server = true`，插件会在首次需要时自动启动后端。请确保 `server_command` 配置正确（默认为 `"magic-debug"`，即系统 PATH 中的可执行文件）。

### 2. 在 Vim/Neovim 中使用

打开一个源文件（如 C 语言程序），执行调试命令：

```vim
" 启动调试（程序路径为 ./myprogram）
:MagicDebugStart ./myprogram

" 在当前行设置断点
:MagicDebugToggleBreakpoint

" 执行控制
:MagicDebugContinue
:MagicDebugStepOver
:MagicDebugStepInto
:MagicDebugStepOut

" 停止调试
:MagicDebugStop

" 打开调试 UI（浮动窗口）
:MagicDebugUI
```

### 3. HTTP API 调用（供 AI 或其他工具）

```bash
# 获取状态
curl http://localhost:8765/api/status

# 设置断点
curl -X POST http://localhost:8765/api/breakpoint/set \
  -H "Content-Type: application/json" \
  -d '{"file": "/path/to/main.c", "line": 10}'

# 继续执行
curl -X POST http://localhost:8765/api/continue
```

## 命令行选项

```
usage: magic-debug [-h] [--debug PROGRAM] [--args ARGS] [--stop-on-entry]
                   [--socket PATH] [--port PORT] [--verbose] [--log-file FILE]
                   [--check] [--version]

Magic Debug - AI-powered debugger

optional arguments:
  --debug PROGRAM       Program to debug
  --args ARGS           Program arguments (comma-separated)
  --stop-on-entry       Stop at program entry
  --socket PATH         Unix socket path (default: /tmp/magic-debug.sock)
  --port PORT           HTTP API port (default: 8765)
  --verbose             Enable verbose logging
  --log-file FILE       Log file path
  --check               Check LLDB installation and exit
  --version             Show version
```

## HTTP API 文档

### 状态查询

| 端点               | 方法 | 描述             |
| ------------------ | ---- | ---------------- |
| `/api/status`      | GET  | 获取调试状态摘要 |
| `/api/state`       | GET  | 获取完整状态     |
| `/api/threads`     | GET  | 获取线程列表     |
| `/api/stack`       | GET  | 获取调用栈       |
| `/api/scopes`      | GET  | 获取作用域       |
| `/api/variables`   | GET  | 获取变量         |
| `/api/breakpoints` | GET  | 获取断点列表     |
| `/api/output`      | GET  | 获取输出         |

### 执行控制

| 端点             | 方法 | 描述     |
| ---------------- | ---- | -------- |
| `/api/start`     | POST | 启动调试 |
| `/api/stop`      | POST | 停止调试 |
| `/api/restart`   | POST | 重启调试 |
| `/api/continue`  | POST | 继续执行 |
| `/api/pause`     | POST | 暂停执行 |
| `/api/step/over` | POST | 单步跳过 |
| `/api/step/into` | POST | 单步进入 |
| `/api/step/out`  | POST | 单步跳出 |

### 断点管理

| 端点                     | 方法 | 描述         |
| ------------------------ | ---- | ------------ |
| `/api/breakpoint/set`    | POST | 设置断点     |
| `/api/breakpoint/remove` | POST | 移除断点     |
| `/api/breakpoint/toggle` | POST | 切换断点     |
| `/api/breakpoint/clear`  | POST | 清除所有断点 |

### 求值

| 端点                | 方法 | 描述       |
| ------------------- | ---- | ---------- |
| `/api/evaluate`     | POST | 求值表达式 |
| `/api/variable/set` | POST | 设置变量值 |

## 项目结构

```
magic-debug/
├── core/
│   ├── __init__.py
│   ├── session.py      # 进程管理
│   ├── dap.py          # DAP 通信
│   ├── state.py        # 状态模型
│   └── controller.py   # 调度逻辑
│
├── adapters/
│   ├── __init__.py
│   └── lldb.py         # LLDB 封装
│
├── server/
│   ├── __init__.py
│   ├── rpc.py          # Vim 通信 (Unix Socket)
│   └── http.py         # AI 接口 (HTTP)
│
├── vim-plugin/
│   └── lua/
│       └── magic-debug/
│           └── init.lua    # Vim 插件
│
├── main.py             # 主程序入口
├── setup.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

## 开发

### 运行测试

```bash
pytest tests/
```

### 代码格式化

```bash
black .
isort .
```

### 类型检查

```bash
mypy .
```

## 故障排除

### 1. lldb-dap 未找到
- 确保 LLDB 已安装（`sudo apt install lldb` 或通过 Xcode 安装）。
- 运行 `magic-debug --check` 查看 LLDB 状态。若路径不正确，可在配置中手动指定 `lldb_dap_path`。

### 2. 后端启动失败
- 检查 `magic-debug` 命令是否在 PATH 中（`which magic-debug`）。
- 若手动启动，确保 socket 文件路径可写（通常 `/tmp` 可写）。
- 查看日志：`magic-debug --verbose`。

### 3. Vim 插件无法连接
- 确认 socket 文件存在（`ls -l /tmp/magic-debug.sock`）。
- 检查插件配置中的 `socket` 路径是否与后端一致。
- 尝试手动启动后端后再执行 `:MagicDebugRefresh`。

### 4. 被调试程序未停止在断点
- 确保程序已编译为带调试符号（`-g` 选项）。
- 断点设置后，执行 `:MagicDebugContinue` 继续运行。

## License

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
