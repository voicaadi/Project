from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models import Workspace, User
from app.api.auth_routes import get_current_user
from app.services.workspace_service import (
    start_workspace,
    stop_workspace,
    get_workspace_status,
    execute_workspace_command,
)

router = APIRouter(prefix="/api/workspaces", tags=["Workspaces"])

class TerminalRequest(BaseModel):
    command: str = Field(min_length=1, max_length=1000)
class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)


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
def start_user_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = get_owned_workspace(workspace_id, current_user, db)

    result = start_workspace(current_user.id, workspace.id)

    workspace.status = "running"
    db.commit()

    return {
        "message": "Ubuntu workspace started",
        "workspace_id": workspace.id,
        **result,
    }


@router.post("/{workspace_id}/stop")
def stop_user_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = get_owned_workspace(workspace_id, current_user, db)

    result = stop_workspace(current_user.id, workspace.id)

    workspace.status = "stopped"
    db.commit()

    return {
        "message": "Ubuntu workspace stopped",
        "workspace_id": workspace.id,
        **result,
    }


@router.get("/{workspace_id}/status")
def user_workspace_status(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = get_owned_workspace(workspace_id, current_user, db)

    result = get_workspace_status(current_user.id, workspace.id)

    return {
        "workspace_id": workspace.id,
        "name": workspace.name,
        **result,
    }
@router.post("/{workspace_id}/terminal")
def execute_terminal_command(
    workspace_id: int,
    data: TerminalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = get_owned_workspace(
        workspace_id,
        current_user,
        db,
    )

    result = execute_workspace_command(
        current_user.id,
        workspace.id,
        data.command,
    )

    return {
        "workspace_id": workspace.id,
        "command": data.command,
        **result,
    }