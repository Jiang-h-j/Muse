"""任务域 API schema（Story 2.1，AR4 camelCase 边界）。

长时生成提交返回 taskId，前端据此连 SSE（GET /api/tasks/{taskId}/events）。
本 story 只暴露示范任务提交（TaskSubmitResponse）；真实生成端点在 Epic 2/4。
"""

from muse.schemas.base import CamelModel


class TaskSubmitResponse(CamelModel):
    """任务提交响应：边界自动 camelCase（task_id → taskId）。

    taskId 既是 ARQ job_id、也是 Redis Pub/Sub 频道键（stable id），前端用它连 SSE。
    """

    task_id: str
