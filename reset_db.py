#!/usr/bin/env python3
"""
reset_db.py — 一键删库重来

用法：
    python reset_db.py
"""

import os
import shutil


def rm_if_exists(path: str):
    if os.path.isfile(path):
        os.remove(path)
        print(f"[✓] 删除文件: {path}")
    elif os.path.isdir(path):
        shutil.rmtree(path)
        print(f"[✓] 删除目录: {path}")
    else:
        print(f"[ ] 不存在，跳过: {path}")


def main():
    print("=" * 50)
    print("AI Companion — 删库重来")
    print("=" * 50)

    # 1. 清理
    print("\n[1/3] 清理旧数据...")
    rm_if_exists("chroma_db")
    rm_if_exists("chat.db")
    rm_if_exists("logs/agent.log")

    # 2. 重建 SQLite 表
    print("\n[2/3] 重建 SQLite 表...")
    from memory_service import init_db as init_memories
    from test_api import init_db as init_chat
    from personality_state import init_personality_db

    init_memories()
    print("[✓] memories 表")
    init_chat()
    print("[✓] messages 表")
    init_personality_db()
    print("[✓] personality 表")

    # 3. 填充 anime_kb（直接调用现有脚本）
    print("\n[3/3] 填充 anime_kb...")
    import init_anime_kb  # 直接执行其全局代码

    print("[✓] anime_kb 已填充")

    # 4. 验证
    print("\n[验证] 当前状态...")
    from retrievers.anime_kb import AnimeRAG
    from retrievers.user_memory import UserMemoryRAG

    print(f"[✓] anime_kb:     {AnimeRAG().collection.count()} 条")
    print(f"[✓] user_memories: {UserMemoryRAG().count()} 条")

    print("\n" + "=" * 50)
    print("完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
