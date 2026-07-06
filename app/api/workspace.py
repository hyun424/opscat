from fastapi import Header


def get_workspace_id(x_opscat_workspace: str | None = Header(default=None)) -> str:
    workspace = (x_opscat_workspace or "demo").strip()
    return workspace or "demo"
