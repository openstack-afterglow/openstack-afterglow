from enum import Enum

from pydantic import BaseModel


class ProgressStep(str, Enum):
    MANILA_PREPARING = "manila_preparing"
    BOOT_VOLUME_CREATING = "boot_volume_creating"
    USERDATA_GENERATING = "userdata_generating"
    SERVER_CREATING = "server_creating"
    ATTACHING_VOLUME = "attaching_volume"
    FLOATING_IP_CREATING = "floating_ip_creating"
    COMPLETED = "completed"
    FAILED = "failed"


class ProgressMessage(BaseModel):
    step: ProgressStep
    progress: int  # 0-100
    message: str
    instance_id: str | None = None
    error: str | None = None
    elapsed_seconds: float | None = None  # 단계 시작부터 경과 시간
