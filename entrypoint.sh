#!/bin/sh
set -e
cd /app

# 首次启动检测：chroma_db 为空说明数据库和知识库还没初始化
if [ -z "$(ls -A chroma_db 2>/dev/null)" ]; then
    echo "[entrypoint] 首次启动，初始化数据库与知识库..."
    python - <<'PY'
from memory_service import init_db as init_memories
from test_api import init_db as init_chat
from personality_state import init_personality_db
init_memories()
init_chat()
init_personality_db()
import init_anime_kb  # 模块级代码直接填充 92 条知识库
print("[entrypoint] 初始化完成")
PY
fi

exec python main.py
