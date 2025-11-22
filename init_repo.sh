# 0. 获取当前目录名作为项目名
local CURRENT_DIR_NAME=$(basename "$PWD")
local PACKAGE_NAME=${CURRENT_DIR_NAME//-/_}

echo "🚀 Initializing Project: $CURRENT_DIR_NAME (Package: $PACKAGE_NAME)..."

# --- 自动化替换逻辑 START ---

# 1. 重命名 src 下的目录
if [ -d "src/placeholder_name" ]; then
    mv src/placeholder_name "src/$PACKAGE_NAME"
    echo "📂 Renamed src package to: src/$PACKAGE_NAME"
fi

# 2. 修改 pyproject.toml 中的 name 字段
if [ -f "pyproject.toml" ]; then
    python3 -c "import sys; content = sys.stdin.read(); print(content.replace('name = \"placeholder_name\"', 'name = \"$PACKAGE_NAME\"'))" < pyproject.toml > pyproject.toml.tmp && mv pyproject.toml.tmp pyproject.toml
    echo "📝 Updated pyproject.toml name"
fi

# 3. 替换代码中的引用 (tests/ 和 src/ 下的所有 .py 文件)
# 这一步解决了 test_smoke.py 中 import placeholder_name 不会被更新的问题
echo "🔄 Updating imports in python files..."
find src tests -name "*.py" -type f -exec python3 -c "import sys; path = sys.argv[1]; content = open(path).read(); open(path, 'w').write(content.replace('placeholder_name', '$PACKAGE_NAME'))" {} \;

# --- 自动化替换逻辑 END ---

# 4. 正常的 uv 流程
if ! command -v uv &> /dev/null; then
    echo "❌ uv not found."
    return 1
fi

echo "📦 Installing dependencies..."
uv sync

echo "🪝 Installing pre-commit hooks..."
uv run pre-commit install

if [ -f ".env.example" ] && [ ! -f ".env" ]; then
    echo "🔑 Creating .env..."
    cp .env.example .env
fi

echo "✅ Setup complete for $PACKAGE_NAME!"
