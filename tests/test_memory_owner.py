"""主体标记（owner）单测：主人 vs 他人的推断与召回过滤。无外部依赖、无副作用。"""

import memory_service as ms


def test_owner_self_facts():
    assert ms._infer_owner("主人喜欢喝奶茶") == "主人"
    # "有个妹妹" 是主人自己的属性，不能误判为他人
    assert ms._infer_owner("主人有个妹妹，现在在读高中") == "主人"
    assert ms._infer_owner("主人的生日是十月十二日") == "主人"
    assert ms._infer_owner("主人被同事抢了功劳") == "主人"


def test_owner_other_facts():
    assert ms._infer_owner("主人的同事小李喜欢喝美式咖啡") == "他人"
    assert ms._infer_owner("主人的妹妹对芒果过敏") == "他人"
    assert ms._infer_owner("主人的朋友家的猫叫咪咪") == "他人"


def test_query_owner_default_self():
    assert ms._infer_query_owner("我最喜欢喝什么饮料？") == "主人"
    assert ms._infer_query_owner("我家里有哪些兄弟姐妹？") == "主人"


def test_query_owner_other():
    assert ms._infer_query_owner("我同事喜欢喝什么？") == "他人"
    assert ms._infer_query_owner("我妹妹对什么过敏？") == "他人"


def test_recall_filters_by_owner(monkeypatch):
    monkeypatch.setattr(ms, "_recall_by_keywords", lambda q, top_k=5: [])
    monkeypatch.setattr(
        ms.user_memory_rag,
        "recall",
        lambda q, top_k=5, min_importance=1: [
            {"id": 1, "fact": "主人喜欢喝奶茶", "keywords": [], "importance": 9,
             "owner": "主人", "distance": 0.2},
            {"id": 2, "fact": "主人的同事喜欢美式咖啡", "keywords": [], "importance": 4,
             "owner": "他人", "distance": 0.25},
        ],
    )
    out = ms.recall_memories("我最喜欢喝什么", top_k=3)
    assert [m["fact"] for m in out] == ["主人喜欢喝奶茶"]
