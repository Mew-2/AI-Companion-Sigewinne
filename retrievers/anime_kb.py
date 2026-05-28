import chromadb
from chromadb.utils import embedding_functions


class AnimeRAG:
    """
    二次元角色设定 RAG：ChromaDB 向量语义检索
    支持按 category（身份/外貌/性格/人际关系等）和 tags 元数据过滤
    """

    def __init__(self, db_path: str = "./chroma_db"):
        self.client = chromadb.PersistentClient(path=db_path)
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="BAAI/bge-small-zh-v1.5"
        )
        self.collection = self.client.get_or_create_collection(
            name="anime_kb", embedding_function=self.embedding_fn
        )

    def add_documents(self, docs: list[dict]):
        """录入设定文档
        docs: [{"id": "1", "content": "...", "metadata": {"category":"personality", "source":"萌娘百科", "tags":["性格"]}}]
        """
        if not docs:
            return
        self.collection.add(
            ids=[d["id"] for d in docs],
            documents=[d["content"] for d in docs],
            metadatas=[d.get("metadata", {}) for d in docs],
        )

    def retrieve(
        self, query: str, top_k: int = 3, category: str = None, tag: str = None
    ) -> list[str]:
        """
        语义检索，支持元数据过滤：
        - category: 按类别过滤（identity/personality/appearance/relationship/background 等）
        - tag: 按标签过滤（如"莱欧斯利"）
        """
        where_clause = {}
        if category:
            where_clause["category"] = {"$eq": category}
        if tag:
            where_clause["tags"] = {"$contains": tag}

        # 组合过滤条件
        filters = where_clause if where_clause else None

        results = self.collection.query(
            query_texts=[query], n_results=top_k, where=filters
        )
        if results["documents"]:
            return results["documents"][0]
        return []

    def clear(self):
        """清空知识库（调试用）"""
        self.client.delete_collection("anime_kb")
        self.collection = self.client.get_or_create_collection(
            name="anime_kb", embedding_function=self.embedding_fn
        )

    def get_all_tags(self) -> set[str]:
        """从知识库所有文档 metadata 中提取唯一 tag 集合（自动维护）"""
        all_meta = self.collection.get(include=["metadatas"])["metadatas"]
        tags = set()
        for meta in all_meta:
            if meta and "tags" in meta:
                tags.update(meta["tags"])
        return tags
