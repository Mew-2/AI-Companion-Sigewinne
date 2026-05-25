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

        # 达到 max_steps 或异常，基于最终上下文生成总结
        answer_system = (
            system_ctx
            + "\n\n【规则】基于以上思考和观察，请给出对用户的最终回复。"
            + "只输出回复内容，不要带 Thought/Action/Observation 前缀。"
        )
        answer_user = f"用户问题：{user_msg}\n\n请直接回答："

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

        # system 放：人设 + 工具说明 + 格式规则 + few-shot 示例（静态指令）
        system_content = f"""【绝对规则】无论用户问什么，你必须先输出 Thought: 和 Action: 或 Final Answer:。
禁止直接以"主人"开头回复。只有 Final Answer: 后面才允许扮演希格雯。

{system_prompt}

你可以使用以下工具：
{tools_desc}

请按以下格式思考并行动：
Thought: 你的思考过程（分析用户需要什么信息）
Action: 工具名称(参数)
Observation: 工具返回结果（由系统自动填入）

当不需要再调用工具时，直接输出：
Final Answer: 给用户的最终回复

注意：
- 每次只能调用一个工具
- 如果用户问题不需要工具，直接 Final Answer
- 如果工具调用失败，说明原因并继续
- Action 的参数必须用英文单引号包裹，如 weather(city='上海')
- **当你看到 Observation 后，请总结信息并输出 Final Answer**

示例1（不需要工具）：
Question: 你好
Thought: 用户打招呼，不需要工具
Final Answer: 你好呀主人~

示例2（需要工具，两轮循环）：
Question: 北京今天天气怎么样？
Thought: 用户问天气，我需要查天气工具
Action: weather(city='北京')
Observation: 北京今天18°C，多云
Thought: 我已经获得天气信息，可以直接回答用户了
Final Answer: 主人，北京今天18°C多云，记得带外套哦~"""

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
