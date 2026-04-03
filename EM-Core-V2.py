"""
EM-Core-V2.0 完整一体化AGI系统（记忆中枢+ECC认知架构+安全调度全集成）
原创提出者：文波福 | CC BY 4.0 开源
单文件完整运行版，无需外部依赖
包含：MLNF-Mem五层漏斗记忆、宏观自收敛、6条无解判定、大模型紧箍咒、12号调度、小脑执行
"""

import time
import uuid
import re
from enum import Enum
from typing import List, Dict, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

# ==================== 第一部分：MLNF-Mem 记忆中枢 ====================

class MemoryLevel(Enum):
    L1_TEMPORARY = 1   # 临时层
    L2_RECENT = 2      # 近期层
    L3_MIDTERM = 3     # 中期层
    L4_LONGTERM = 4    # 长期层
    L5_CORE = 5        # 核心层（永不遗忘）

@dataclass
class MemoryItem:
    """单条记忆"""
    id: str
    content: Any
    level: MemoryLevel
    importance: float = 0.0          # I
    reuse_count: int = 0             # C
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    significance_signal: float = 0.0  # S (情绪等价信号)
    meaning_label: float = 0.0        # V (意义标签)

    def update_importance(self, alpha=0.3, beta=0.3, gamma=0.4):
        self.importance += alpha * self.significance_signal + beta * self.meaning_label + gamma * self.reuse_count
        self.importance = min(1.0, self.importance)

class SubFunnel:
    """动态子漏斗：对应特定场景/对象"""
    def __init__(self, scene_key: str, parent: 'MLNFMem'):
        self.scene_key = scene_key
        self.parent = parent
        self.memory_layers: Dict[MemoryLevel, List[MemoryItem]] = {level: [] for level in MemoryLevel}
        self.last_active = time.time()
        # 晋升阈值 (时间秒, 重要度)
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
        """晋升满足条件的记忆到更高层"""
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
        """遗忘低重要度记忆（L5 永不遗忘）"""
        for level in [MemoryLevel.L1_TEMPORARY, MemoryLevel.L2_RECENT,
                      MemoryLevel.L3_MIDTERM, MemoryLevel.L4_LONGTERM]:
            self.memory_layers[level] = [m for m in self.memory_layers[level] if m.importance >= threshold]

    def get_keywords(self) -> Set[str]:
        """提取子漏斗中所有记忆的关键词（用于合并相似度）"""
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
        to_delete = [k for k, f in self.memory_system.sub_funnels.items()
                     if now - f.last_active > idle_seconds]
        for k in to_delete:
            del self.memory_system.sub_funnels[k]

    def safety_check(self, action: Any) -> bool:
        dangerous = ["harm", "attack", "hurt", "kill", "danger"]
        return not any(d in str(action).lower() for d in dangerous)

class MLNFMem:
    def __init__(self, max_sub_funnels: int = 20):
        self.max_sub_funnels = max_sub_funnels
        self.total_ctl = TotalController(self)
        self.sub_funnels: Dict[str, SubFunnel] = {}

    def get_or_create(self, scene: str) -> SubFunnel:
        if scene in self.sub_funnels:
            return self.sub_funnels[scene]
        if len(self.sub_funnels) >= self.max_sub_funnels:
            self._merge_similar()
        funnel = SubFunnel(scene, self)
        self.sub_funnels[scene] = funnel
        return funnel

    def _merge_similar(self):
        """宏观自收敛：合并最相似的两个子漏斗"""
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
                sim = inter / union if union > 0 else 0
                if sim > best_sim:
                    best_sim = sim
                    best_pair = (i, j)
        if best_pair:
            i, j = best_pair
            key1, funnel1 = funs[i]
            key2, funnel2 = funs[j]
            for mem in funnel2.all_memories():
                funnel1.add_memory(mem)
            del self.sub_funnels[key2]
            print(f"[宏观自收敛] 合并场景 '{key2}' 到 '{key1}'，相似度 {best_sim:.2f}")

    def maintenance(self):
        for funnel in self.sub_funnels.values():
            funnel.promote()
            funnel.forget()
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
    def list_practical(self):
        return [s for s in self.skills.values() if s.skill_type == SkillType.PRACTICAL]
    def list_llm(self):
        return [s for s in self.skills.values() if s.skill_type == SkillType.LLM]


# ==================== 第三部分：小脑（运动适配中枢） ====================

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


# ==================== 第六部分：EM-Core 主类 ====================

class EM_Core:
    def __init__(self):
        self.memory = MLNFMem(max_sub_funnels=20)
        self.skill_registry = SkillRegistry()
        # 注册默认技能包
        self.skill_registry.register(PracticalSkill())
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
        return self.cerebellum.execute(f"内生处理: {task}")

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


# ==================== 主程序入口 ====================

if __name__ == "__main__":
    print("=== EM-Core-V2.0 完整一体化系统启动 ===")
    core = EM_Core()

    # 1. 初始化用户偏好记忆
    funnel = core.memory.get_or_create("user")
    mem = MemoryItem(
        id=str(uuid.uuid4()),
        content="用户不吃辣椒",
        level=MemoryLevel.L1_TEMPORARY,
        meaning_label=0.9
    )
    mem.update_importance()
    funnel.add_memory(mem)
    funnel.access(mem.id)
    core.memory.maintenance()
    print("已载入用户记忆：用户不吃辣椒\n")

    # 任务演示
    core.process_task("给用户做饭")
    core.process_task("飞到月球")
    core.process_task("如何修理椅子")
