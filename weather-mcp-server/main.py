import os
import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
from starlette.responses import JSONResponse
import uvicorn

# 创建 MCP 服务器实例
server = Server("weather-wttr-server")

# --- MCP 工具定义 ---
@server.list_tools()
async def list_tools():
    return [{
        "name": "get_weather",
        "description": "获取指定城市的实时天气（基于 wttr.in）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名称，如 Beijing、London"},
                "lang": {"type": "string", "description": "语言代码，如 zh 为中文", "default": "en"}
            },
            "required": ["city"]
        }
    }]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name != "get_weather":
        raise ValueError(f"未知工具: {name}")
    city = arguments["city"]
    lang = arguments.get("lang", "en")
    async with httpx.AsyncClient() as client:
        url = f"https://wttr.in/{city}?format=j1&lang={lang}&m"
        resp = await client.get(url, timeout=10.0)
        if resp.status_code != 200:
            return f"无法获取 {city} 的天气信息。"
        data = resp.json()
        try:
            current = data["current_condition"][0]
            area = data["nearest_area"][0]["areaName"][0]["value"]
            country = data["nearest_area"][0]["country"][0]["value"]
            temp = current["temp_C"]
            desc = current["weatherDesc"][0]["value"]
            return f"📍 {area}, {country}\n🌡️ {temp}°C, {desc}"
        except (KeyError, IndexError):
            return f"无法解析 {city} 的天气数据。"

# --- SSE 传输配置 ---
sse = SseServerTransport("/messages")

async def handle_sse(request: Request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())

# --- 健康检查端点 (对 Render 很重要) ---
async def health_check(request: Request):
    return JSONResponse({"status": "healthy"})

# --- Starlette 应用 ---
app = Starlette(
    routes=[
        Route("/health", endpoint=health_check), # 健康检查路由
        Route("/sse", endpoint=handle_sse),      # SSE 连接路由
        Mount("/messages", app=sse.handle_post_message),
    ]
)

# --- 启动方式 (Render 会用到) ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000)) # Render 会动态分配端口
    uvicorn.run(app, host="0.0.0.0", port=port)