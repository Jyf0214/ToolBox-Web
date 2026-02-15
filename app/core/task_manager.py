import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Unknown Task"
    user_type: str = "guest"  # guest or admin
    status: str = "waiting"  # waiting, processing, completed, failed
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    filename: Optional[str] = None
    ip: str = "Unknown"

class TaskManager:
    def __init__(self, max_concurrent_tasks: int = 2):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.queue: List[Task] = []
        self.active_tasks: Dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition()

    async def add_task(self, name: str, user_type: str, ip: str, filename: Optional[str] = None) -> Task:
        task = Task(name=name, user_type=user_type, ip=ip, filename=filename)
        async with self._lock:
            self.queue.append(task)
            print(f"[Queue] Task added: {task.id} (Total waiting: {len(self.queue)})")
        return task

    async def start_task(self, task_id: str):
        async with self._condition:
            while True:
                async with self._lock:
                    # 检查是否轮到该任务
                    waiting_ids = [t.id for t in self.queue]
                    if task_id in waiting_ids:
                        index = waiting_ids.index(task_id)
                        can_run = len(self.active_tasks) < self.max_concurrent_tasks
                        
                        # 这里简单处理：只有排在前面的且有空位才运行
                        if index < (self.max_concurrent_tasks - len(self.active_tasks)):
                            # 弹出任务
                            task = self.queue.pop(index)
                            task.status = "processing"
                            task.started_at = datetime.utcnow()
                            self.active_tasks[task.id] = task
                            print(f"[Queue] Task started: {task.id} (Active: {len(self.active_tasks)})")
                            return task
                
                await self._condition.wait()

    async def complete_task(self, task_id: str):
        async with self._lock:
            if task_id in self.active_tasks:
                task = self.active_tasks.pop(task_id)
                task.status = "completed"
                task.completed_at = datetime.utcnow()
                print(f"[Queue] Task completed: {task.id}")
        
        async with self._condition:
            self._condition.notify_all()

    def get_status(self):
        return {
            "waiting_count": len(self.queue),
            "active_count": len(self.active_tasks),
            "max_concurrent": self.max_concurrent_tasks
        }

global_task_manager = TaskManager(max_concurrent_tasks=1) # 默认设为 1，方便观察排队
