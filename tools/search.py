import os
import requests
from dotenv import load_dotenv

# 保险加载：如果 main.py 先执行了 load_dotenv()，这里重复调用无害
# 如果单独运行 search.py 测试，这行确保能读到 .env
load_dotenv()

# 从环境变量读取 Key，硬编码是工程坏习惯
BOCHA_API_KEY = os.getenv("BOCHA_API_KEY")
BOCHA_URL = "https://api.bochaai.com/v1/web-search"


def web_search(query: str) -> str:
    """
    调用博查 AI 搜索 API。
    返回：适合 LLM 直接阅读的摘要文本（不是原始 JSON）。
    """
    # 防御：Key 没配时返回 mock 级别的降级信息，不让程序崩
    if not BOCHA_API_KEY:
        return f"关于'{query}'的搜索结果：搜索服务 API Key 未配置。"

    headers = {
        "Authorization": f"Bearer {BOCHA_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "query": query,
        "summary": True,  # 博查返回长摘要，LLM 更容易总结
        "count": 5,       # 取前 5 条，控制 token 消耗
    }

    try:
        resp = requests.post(BOCHA_URL, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()  # 如果 401/429，这里抛异常进 except
        data = resp.json()

        # 博查返回结构：data.webPages.value[]
        pages = data.get("data", {}).get("webPages", {}).get("value", [])
        if not pages:
            return f"关于'{query}'的搜索未找到相关结果。"

        # 只取前 3 条最相关的，拼成 LLM 可读的文本
        # 格式："1. 标题: 摘要\n2. 标题: 摘要..."
        results = []
        for i, p in enumerate(pages[:3], 1):
            title = p.get("name", "无标题")
            # summary 是长摘要，snippet 是短摘要，优先取 summary
            summary = p.get("summary") or p.get("snippet", "无摘要")
            results.append(f"{i}. {title}: {summary}")

        return "搜索结果：\n" + "\n".join(results)

    except requests.exceptions.Timeout:
        # 超时降级：返回提示，不崩程序
        return f"关于'{query}'的搜索超时，请稍后再试。"
    except Exception as e:
        # 其他错误（401 Key 错、429 限流、网络断）统一降级
        return f"关于'{query}'的搜索服务暂时不可用（{str(e)}）。"


# 本地测试入口：直接运行 python tools/search.py 可调试
if __name__ == "__main__":
    print(web_search("黑洞是什么"))