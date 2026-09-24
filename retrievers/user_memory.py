import chromadb
from chromadb.utils import embedding_functions
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class UserMemoryRAG:
    """
    用户长期记忆向量检索：替代 jieba 关键词召回
    复用 bge-small-zh-v1.5，与 anime_kb 隔离（不同 collection）
    """

    def __init__(self, db_path: str = "./chroma_db"):
        self.client = chromadb.PersistentClient(path=db_path)
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="BAAI/bge-small-zh-v1.5"
        )
        self.collection = self.client.get_or_create_collection(
            name="user_memories",
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add_memory(
        self,
        memory_id: str,
        fact: str,
        keywords: list,
        importance: int = 5,
        source: str = "dialogue",
        owner: str = "主人",
    ) -> None:
        """写入单条记忆"""
        self.collection.add(
            ids=[memory_id],
            documents=[fact],
            metadatas=[
                {
                    "keywords": json.dumps(keywords, ensure_ascii=False),
                    "importance": importance,
                    "created_at": datetime.now().isoformat(),
                    "source": source,
                    "owner": owner,
                }
            ],
        )
        logger.info(f"[UserMemory] 写入 id={memory_id}, fact={fact[:30]}...")

    def recall(
        self,
        query: str,
        top_k: int = 5,
        min_importance: int = 1,
        max_distance: float | None = None,
    ) -> list[dict]:
        """语义召回。max_distance 非空时丢弃距离超过阈值的弱相关结果。"""
        where_clause = (
            {"importance": {"$gte": min_importance}} if min_importance > 1 else None
        )

        results = self.collection.query(
            query_texts=[query], n_results=top_k, where=where_clause
        )

        if not results["documents"] or not results["documents"][0]:
            return []

        memories = []
        for i in range(len(results["documents"][0])):
            meta = results["metadatas"][0][i]
            try:
                kw = json.loads(meta.get("keywords", "[]"))
            except Exception:
                kw = []
            memories.append(
                {
                    "id": results["ids"][0][i],
                    "fact": results["documents"][0][i],
                    "keywords": kw,
                    "importance": meta.get("importance", 5),
                    "owner": meta.get("owner", "主人"),
                    # access_count/last_accessed 在 Chroma 里没有权威值，
                    # 这里先占位，由 memory_service.recall_memories 从 SQLite 回填权威值。
                    "access_count": meta.get("access_count", 0),
                    "created_at": meta.get("created_at", ""),
                    "last_accessed": meta.get("last_accessed", ""),
                    "distance": (
                        results["distances"][0][i] if results.get("distances") else None
                    ),
                }
            )

        # 相关性阈值：距离越大越不相关，超过阈值直接丢弃
        if max_distance is not None:
            kept = [
                m
                for m in memories
                if m.get("distance") is None or m["distance"] <= max_distance
            ]
            dropped = len(memories) - len(kept)
            if dropped:
                logger.info(
                    f"[UserMemory] 阈值过滤：丢弃 {dropped} 条 distance>{max_distance}"
                )
            memories = kept

        logger.info(f"[UserMemory] 召回 {len(memories)} 条, query={query[:20]}...")

        for m in memories:
            logger.info(
                f"[UserMemory]   → id={m['id']}, fact={m['fact'][:30]}, distance={m.get('distance')}"
            )

        return memories

    def delete(self, memory_id: str) -> None:
        self.collection.delete(ids=[memory_id])

    def clear(self) -> None:
        self.client.delete_collection("user_memories")
        self.collection = self.client.get_or_create_collection(
            name="user_memories",
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        logger.warning("[UserMemory] 已清空重建")

    def count(self) -> int:
        return self.collection.count()
