import re
from typing import Dict, Callable, List, AsyncIterator
import logging
import asyncio

logger = logging.getLogger(__name__)


class ReActAgent:
    """
    手写 ReAct 循环：Thought -> Action -> Observation -> ... -> Final Answer
    支持非流式(run)和流式(run_stream)两种模式。
    """

    def __init__(self, tools: Dict[str, callable], max_steps: int = 3):
        self.tools = tools
        self.max_steps = max_steps

    def _run_react_planning(
        self, system_ctx: str, user_ctx: str
    ) -> tuple[str, List[str], List[str], str | None, str | None]:
        """
        非流式跑 ReAct 规划循环，收集工具调用和观察结果。
        返回: (final_context, thoughts, actions, used_tool, direct_answer)
        """
        thoughts = []
        actions = []
        context = user_ctx
        used_tool = None
        direct_answer = None

        for step in range(self.max_steps):
            llm_output = self._call_llm(system_ctx, context)

            if "Final Answer:" in llm_output:
                direct_answer = llm_output.split("Final Answer:")[-1].strip()
                logger.info(f"[Step {step}] 直接回答（无需工具）")
                break

            thought = self._extract_thought(llm_output)
            action_str = self._extract_action(llm_output)

            if not action_str:
                logger.warning(f"[Step {step}] 格式异常，终止规划")
                logger.warning(f"[Step {step}] LLM原始输出:\n{llm_output}")
                break

            thoughts.append(thought)
            actions.append(action_str)

            tool_name, tool_params = self._parse_action(action_str)
            logger.info(f"[Step {step}] 调用工具: {action_str}")

            if tool_name in self.tools:
                observation = self.tools[tool_name](**tool_params)
                if used_tool is None:
                    used_tool = tool_name
                logger.info(f"[Step {step}] 工具返回: {len(observation)} 字")
            else:
                observation = f"错误：没有 {tool_name} 这个工具"
                logger.error(f"[Step {step}] 工具不存在: {tool_name}")

            context += f"\nObservation: {observation}\n"

        return context, thoughts, actions, used_tool, direct_answer

    def run(self, user_msg: str, system_prompt: str) -> dict:
        """
        标准非流式 ReAct（兼容旧版 /chat 接口）。
        """
        system_ctx, user_ctx = self._build_context(system_prompt, user_msg)
        context, thoughts, actions, used_tool, direct_answer = self._run_react_planning(
            system_ctx, user_ctx
        )

        if direct_answer:
            return {
                "reply": direct_answer,
                "thoughts": thoughts,
                "actions": actions,
                "used_tool": used_tool,
            }

        # 达到 max_steps 或异常：用人设 + 工具结果生成最终回复
        answer_system = f"""{system_prompt}

【规则】基于以上工具调用得到的信息，以希格雯的身份直接回复用户。
只输出回复内容，不要带 Thought/Action/Observation 前缀。"""
        answer_user = f"用户问题：{user_msg}\n\n工具调用过程：\n{context}\n\n希格雯说："

        summary = self._call_llm(answer_system, answer_user)
        final_reply = summary.replace("Final Answer:", "").strip()

        return {
            "reply": final_reply,
            "thoughts": thoughts,
            "actions": actions,
            "used_tool": used_tool,
        }

    async def run_stream(
        self, user_msg: str, system_prompt: str
    ) -> AsyncIterator[dict]:
        """
        流式 ReAct：
        1. 非流式完成规划（Thought/Action/Observation）
        2. 干净 prompt 流式生成 Final Answer（真流式，非模拟）
        """
        system_ctx, user_ctx = self._build_context(system_prompt, user_msg)

        # 阶段 1：规划放线程池，避免阻塞 FastAPI 事件循环
        context, thoughts, actions, used_tool, direct_answer = await asyncio.to_thread(
            self._run_react_planning, system_ctx, user_ctx
        )

        yield {"type": "meta", "used_tool": used_tool, "thoughts": thoughts}

        logger.info(
            f"[ReAct] Thoughts: {thoughts}, Actions: {actions}, Tool: {used_tool}"
        )

        # 阶段 2：生成最终回复
        if direct_answer:
            # 无需工具，LLM 规划阶段已直接给出 Final Answer，逐字流式输出
            for char in direct_answer:
                yield {"type": "text", "content": char}
        else:
            # 需要工具：system prompt 彻底隔离 ReAct 规则，只保留人设 + 强约束
            clean_system = f"""{system_prompt}

【绝对规则】你现在直接对用户说话，像希格雯一样自然聊天。
- 禁止输出 Thought、Action、Observation、Final Answer 等任何标签或英文前缀
- 禁止暴露查询过程（如"我查了一下天气"）
- 直接把信息自然融入回复，语气温柔，只说中文"""

            # context 里已包含完整 ReAct 历史（含 Observation 结果）
            answer_user = f"请基于以下信息直接回复用户，不要加任何标签：\n\n{context}\n\n用户原始问题：{user_msg}\n\n希格雯说："

            async for token in self._call_llm_stream(clean_system, answer_user):
                yield {"type": "text", "content": token}

        yield {"type": "done"}

    def _call_llm(self, system_content: str, user_content: str) -> str:
        """基类 mock，子类覆盖为真实 LLM 调用"""
        return "Final Answer: 这是模拟回复，实际接入 LLM 后替换。"

    async def _call_llm_stream(
        self, system_content: str, user_content: str
    ) -> AsyncIterator[str]:
        """基类 mock，子类覆盖为真实 LLM 流式调用。yield 每个 token."""
        yield "这是模拟流式回复，实际接入 LLM 后替换。"

    def _build_context(self, system_prompt: str, user_msg: str) -> tuple[str, str]:
        """返回 (system_content, user_content)"""
        tools_desc = "\n".join(
            [
                f"- {name}{self._get_signature(func)}"
                for name, func in self.tools.items()
            ]
        )

        # 只留极简身份标识 + 工具规则，不渗入完整人设/RAG/历史，避免角色扮演干扰工具决策
        system_content = f"""你是希格雯，同时也需要判断用户是否需要调用实时工具来获取信息。

你可以使用以下工具：
{tools_desc}

【硬规则——必须调用工具】
- 用户询问天气、气温、温度、空气质量、湿度、风向等实时/时效性信息 → 必须调用 weather 或 search
- 用户询问实时新闻、热搜、股价、比赛结果等 → 必须调用 search
- 用户说"看下/查一下/看一下/搜一下/搜索/查查/查一查" + 天气/城市/新闻等 → 必须调用对应工具
- 即使你了解一些背景常识，对于实时数据也不能绕过工具

【格式】
Thought: 分析是否需要工具
Action: 工具名称(参数)

当不需要工具时，直接输出：
Final Answer: 回复内容

注意：
- 每次只能调用一个工具
- Action 参数必须用英文单引号包裹，如 weather(city='上海')

示例：

Question: 北京今天天气怎么样？
Thought: 用户问天气，需要调用天气工具
Action: weather(city='北京')

Question: 查一下上海今天天气
Thought: 用户想查天气，需要调用天气工具
Action: weather(city='上海')

Question: 看下上海天气
Thought: 用户想看天气，需要调用天气工具
Action: weather(city='上海')

Question: 搜一下今天的新闻
Thought: 用户想搜索新闻，需要调用搜索工具
Action: search(query='今天新闻')

Question: 你头发是什么颜色的？
Thought: 用户问的是角色设定常识，不需要工具
Final Answer: 主人，我的头发是蓝色的哦~

Question: 你好
Thought: 用户打招呼，不需要工具
Final Answer: 主人好呀~"""

        user_content = f"Question: {user_msg}\nThought:"

        return system_content, user_content

    def _extract_thought(self, output: str) -> str:
        """从 LLM 输出提取 Thought"""
        match = re.search(
            r"Thought:\s*(.+?)(?=\nAction:|\nFinal Answer:|$)", output, re.DOTALL
        )
        return match.group(1).strip() if match else ""

    def _extract_action(self, output: str) -> str:
        """从 LLM 输出提取 Action"""
        match = re.search(r"Action:\s*(.+?)(?=\n|$)", output)
        return match.group(1).strip() if match else ""

    def _parse_action(self, action_str: str):
        """解析 Action 字符串，支持 weather(city='上海') 和 weather(上海)"""
        match = re.match(r"(\w+)\((.*)\)", action_str)
        if not match:
            logger.warning(f"_parse_action 无法解析: {action_str}")
            return action_str, {}

        tool_name = match.group(1)
        params_str = match.group(2).strip()
        logger.debug(f"_parse_action 原始参数字符串: {params_str}")

        params = {}
        if params_str:
            # 1. 匹配 key='value' 或 key="value"
            pairs = re.findall(r"(\w+)\s*=\s*['\"]([^'\"]+)['\"]", params_str)

            # 2. 匹配 key=value（无引号）
            if not pairs:
                pairs = re.findall(r"(\w+)\s*=\s*([^,\s]+)", params_str)

            # 3. 如果还是没匹配到（如 "上海"），把整个字符串当作第一个参数
            if not pairs:
                val = params_str.strip("'\"").strip()
                if tool_name in self.tools:
                    import inspect

                    sig = inspect.signature(self.tools[tool_name])
                    params_keys = list(sig.parameters.keys())
                    if params_keys:
                        params[params_keys[0]] = val
                        logger.debug(f"_parse_action 推断参数: {params_keys[0]}={val}")
                else:
                    params["query"] = val

            for key, val in pairs:
                params[key] = val

        logger.debug(f"_parse_action 最终参数: {params}")
        return tool_name, params

    def _get_signature(self, func: Callable) -> str:
        """获取函数签名用于 Prompt 描述"""
        import inspect

        sig = inspect.signature(func)
        return str(sig)
