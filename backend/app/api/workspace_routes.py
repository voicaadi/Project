from fastapi import APIRouter, Depends, HTTPException
from uuid import uuid4
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models import Workspace, User, UserDevice
from app.api.auth_routes import get_current_user
from app.services.device_connection import device_connections

router = APIRouter(prefix="/api/workspaces", tags=["Workspaces"])

class TerminalRequest(BaseModel):
    command: str = Field(min_length=1, max_length=1000)
class WorkspaceDeviceAssign(BaseModel):
    device_id: int = Field(gt=0)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)


async def request_agent_workspace(
    workspace: Workspace,
    current_user: User,
    db: Session,
    operation: str,
    command: str | None = None,
):
    if not workspace.device_id:
        raise HTTPException(
            status_code=409,
            detail="Workspace has no assigned device",
        )

    device = db.query(UserDevice).filter(
        UserDevice.id == workspace.device_id,
        UserDevice.user_id == current_user.id,
        UserDevice.is_active.is_(True),
    ).first()

    if not device:
        raise HTTPException(
            status_code=409,
            detail="Assigned device is unavailable or inactive",
        )

    if not await device_connections.is_connected(device.id):
        raise HTTPException(
            status_code=409,
            detail="Assigned device is not connected",
        )

    message = {
        "type": "workspace.request",
        "request_id": str(uuid4()),
        "operation": operation,
        "user_id": current_user.id,
        "workspace_id": workspace.id,
    }

    if command is not None:
        message["command"] = command

    try:
        return await device_connections.request_workspace(
            device.id,
            message,
            timeout=30.0,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Local agent request timed out",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.post("/")
def create_workspace(
    data: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = Workspace(
        name=data.name,
        user_id=current_user.id,
        status="stopped",
    )

    db.add(workspace)
    db.commit()
    db.refresh(workspace)

    return {
        "message": "Workspace created successfully",
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "status": workspace.status,
        },
    }


@router.get("/")
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspaces = (
        db.query(Workspace)
        .filter(Workspace.user_id == current_user.id)
        .all()
    )

    return [
        {
            "id": workspace.id,
            "name": workspace.name,
            "status": workspace.status,
        }
        for workspace in workspaces
    ]


@router.delete("/{workspace_id}")
def delete_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = (
        db.query(Workspace)
        .filter(
            Workspace.id == workspace_id,
            Workspace.user_id == current_user.id,
        )
        .first()
    )

    if not workspace:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )

    db.delete(workspace)
    db.commit()

    return {"message": "Workspace deleted successfully"}

def get_owned_workspace(
    workspace_id: int,
    current_user: User,
    db: Session,
):
    workspace = (
        db.query(Workspace)
        .filter(
            Workspace.id == workspace_id,
            Workspace.user_id == current_user.id,
        )
        .first()
    )

    if not workspace:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )

    return workspace


@router.post("/{workspace_id}/start")
async def start_user_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = get_owned_workspace(workspace_id, current_user, db)
    result = await request_agent_workspace(
        workspace, current_user, db, "start"
    )

    workspace.status = result.get("status", "running")
    db.commit()

    return {
        "message": "Ubuntu workspace started",
        "workspace_id": workspace.id,
        **result,
    }

@router.post("/{workspace_id}/stop")
async def stop_user_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = get_owned_workspace(workspace_id, current_user, db)
    result = await request_agent_workspace(
        workspace, current_user, db, "stop"
    )

    workspace.status = "stopped"
    db.commit()

    return {
        "message": "Ubuntu workspace stopped",
        "workspace_id": workspace.id,
        **result,
    }

@router.get("/{workspace_id}/status")
async def user_workspace_status(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = get_owned_workspace(workspace_id, current_user, db)
    result = await request_agent_workspace(
        workspace, current_user, db, "status"
    )

    if result.get("status") in ("running", "stopped"):
        workspace.status = result["status"]
        db.commit()

    return {
        "workspace_id": workspace.id,
        "name": workspace.name,
        **result,
    }

@router.post("/{workspace_id}/terminal")
async def execute_terminal_command(
    workspace_id: int,
    data: TerminalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = get_owned_workspace(workspace_id, current_user, db)
    result = await request_agent_workspace(
        workspace,
        current_user,
        db,
        "execute",
        data.command,
    )

    return {
        "workspace_id": workspace.id,
        "command": data.command,
        **result,
    }

@router.patch("/{workspace_id}/device")
async def assign_workspace_device(
    workspace_id: int,
    data: WorkspaceDeviceAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = get_owned_workspace(workspace_id, current_user, db)

    device = db.query(UserDevice).filter(
        UserDevice.id == data.device_id,
        UserDevice.user_id == current_user.id,
        UserDevice.is_active.is_(True),
    ).first()

    if not device:
        raise HTTPException(status_code=404, detail="Active device not found")

    if not await device_connections.is_connected(device.id):
        raise HTTPException(status_code=409, detail="Device is not connected")

    workspace.device_id = device.id
    db.commit()

    return {
        "workspace_id": workspace.id,
        "device_id": device.id,
        "device_name": device.device_name,
        "message": "Workspace assigned to device",
    }
