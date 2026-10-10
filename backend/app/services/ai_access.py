"""Access decisions derived exclusively from authenticated server-side roles."""
from fastapi import HTTPException, status

ROLE_LEVEL = {"EMPLOYEE": 0, "MANAGER": 1, "HR": 2, "ADMIN": 3}
KNOWN_ROLES = frozenset(ROLE_LEVEL)


def user_roles(user) -> set[str]:
    return {
        assignment.role.role_code
        for assignment in getattr(user, "role_assignments", ())
        if getattr(getattr(assignment, "role", None), "role_code", None)
    }


def require_known_role(roles: set[str]) -> None:
    """Reject unknown or missing roles instead of silently granting self access."""
    if not roles or not roles.issubset(KNOWN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI_ACCESS_DENIED")


def require_reviewer_role(roles: set[str]) -> None:
    require_known_role(roles)
    if not roles & {"MANAGER", "HR", "ADMIN"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI_ACCESS_DENIED")


def allowed_knowledge_roles(roles: set[str]) -> list[str]:
    require_known_role(roles)
    level = max((ROLE_LEVEL.get(role, -1) for role in roles), default=-1)
    return [role for role, required in ROLE_LEVEL.items() if required <= level]


def report_scope(user, requested_scope: str | None = None) -> str:
    """Resolve and authorize a report scope using roles from the authenticated user."""
    roles = user_roles(user)
    require_reviewer_role(roles)

    if roles & {"ADMIN", "HR"}:
        allowed = {"SELF", "DIRECT_REPORTS", "COMPANY"}
        default = "COMPANY"
    elif "MANAGER" in roles:
        allowed = {"SELF", "DIRECT_REPORTS"}
        default = "DIRECT_REPORTS"
    else:
        allowed = {"SELF"}
        default = "SELF"

    selected = requested_scope or default
    if selected not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI_ACCESS_DENIED")
    if selected in {"SELF", "DIRECT_REPORTS"} and getattr(user, "employee_id", None) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI_ACCESS_DENIED")
    return selected
