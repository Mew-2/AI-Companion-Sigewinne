def get_weather(city: str) -> str:
    """查询城市天气（模拟实现，实际可接和风/心知 API）"""
    # 模拟数据，面试时可说"这里留接口接真实 API"
    mock_data = {
        "上海": "25°C，晴天，适合出门~",
        "北京": "18°C，多云，记得带外套",
        "广州": "30°C，雷阵雨，带伞哦",
    }
    return f"{city}今天{mock_data.get(city, '天气不错，适合散步')}"
