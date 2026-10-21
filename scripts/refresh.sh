#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 1/2 重新生成数据集（合并 normalized_data/ + updates/）"
python3 etl/build_dataset.py

echo "==> 2/2 重新落库"
python3 db/seed.py

echo ""
echo "✅ 完成。若 API 服务正在运行，请重启以读取新数据："
echo "   python3 api/server.py"
