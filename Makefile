# Magic Debug Makefile

.PHONY: install test clean run check

# 默认目标
all: check install

# 检查依赖
check:
	@echo "Checking Python version..."
	@python3 --version
	@echo "Checking LLDB installation..."
	@python3 -c "from adapters.lldb import check_lldb_installation; import json; print(json.dumps(check_lldb_installation(), indent=2))"

# 安装
install:
	pip install -e .

# 运行测试
test:
	pytest tests/ -v

# 运行服务器
run:
	python3 main.py

# 调试模式运行
debug:
	python3 main.py --verbose

# 清理
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +

# 格式化代码
format:
	black .
	isort .

# 类型检查
lint:
	mypy .

# 构建发布包
build:
	python3 -m build

# 编译测试程序
build-test:
	gcc -g -o tests/test_sample tests/test_sample.c

# 帮助
help:
	@echo "Magic Debug Makefile"
	@echo ""
	@echo "Usage:"
	@echo "  make check      - Check dependencies"
	@echo "  make install    - Install the package"
	@echo "  make test       - Run tests"
	@echo "  make run        - Run the server"
	@echo "  make debug      - Run with verbose logging"
	@echo "  make clean      - Clean build artifacts"
	@echo "  make format     - Format code"
	@echo "  make lint       - Run type checker"
	@echo "  make build      - Build distribution package"
	@echo "  make build-test - Build test program"
