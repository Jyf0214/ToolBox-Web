import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

# 数据库相关
from sqlalchemy import insert
from app.core import database
from app.models.models import TaskHistory


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
    error_message: Optional[str] = None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "user_type": self.user_type,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "filename": self.filename,
            "ip": self.ip,
            "error_message": self.error_message,
        }


class TaskManager:
    def __init__(self, max_concurrent_tasks: int = 2):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.queue: List[Task] = []
        self.active_tasks: Dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition()

    async def add_task(
        self, name: str, user_type: str, ip: str, filename: Optional[str] = None
    ) -> Task:
        task = Task(name=name, user_type=user_type, ip=ip, filename=filename)
        async with self._lock:
            self.queue.append(task)
            print(f"[Queue] 任务已添加: {task.id}")
        
        # 唤醒正在等待 start_task 的协程
        async with self._condition:
            self._condition.notify_all()
        return task

    async def start_task(self, task_id: str):
        """
        请求开始执行任务。
        管理员任务 (admin) 将跳过限制立即执行。
        普通任务 (guest) 需等待队列顺序和并发限制。
        """
        async with self._condition:
            while True:
                async with self._lock:
                    # 获取当前任务对象
                    task = next((t for t in self.queue if t.id == task_id), None)
                    
                    if task:
                        index = self.queue.index(task)
                        # 如果是管理员任务，立即执行
                        if task.user_type == "admin":
                            self.queue.pop(index)
                            task.status = "processing"
                            task.started_at = datetime.utcnow()
                            self.active_tasks[task.id] = task
                            print(f"[Queue] 管理员任务立即开始: {task.id}")
                            return task
                        
                        # 如果是普通任务，检查并发限制和队列顺序
                        if len(self.active_tasks) < self.max_concurrent_tasks:
                            # 仅当处于队列首位（或前方全是管理员任务已被处理）时执行
                            if index == 0:
                                self.queue.pop(index)
                                task.status = "processing"
                                task.started_at = datetime.utcnow()
                                self.active_tasks[task.id] = task
                                print(f"[Queue] 普通任务开始执行: {task.id}")
                                return task
                    elif task_id in self.active_tasks:
                        # 任务已经在执行中
                        return self.active_tasks[task_id]
                
                # 等待通知
                await self._condition.wait()

    async def complete_task(
        self,
        task_id: str,
        status: str = "completed",
        error_message: Optional[str] = None,
    ):
        async with self._lock:
            if task_id in self.active_tasks:
                task = self.active_tasks.pop(task_id)
                task.status = status
                task.completed_at = datetime.utcnow()
                task.error_message = error_message

                try:
                    async with database.AsyncSessionLocal() as session:
                        duration = 0
                        if task.completed_at and task.started_at:
                            duration = int(
                                (task.completed_at - task.started_at).total_seconds()
                            )

                        stmt = insert(TaskHistory).values(
                            task_id=task.id,
                            task_name=task.name,
                            user_type=task.user_type,
                            ip_address=task.ip,
                            filename=task.filename,
                            status=task.status,
                            created_at=task.created_at,
                            started_at=task.started_at,
                            completed_at=task.completed_at,
                            duration=duration,
                        )
                        await session.execute(stmt)
                        await session.commit()
                except Exception as e:
                    print(f"[Queue] Failed history save: {e}")

        async with self._condition:
            self._condition.notify_all()

    def get_status(self):
        return {
            "waiting_count": len(self.queue),
            "active_count": len(self.active_tasks),
            "max_concurrent": self.max_concurrent_tasks,
        }

    def get_system_stats(self):
        import psutil

        vm = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": vm.percent,
            "memory_total": round(vm.total / (1024**3), 2),
            "memory_available": round(vm.available / (1024**3), 2),
        }


global_task_manager = TaskManager(max_concurrent_tasks=1)
