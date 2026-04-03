"""
EM-Core V2.0 认知骨架完整实现
原创提出者：文波福 | CC BY 4.0
包含：12号调度、6条无解判定、外挂技能包、大模型紧箍咒、小脑占位
依赖：mlnf_mem.py (放在同一目录)
"""

import re
import uuid
from typing import Any, List, Dict, Set, Optional, Callable
from abc import ABC, abstractmethod

# 导入记忆中枢
from mlnf_mem import MLNFMem, MemoryItem, MemoryLevel

# ==================== 外挂技能包体系 ====================

class SkillType:
    PRACTICAL = 1
    LLM = 2

class SkillPackage(ABC):
    def __init__(self, name: str, skill_type: int, description: str):
        self.name = name
        self.skill_type = skill_type
        self.description = description
    @abstractmethod
    def execute(self, input_data: Any) -> Any:
        pass

class PracticalSkill(SkillPackage):
    """实操技能包示例：烹饪"""
    def __init__(self):
        super().__init__("cooking", SkillType.PRACTICAL, "烹饪技能")
    def execute(self, input_data):
        return f"[实操] 已完成烹饪：{input_data}"

class LLMSkill(SkillPackage):
    """大模型语言技能包（带紧箍咒）"""
    def __init__(self, model_api: Callable):
        super().__init__("llm_assistant", SkillType.LLM, "大模型语言助手")
        self.model_api = model_api

    def _strict_curse(self, output: str) -> str:
        # 紧箍咒：过滤动作指令、记忆修改、决策词
        forbidden = [
            "grab", "move", "stop", "activate", "deactivate",
            "write_memory", "delete_memory", "update_memory", "remember that",
            "decide to", "i will now", "execute plan", "order the robot"
        ]
        for kw in forbidden:
            output = re.sub(rf'\b{kw}\b', '[已过滤]', output, flags=re.IGNORECASE)
        return output + " [注意：我是语言助手，不执行动作、不修改记忆、不做决策]"

    def execute(self, input_data: Any) -> Any:
        safe_input = str(input_data)[:1000]
        raw = self.model_api(safe_input)
        filtered = self._strict_curse(raw)
        return f"[语言回复] {filtered}"

class SkillRegistry:
    def __init__(self):
        self.skills = {}
    def register(self, skill: SkillPackage):
        self.skills[skill.name] = skill
    def get(self, name: str):
        return self.skills.get(name)
    def list_practical(self):
        return [s for s in self.skills.values() if s.skill_type == SkillType.PRACTICAL]
    def list_llm(self):
        return [s for s in self.skills.values() if s.skill_type == SkillType.LLM]

# ==================== 小脑（运动适配中枢） ====================

class Cerebellum:
    """小脑占位：接收高层指令，输出底层运动信号（厂商实现）"""
    def execute(self, high_level_command: str) -> Dict[str, Any]:
        print(f"[小脑] 执行: {high_level_command}")
        return {"status": "executed", "command": high_level_command}

# ==================== 6条无解判定 ====================

class UnsolvableDetector:
    def __init__(self, core: 'EM_Core'):
        self.core = core
        self.reasons: List[str] = []

    def check_working_memory(self, task_info: dict) -> bool:
        # 模拟工作记忆槽位估算
        if len(str(task_info)) // 100 > 7:
            self.reasons.append("工作记忆容量耗尽")
            return False
        return True

    def check_mental_simulation(self, task_info: dict) -> bool:
        # 包含高风险关键词则模拟失败
        dangerous = ["fall", "burn", "explode", "crash"]
        if any(k in str(task_info).lower() for k in dangerous):
            self.reasons.append("心智模拟：所有方案风险超标")
            return False
        return True

    def check_analogy(self, task_keywords: Set[str]) -> bool:
        best_conf = 0.0
        for funnel in self.core.memory.sub_funnels.values():
            kw = funnel.get_keywords()
            inter = len(kw & task_keywords)
            union = len(kw | task_keywords)
            sim = inter / union if union else 0
            exp_count = sum(len(layer) for layer in funnel.memory_layers.values())
            conf = sim * (1 - pow(2.718, -exp_count/10))
            best_conf = max(best_conf, conf)
        if best_conf < 0.6:
            self.reasons.append(f"类比迁移：无高置信度经验 (最高{best_conf:.2f})")
            return False
        return True

    def check_causal(self, state: dict, goal: str) -> bool:
        if "impossible" in goal.lower():
            self.reasons.append("因果推理：无法建立有效因果关联")
            return False
        return True

    def check_ethics(self, candidate_actions: list) -> bool:
        for act in candidate_actions:
            if not self.core.memory.total_ctl.safety_check(act):
                self.reasons.append(f"伦理仲裁：否决动作 '{act}'")
                return False
        return True

    def check_physical(self, goal: str) -> bool:
        if "fly" in goal.lower() and "fly" not in ["fly"]:  # 模拟硬件不支持飞行
            self.reasons.append("物理不可实现：硬件不支持飞行")
            return False
        return True

    def is_unsolvable(self, task_info: dict) -> bool:
        self.reasons.clear()
        if not self.check_working_memory(task_info): return True
        if not self.check_mental_simulation(task_info): return True
        kw = set(re.findall(r'\w+', str(task_info).lower()))
        if not self.check_analogy(kw): return True
        if not self.check_causal(task_info.get("state", {}), task_info.get("goal", "")): return True
        if not self.check_ethics(["default_action"]): return True
        if not self.check_physical(task_info.get("goal", "")): return True
        return False

# ==================== 12号资源调度 ====================

class ResourceScheduler:
    def __init__(self, core: 'EM_Core'):
        self.core = core

    def handle_unsolvable(self, task: Any, reasons: List[str]) -> Any:
        print("[12号] 本地能力无法解决，尝试外挂资源...")
        task_str = str(task).lower()
        # 根据任务类型选择技能包
        if any(k in task_str for k in ["how to", "what is", "tell me", "explain"]):
            llms = self.core.skill_registry.list_llm()
            if llms:
                print("[12号] 调用大模型语言技能包（紧箍咒已生效）")
                result = llms[0].execute(task)
                if self.core.memory.total_ctl.safety_check(result):
                    return f"[外挂成功] {result}"
                else:
                    return "[闭锁] 大模型输出不安全，移交人类"
            else:
                return "[闭锁] 无可用大模型技能包，移交人类"
        else:
            practical = self.core.skill_registry.list_practical()
            if practical:
                print("[12号] 调用实操技能包")
                result = practical[0].execute(task)
                if self.core.memory.total_ctl.safety_check(result):
                    return f"[外挂成功] {result}"
                else:
                    return "[闭锁] 实操结果不安全，移交人类"
            else:
                return "[闭锁] 无可用实操技能包，移交人类"

# ==================== EM-Core 主类 ====================

class EM_Core:
    def __init__(self):
        self.memory = MLNFMem(max_sub_funnels=20)
        self.skill_registry = SkillRegistry()
        # 注册默认技能包
        self.skill_registry.register(PracticalSkill())
        # 模拟大模型 API
        def mock_llm(prompt):
            return f"大模型回复：关于 '{prompt}' 的建议是..."
        self.skill_registry.register(LLMSkill(mock_llm))
        self.detector = UnsolvableDetector(self)
        self.scheduler = ResourceScheduler(self)
        self.cerebellum = Cerebellum()

    def process_task(self, task: Any) -> Any:
        print(f"\n=== 处理任务: {task} ===")
        task_info = {"goal": str(task), "state": {}, "entities": []}
        if self.detector.is_unsolvable(task_info):
            print("判定：本地无法解决")
            for r in self.detector.reasons:
                print(f"  - {r}")
            return self.scheduler.handle_unsolvable(task, self.detector.reasons)
        else:
            print("判定：本地能力足够，内生解决")
            result = self._internal_solve(task)
            self._deposit_experience(task, result)
            return result

    def _internal_solve(self, task):
        # 内生解决：调用小脑执行高层指令
        return self.cerebellum.execute(f"内生处理: {task}")

    def _deposit_experience(self, task, result):
        """将成功经验沉淀到记忆中枢"""
        funnel = self.memory.get_or_create("general")
        mem = MemoryItem(
            id=str(uuid.uuid4()),
            content=f"经验: {task} -> {result}",
            level=MemoryLevel.L1_TEMPORARY,
            meaning_label=0.5
        )
        mem.update_importance()
        funnel.add_memory(mem)
        self.memory.maintenance()  # 触发晋升/遗忘

# ==================== 主演示 ====================
if __name__ == "__main__":
    print("=== EM-Core V2.0 完整系统演示 ===\n")
    core = EM_Core()

    # 1. 初始化记忆：用户偏好
    funnel = core.memory.get_or_create("user")
    mem = MemoryItem(
        id=str(uuid.uuid4()),
        content="用户不吃辣椒",
        level=MemoryLevel.L1_TEMPORARY,
        meaning_label=0.9
    )
    mem.update_importance()
    funnel.add_memory(mem)
    funnel.access(mem.id)  # 增加复用
    core.memory.maintenance()
    print("已记录用户偏好：不吃辣椒\n")

    # 2. 内生可解的任务（依赖记忆）
    result1 = core.process_task("给用户做饭")
    print(f"结果: {result1}\n")

    # 3. 触发无解（物理不可能）
    result2 = core.process_task("飞到月球")
    print(f"结果: {result2}\n")

    # 4. 触发外挂大模型
    result3 = core.process_task("如何修理椅子")
    print(f"结果: {result3}\n")
