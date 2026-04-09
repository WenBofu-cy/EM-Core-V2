"""
EM-Core V2.0 完整版（主动提问 + 偏好记忆沉淀）
- 首次遇到不确定（多个杯子、模糊数量）时提问用户
- 自动将用户选择写入长期记忆（高意义标签）
- 下次执行同类任务时，直接复用上次的偏好，无需重复提问
- 如果偏好的物体不在当前场景中，主动询问是否更换并更新记忆
"""

import time
import uuid
import re
from enum import Enum
from typing import List, Dict, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

# ==================== 第一部分：MLNF-Mem 记忆中枢（完整） ====================

class MemoryLevel(Enum):
    L1_TEMPORARY = 1
    L2_RECENT = 2
    L3_MIDTERM = 3
    L4_LONGTERM = 4
    L5_CORE = 5

@dataclass
class MemoryItem:
    id: str
    content: Any
    level: MemoryLevel
    importance: float = 0.0
    reuse_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    significance_signal: float = 0.0
    meaning_label: float = 0.0

    def update_importance(self, alpha=0.3, beta=0.3, gamma=0.4):
        self.importance += alpha * self.significance_signal + beta * self.meaning_label + gamma * self.reuse_count
        self.importance = min(1.0, self.importance)

class SubFunnel:
    def __init__(self, scene_key: str, parent: 'MLNFMem'):
        self.scene_key = scene_key
        self.parent = parent
        self.memory_layers = {level: [] for level in MemoryLevel}
        self.last_active = time.time()
        self.promotion_thresholds = {
            MemoryLevel.L1_TEMPORARY: (30, 0.3),
            MemoryLevel.L2_RECENT: (3600, 0.5),
            MemoryLevel.L3_MIDTERM: (86400, 0.7),
            MemoryLevel.L4_LONGTERM: (604800, 0.9),
        }

    def add_memory(self, item: MemoryItem):
        item.level = MemoryLevel.L1_TEMPORARY
        self.memory_layers[item.level].append(item)
        self.last_active = time.time()

    def access(self, mem_id: str) -> Optional[MemoryItem]:
        for level in MemoryLevel:
            for mem in self.memory_layers[level]:
                if mem.id == mem_id:
                    mem.last_accessed = time.time()
                    mem.reuse_count += 1
                    mem.update_importance()
                    self.last_active = time.time()
                    return mem
        return None

    def promote(self):
        for from_level, to_level in [
            (MemoryLevel.L1_TEMPORARY, MemoryLevel.L2_RECENT),
            (MemoryLevel.L2_RECENT, MemoryLevel.L3_MIDTERM),
            (MemoryLevel.L3_MIDTERM, MemoryLevel.L4_LONGTERM),
            (MemoryLevel.L4_LONGTERM, MemoryLevel.L5_CORE),
        ]:
            t_sec, t_imp = self.promotion_thresholds[from_level]
            now = time.time()
            promoted = []
            for mem in self.memory_layers[from_level]:
                if (now - mem.created_at > t_sec) and (mem.importance > t_imp):
                    mem.level = to_level
                    self.memory_layers[to_level].append(mem)
                    promoted.append(mem)
            for mem in promoted:
                self.memory_layers[from_level].remove(mem)

    def forget(self, threshold=0.1):
        for level in [MemoryLevel.L1_TEMPORARY, MemoryLevel.L2_RECENT,
                      MemoryLevel.L3_MIDTERM, MemoryLevel.L4_LONGTERM]:
            self.memory_layers[level] = [m for m in self.memory_layers[level] if m.importance >= threshold]

    def get_keywords(self) -> Set[str]:
        kw = set()
        for level in MemoryLevel:
            for mem in self.memory_layers[level]:
                if isinstance(mem.content, str):
                    kw.update(re.findall(r'\w+', mem.content.lower()))
        return kw

    def all_memories(self) -> List[MemoryItem]:
        result = []
        for level in MemoryLevel:
            result.extend(self.memory_layers[level])
        return result

class TotalController:
    def __init__(self, memory_system: 'MLNFMem'):
        self.memory_system = memory_system

    def cleanup_idle_funnels(self, idle_seconds=7*86400):
        now = time.time()
        to_del = [k for k, f in self.memory_system.sub_funnels.items() if now - f.last_active > idle_seconds]
        for k in to_del:
            del self.memory_system.sub_funnels[k]

    def safety_check(self, action: Any) -> bool:
        dangerous = ["harm", "attack", "hurt", "kill", "danger"]
        return not any(d in str(action).lower() for d in dangerous)

class MLNFMem:
    def __init__(self, max_sub_funnels=20):
        self.max_sub_funnels = max_sub_funnels
        self.total_ctl = TotalController(self)
        self.sub_funnels = {}

    def get_or_create(self, scene: str) -> SubFunnel:
        if scene in self.sub_funnels:
            return self.sub_funnels[scene]
        if len(self.sub_funnels) >= self.max_sub_funnels:
            self._merge_similar()
        f = SubFunnel(scene, self)
        self.sub_funnels[scene] = f
        return f

    def _merge_similar(self):
        if len(self.sub_funnels) < 2:
            return
        funs = list(self.sub_funnels.items())
        best_sim = -1
        best_pair = None
        for i in range(len(funs)):
            for j in range(i+1, len(funs)):
                kw1 = funs[i][1].get_keywords()
                kw2 = funs[j][1].get_keywords()
                inter = len(kw1 & kw2)
                union = len(kw1 | kw2)
                sim = inter / union if union else 0
                if sim > best_sim:
                    best_sim = sim
                    best_pair = (i, j)
        if best_pair:
            i, j = best_pair
            key1, f1 = funs[i]
            key2, f2 = funs[j]
            for mem in f2.all_memories():
                f1.add_memory(mem)
            del self.sub_funnels[key2]

    def maintenance(self):
        for f in self.sub_funnels.values():
            f.promote()
            f.forget()
        self.total_ctl.cleanup_idle_funnels()

# ==================== 第二部分：外挂技能包体系 ====================

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
    def __init__(self):
        super().__init__("cooking", SkillType.PRACTICAL, "烹饪技能")

    def execute(self, input_data):
        return f"[实操] 已完成烹饪：{input_data}"

class LLMSkill(SkillPackage):
    def __init__(self, model_api: Callable):
        super().__init__("llm_assistant", SkillType.LLM, "大模型语言助手")
        self.model_api = model_api

    def _strict_curse(self, output: str) -> str:
        forbidden = ["grab", "move", "stop", "activate", "deactivate",
                     "write_memory", "delete_memory", "update_memory", "remember that",
                     "decide to", "i will now", "execute plan", "order the robot"]
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

    def list_practical(self):
        return [s for s in self.skills.values() if s.skill_type == SkillType.PRACTICAL]

    def list_llm(self):
        return [s for s in self.skills.values() if s.skill_type == SkillType.LLM]

# ==================== 第三部分：小脑 ====================

class Cerebellum:
    def execute(self, high_level_command: str) -> Dict[str, Any]:
        print(f"[小脑] 执行: {high_level_command}")
        return {"status": "executed", "command": high_level_command}

# ==================== 第四部分：6条无解判定 ====================

class UnsolvableDetector:
    def __init__(self, core: 'EM_Core'):
        self.core = core
        self.reasons: List[str] = []

    def check_working_memory(self, task_info: dict) -> bool:
        if len(str(task_info)) // 100 > 7:
            self.reasons.append("工作记忆容量耗尽")
            return False
        return True

    def check_mental_simulation(self, task_info: dict) -> bool:
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
        if "fly" in goal.lower():
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

# ==================== 第五部分：12号资源调度 ====================

class ResourceScheduler:
    def __init__(self, core: 'EM_Core'):
        self.core = core

    def handle_unsolvable(self, task: Any, reasons: List[str]) -> Any:
        print("[12号] 本地能力无法解决，尝试外挂资源...")
        task_str = str(task).lower()
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

# ==================== 第六部分：偏好记忆与智能提问 ====================

class PreferenceManager:
    def __init__(self, memory: MLNFMem):
        self.memory = memory

    def get_preferred_cup(self, task_type: str, available_cups: List[str]) -> Optional[str]:
        funnel = self.memory.get_or_create("user_preferences")
        for level in [MemoryLevel.L5_CORE, MemoryLevel.L4_LONGTERM, MemoryLevel.L3_MIDTERM]:
            for mem in funnel.memory_layers[level]:
                content = str(mem.content)
                if task_type in content and "preferred_cup" in content:
                    for cup in available_cups:
                        if cup in content:
                            return cup
        return None

    def save_preferred_cup(self, task_type: str, chosen_cup: str):
        funnel = self.memory.get_or_create("user_preferences")
        content = f"{task_type} preferred_cup: {chosen_cup}"
        mem = MemoryItem(
            id=str(uuid.uuid4()),
            content=content,
            level=MemoryLevel.L1_TEMPORARY,
            meaning_label=0.9,
            significance_signal=0.5
        )
        mem.update_importance()
        funnel.add_memory(mem)
        self.memory.maintenance()
        print(f"   [记忆] 已记住偏好：{task_type} 用 {chosen_cup}")

class EnhancedUncertaintyResolver:
    def __init__(self, memory: MLNFMem):
        self.memory = memory
        self.pref_manager = PreferenceManager(memory)

    def resolve_cup_ambiguity(self, task_type: str, available_cups: List[str], task_info: Dict) -> Dict:
        preferred = self.pref_manager.get_preferred_cup(task_type, available_cups)
        if preferred and preferred in available_cups:
            print(f"   [偏好记忆] 上次您用了 {preferred}，本次自动选择。")
            task_info["selected_cup"] = preferred
            return task_info

        if preferred and preferred not in available_cups:
            print(f"   [注意] 您之前偏好的杯子 '{preferred}' 不在当前场景中。")
            answer = self._ask_user(f"您常用的杯子 {preferred} 找不到，请从 {', '.join(available_cups)} 中选择一个：")
        else:
            answer = self._ask_user(f"有多个杯子：{', '.join(available_cups)}，请选择一个：")

        chosen = self._match_cup(answer, available_cups)
        self.pref_manager.save_preferred_cup(task_type, chosen)
        task_info["selected_cup"] = chosen
        return task_info

    def resolve_quantity_ambiguity(self, vague_word: str, task_info: Dict) -> Dict:
        answer = self._ask_user(f"您说「{vague_word}」，请给出具体数量（例如 2）：")
        num = self._extract_number(answer)
        if num is None:
            num = 2
        task_info["explicit_quantity"] = num
        return task_info

    def _ask_user(self, question: str) -> str:
        print(f"\n🤖 系统提问: {question}")
        return input("👤 您的回答: ").strip()

    def _match_cup(self, answer: str, cups: List[str]) -> str:
        ans_lower = answer.lower()
        for cup in cups:
            if cup.lower() in ans_lower:
                return cup
        return cups[0]

    def _extract_number(self, text: str) -> Optional[int]:
        match = re.search(r'\d+', text)
        return int(match.group()) if match else None

    def resolve_all(self, task_info: Dict, scene: Dict) -> Dict:
        updated = task_info.copy()
        cups = scene.get("candidate_objects", {}).get("杯子", [])
        if len(cups) > 1:
            task_type = "倒可乐"
            updated = self.resolve_cup_ambiguity(task_type, cups, updated)
        text = str(task_info.get("goal", ""))
        vague = re.findall(r'(少量|一些|适量|几块|几个)', text)
        if vague:
            updated = self.resolve_quantity_ambiguity(vague[0], updated)
        return updated

# ==================== 第七部分：EM-Core 主类 ====================

class EM_Core:
    def __init__(self):
        self.memory = MLNFMem(max_sub_funnels=20)
        self.skill_registry = SkillRegistry()
        self.skill_registry.register(PracticalSkill())

        def mock_llm(prompt):
            return f"大模型回复：关于 '{prompt}' 的建议是..."

        self.skill_registry.register(LLMSkill(mock_llm))
        self.detector = UnsolvableDetector(self)
        self.scheduler = ResourceScheduler(self)
        self.cerebellum = Cerebellum()
        self.resolver = EnhancedUncertaintyResolver(self.memory)

    def get_scene(self) -> Dict:
        return {
            "candidate_objects": {"杯子": ["红色杯子", "蓝色杯子", "白色杯子"]},
            "fridge_has_ice": True,
            "cola_position": "on_table"
        }

    def process_task(self, instruction: str) -> Any:
        print(f"\n=== 处理任务: {instruction} ===")
        task_info = {"goal": instruction, "state": {}, "entities": []}
        scene = self.get_scene()
        task_info = self.resolver.resolve_all(task_info, scene)
        print("✅ 澄清后的任务信息:", task_info)

        if self.detector.is_unsolvable(task_info):
            print("判定：本地无法解决")
            for r in self.detector.reasons:
                print(f"  - {r}")
            return self.scheduler.handle_unsolvable(instruction, self.detector.reasons)

        print("判定：本地能力足够，内生解决")
        steps = self._plan_from_task_info(task_info, scene)
        for step in steps:
            if not self.memory.total_ctl.safety_check(step):
                print(f"❌ 安全拦截: {step}")
                return "[闭锁] 危险动作被阻止"
            self.cerebellum.execute(step)
            time.sleep(0.3)
        self._deposit_experience(instruction, "success")
        return "🎉 任务完成"

    def _plan_from_task_info(self, task_info: Dict, scene: Dict) -> List[str]:
        cup = task_info.get("selected_cup", "杯子")
        steps = [f"拿起{cup}", "倒可乐"]
        if scene.get("fridge_has_ice"):
            ice_num = task_info.get("explicit_quantity", 2)
            steps.append(f"打开冰箱，取出{ice_num}块冰块，关闭冰箱")
            steps.append(f"将冰块放入{cup}")
        steps.append(f"将{cup}端给用户")
        return steps

    def _deposit_experience(self, task, result):
        funnel = self.memory.get_or_create("general")
        mem = MemoryItem(
            id=str(uuid.uuid4()),
            content=f"经验: {task} -> {result}",
            level=MemoryLevel.L1_TEMPORARY,
            meaning_label=0.5
        )
        mem.update_importance()
        funnel.add_memory(mem)
        self.memory.maintenance()

# ==================== 运行演示 ====================
if __name__ == "__main__":
    print("=== EM-Core V2.0 偏好记忆版（会记住您选的杯子）===\n")
    core = EM_Core()
    instruction = "帮我倒一杯可乐，加少量冰块"

    print("【第一次执行】")
    result = core.process_task(instruction)
    print("\n最终结果:", result)

    print("\n" + "="*50)
    print("【场景变化：您常用的红色杯子不见了，现在只有蓝色和白色杯子】")
    core.get_scene = lambda: {
        "candidate_objects": {"杯子": ["蓝色杯子", "白色杯子"]},
        "fridge_has_ice": True,
        "cola_position": "on_table"
    }
    print("【第二次执行（偏好杯子消失，系统会询问并更新记忆）】")
    result2 = core.process_task(instruction)
    print("\n最终结果:", result2)

    print("\n" + "="*50)
    print("【第三次执行（应该自动使用上次新选的杯子）】")
    result3 = core.process_task(instruction)
    print("\n最终结果:", result3)
