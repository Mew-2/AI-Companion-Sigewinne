import re
from typing import Dict, Callable, List
import logging

logger = logging.getLogger(__name__)  # 模块级 logger


class ReActAgent:
    """
    手写 ReAct 循环：Thought -> Action -> Observation -> ... -> Final Answer
    """

    def __init__(self, tools: Dict[str, callable], max_steps: int = 3):
        self.tools = tools
        self.max_steps = max_steps

    def run(self, user_msg: str, system_prompt: str) -> dict:
        thoughts = []
        actions = []

        # 分离 system 和初始 user content
        system_ctx, user_ctx = self._build_context(system_prompt, user_msg)
        context = user_ctx  # 只有 user 部分会增长

        for step in range(self.max_steps):
            llm_output = self._call_llm(system_ctx, context)

            # 日志记录 LLM 原始输出（截断防刷屏）
            logger.info(f"[Step {step}] LLM原始输出: {llm_output[:300]}")

            if "Final Answer:" in llm_output:
                final_reply = llm_output.split("Final Answer:")[-1].strip()
                logger.info(f"[Step {step}] 直接回答: {final_reply[:100]}")
                return {"reply": final_reply, "thoughts": thoughts, "actions": actions}

            thought = self._extract_thought(llm_output)
            action_str = self._extract_action(llm_output)

            logger.info(f"[Step {step}] Thought: {thought[:100]}")
            logger.info(f"[Step {step}] Action: {action_str}")

            if not action_str:
                logger.warning(f"[Step {step}] LLM未按格式输出Action，强制降级")
                return {
                    "reply": "希格雯思考得有点混乱...",
                    "thoughts": thoughts,
                    "actions": actions,
                }

            thoughts.append(thought)
            actions.append(action_str)

            logger.info(f"[Step {step}] 原始Action字符串: {action_str}")
            tool_name, tool_params = self._parse_action(action_str)
            logger.info(
                f"[Step {step}] 解析结果: tool={tool_name}, params={tool_params}"
            )

            tool_name, tool_params = self._parse_action(action_str)
            if tool_name in self.tools:
                observation = self.tools[tool_name](**tool_params)
                logger.info(f"[Step {step}] Observation: {observation[:100]}")
            else:
                observation = f"错误：没有 {tool_name} 这个工具"
                logger.error(f"[Step {step}] 工具不存在: {tool_name}")

            context += f"\nObservation: {observation}\n"

        return {
            "reply": "希格雯查了好多资料，先总结到这里吧~",
            "thoughts": thoughts,
            "actions": actions,
        }

    def _build_context(self, system_prompt: str, user_msg: str) -> tuple[str, str]:
        """返回 (system_content, user_content)"""
        tools_desc = "\n".join(
            [
                f"- {name}{self._get_signature(func)}"
                for name, func in self.tools.items()
            ]
        )

        # system 放：人设 + 工具说明 + 格式规则 + few-shot 示例（静态指令）
        system_content = f"""{system_prompt}

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

    def _call_llm(self, system_content: str, user_content: str) -> str:
        """基类 mock，子类覆盖"""
        return "Final Answer: 这是模拟回复，实际接入 LLM 后替换。"

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
        logger.info(f"_parse_action 原始参数字符串: {params_str}")

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
                        logger.info(f"_parse_action 推断参数: {params_keys[0]}={val}")
                else:
                    params["query"] = val

            for key, val in pairs:
                params[key] = val

        logger.info(f"_parse_action 最终参数: {params}")
        return tool_name, params

    def _get_signature(self, func: Callable) -> str:
        """获取函数签名用于 Prompt 描述"""
        import inspect

        sig = inspect.signature(func)
        return str(sig)
