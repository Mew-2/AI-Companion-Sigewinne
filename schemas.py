from pydantic import BaseModel, Field
from typing import Optional, List


class ChatRequest(BaseModel):
    msg: str = Field(..., min_length=1, max_length=2000, description="用户输入")
    session_id: Optional[str] = Field(default="default", description="会话ID")


class MemoryItem(BaseModel):
    fact: str
    keywords: Optional[str] = None
    importance: Optional[int] = 5


class ChatResponse(BaseModel):
    reply: str
    emotion: Optional[str] = "normal"
    affection: Optional[int] = 0
    recalled_memories: List[MemoryItem] = []
    used_tool: Optional[str] = None
