import os
import requests
from dotenv import load_dotenv

load_dotenv()
HEFENG_KEY = os.getenv("HEFENG_KEY")
# 从控制台设置里复制你的专属 Host
HEFENG_HOST = os.getenv("HEFENG_HOST", "你的APIHost")  # 例如 abc123.qweatherapi.com


def get_weather(city: str) -> str:
    if not HEFENG_KEY:
        return f"{city}今天天气不错（Key未配置）"

    try:
        # Step 1: GEO 城市搜索（用专属 Host）
        geo_resp = requests.get(
            f"https://{HEFENG_HOST}/geo/v2/city/lookup",
            params={"location": city, "key": HEFENG_KEY},
            timeout=5,
        )
        geo_data = geo_resp.json()
        code = geo_data.get("code", "999")

        if code != "200":
            return f"{city}GEO查询失败（错误码: {code}）"

        locations = geo_data.get("location", [])
        if not locations:
            return f"找不到城市：{city}"

        location_id = locations[0]["id"]

        # Step 2: 实况天气（同一个专属 Host）
        weather_resp = requests.get(
            f"https://{HEFENG_HOST}/v7/weather/now",
            params={"location": location_id, "key": HEFENG_KEY},
            timeout=5,
        )
        weather_data = weather_resp.json()
        now = weather_data.get("now", {})

        return f"{city}今天{now.get('text', '未知')}，{now.get('temp', '?')}°C"

    except Exception as e:
        return f"{city}天气查询失败（{str(e)}）"


if __name__ == "__main__":
    print(get_weather("上海"))
