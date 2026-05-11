from __future__ import annotations

import os
from typing import Dict


class DockerController:
    def __init__(self, container_name: str | None):
        self.container_name = (container_name or "").strip()

    def available(self) -> bool:
        if not self.container_name:
            return False
        return bool(os.path.exists("/var/run/docker.sock") or os.environ.get("DOCKER_HOST"))

    def restart(self) -> Dict[str, str | bool]:
        if not self.container_name:
            return {"ok": False, "message": "IMMICHFRAME_CONTAINER is not configured"}
        try:
            import docker  # type: ignore
        except Exception as exc:
            return {"ok": False, "message": f"Docker SDK is not available: {exc}"}
        try:
            client = docker.from_env()
            container = client.containers.get(self.container_name)
            container.restart(timeout=20)
            return {"ok": True, "message": f"Restarted container '{self.container_name}'"}
        except Exception as exc:
            return {"ok": False, "message": f"Could not restart '{self.container_name}': {exc}"}
