from datetime import date
from typing import List, Optional
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_roles
from app.models.auth import UserAccount, Role, UserRoleAssignment
from app.core.security import get_password_hash
from app.models.organization import Employee, Department, Position
from app.schemas.organization import EmployeeCreate, EmployeeUpdate, EmployeeResponse, EmployeePasswordReset

router = APIRouter()
DEMO_EMAILS = {"admin@hrgroup3.com", "manager@hrgroup3.com", "employee@hrgroup3.com"}


@router.get("", response_model=List[EmployeeResponse])
async def list_employees(
    department_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN", "MANAGER"]))
):
    """List employees within the current user's scope, with optional filters."""
    stmt = select(Employee).options(
        selectinload(Employee.department),
        selectinload(Employee.position),
        selectinload(Employee.user_account)
    )
    user_roles = {assignment.role.role_code for assignment in current_user.role_assignments}
    if not user_roles.intersection({"ADMIN", "HR"}):
        if current_user.employee_id is None:
            return []
        stmt = stmt.where(Employee.manager_employee_id == current_user.employee_id)
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    if status_filter:
        stmt = stmt.where(Employee.employment_status == status_filter)
    
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    emp_in: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN"]))
):
    """Create a new employee profile"""
    # 1. Check duplicate code or email
    stmt_check = select(Employee).where(
        (Employee.employee_code == emp_in.employee_code) | (Employee.email == emp_in.email)
    )
    existing = (await db.execute(stmt_check)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã nhân viên hoặc email đã tồn tại trong hệ thống"
        )

    # 2. Validate department exists
    dept = (await db.execute(
        select(Department).where(Department.department_id == emp_in.department_id)
    )).scalar_one_or_none()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Phòng ban với ID {emp_in.department_id} không tồn tại"
        )

    # 3. Validate position exists
    pos = (await db.execute(
        select(Position).where(Position.position_id == emp_in.position_id)
    )).scalar_one_or_none()
    if not pos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chức danh với ID {emp_in.position_id} không tồn tại"
        )

    # 4. Validate manager if provided
    if emp_in.manager_employee_id:
        mgr = (await db.execute(
            select(Employee).where(Employee.employee_id == emp_in.manager_employee_id)
        )).scalar_one_or_none()
        if not mgr:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Người quản lý với ID {emp_in.manager_employee_id} không tồn tại"
            )

    employee_role = None
    if emp_in.login_password is not None:
        account = (await db.execute(
            select(UserAccount).where(UserAccount.login_email == str(emp_in.email))
        )).scalar_one_or_none()
        if account:
            raise HTTPException(status_code=409, detail="Email đăng nhập đã tồn tại")
        employee_role = (await db.execute(
            select(Role).where(Role.role_code == "EMPLOYEE")
        )).scalar_one_or_none()
        if not employee_role:
            raise HTTPException(status_code=400, detail="Chưa có quyền EMPLOYEE. Vui lòng khởi tạo dữ liệu mẫu.")

    emp = Employee(**emp_in.model_dump(exclude={"login_password"}))
    try:
        db.add(emp)
        await db.flush()
        if emp_in.login_password is not None:
            account = UserAccount(
                employee_id=emp.employee_id,
                login_email=str(emp_in.email),
                password_hash=get_password_hash(emp_in.login_password),
                is_active=emp.employment_status == "ACTIVE",
            )
            db.add(account)
            await db.flush()
            db.add(UserRoleAssignment(
                user_account_id=account.user_account_id,
                role_id=employee_role.role_id,
            ))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Mã nhân viên hoặc email đã tồn tại")

    # Reload with relationships
    stmt_load = select(Employee).where(Employee.employee_id == emp.employee_id).options(
        selectinload(Employee.department),
        selectinload(Employee.position),
        selectinload(Employee.user_account)
    )
    loaded_emp = (await db.execute(stmt_load)).scalar_one()
    return loaded_emp


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN", "MANAGER"]))
):
    """Get single employee profile by ID"""
    stmt = select(Employee).where(Employee.employee_id == employee_id).options(
        selectinload(Employee.department),
        selectinload(Employee.position),
        selectinload(Employee.user_account)
    )
    emp = (await db.execute(stmt)).scalar_one_or_none()
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy nhân viên"
        )
    user_roles = {assignment.role.role_code for assignment in current_user.role_assignments}
    if not user_roles.intersection({"ADMIN", "HR"}):
        if current_user.employee_id is None or (
            emp.employee_id != current_user.employee_id
            and emp.manager_employee_id != current_user.employee_id
        ):
            raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên")
    return emp


@router.patch("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    emp_update: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN"]))
):
    """Update employee details"""
    stmt = select(Employee).where(Employee.employee_id == employee_id)
    emp = (await db.execute(stmt)).scalar_one_or_none()
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy nhân viên"
        )

    update_data = emp_update.model_dump(exclude_unset=True, exclude={"new_password"})
    account = (await db.execute(
        select(UserAccount).where(UserAccount.employee_id == employee_id)
    )).scalar_one_or_none()
    user_roles = {assignment.role.role_code for assignment in current_user.role_assignments}
    if emp_update.new_password is not None and "ADMIN" not in user_roles:
        raise HTTPException(status_code=403, detail="Chỉ ADMIN được đặt lại mật khẩu")
    is_demo = emp.email.lower() in DEMO_EMAILS or (account and account.login_email.lower() in DEMO_EMAILS)
    if is_demo and (
        emp_update.new_password is not None
        or ("email" in update_data and str(update_data["email"]) != emp.email)
        or ("employment_status" in update_data and update_data["employment_status"] != emp.employment_status)
    ):
        raise HTTPException(status_code=400, detail="Không được đổi email, mật khẩu hoặc trạng thái của tài khoản demo")
    employee_role = None
    if emp_update.new_password is not None and not account:
        login_email = str(update_data.get("email", emp.email))
        existing_login = (await db.execute(
            select(UserAccount).where(UserAccount.login_email == login_email)
        )).scalar_one_or_none()
        if existing_login:
            raise HTTPException(status_code=409, detail="Email đăng nhập đã tồn tại")
        employee_role = (await db.execute(
            select(Role).where(Role.role_code == "EMPLOYEE")
        )).scalar_one_or_none()
        if not employee_role:
            raise HTTPException(status_code=400, detail="Chưa có quyền EMPLOYEE. Vui lòng khởi tạo dữ liệu mẫu.")
    if "email" in update_data:
        email = str(update_data["email"])
        if not is_demo and email.lower() in DEMO_EMAILS:
            raise HTTPException(status_code=400, detail="Email này dành cho tài khoản demo")
        duplicate_employee = (await db.execute(
            select(Employee).where(Employee.email == email, Employee.employee_id != employee_id)
        )).scalar_one_or_none()
        duplicate_account = (await db.execute(
            select(UserAccount).where(UserAccount.login_email == email, UserAccount.employee_id != employee_id)
        )).scalar_one_or_none()
        if duplicate_employee or duplicate_account:
            raise HTTPException(status_code=409, detail="Email đã tồn tại trong hệ thống")

    # Validate foreign keys if updated
    if "department_id" in update_data and update_data["department_id"] is not None:
        dept = (await db.execute(
            select(Department).where(Department.department_id == update_data["department_id"])
        )).scalar_one_or_none()
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phòng ban không tồn tại"
            )

    if "position_id" in update_data and update_data["position_id"] is not None:
        pos = (await db.execute(
            select(Position).where(Position.position_id == update_data["position_id"])
        )).scalar_one_or_none()
        if not pos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chức danh không tồn tại"
            )

    if "manager_employee_id" in update_data and update_data["manager_employee_id"] is not None:
        if update_data["manager_employee_id"] == employee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nhân viên không thể tự làm quản lý trực tiếp của chính mình"
            )
        mgr = (await db.execute(
            select(Employee).where(Employee.employee_id == update_data["manager_employee_id"])
        )).scalar_one_or_none()
        if not mgr:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Người quản lý không tồn tại"
            )

    if "employment_status" in update_data:
        if update_data["employment_status"] == "ACTIVE":
            update_data["termination_date"] = None
        elif not update_data.get("termination_date") and not emp.termination_date:
            update_data["termination_date"] = date.today()

    # Update profile and login account in the same transaction.
    try:
        for field, value in update_data.items():
            setattr(emp, field, value)
        if account:
            if "email" in update_data:
                account.login_email = str(update_data["email"])
            if "employment_status" in update_data:
                account.is_active = update_data["employment_status"] == "ACTIVE"
            if emp_update.new_password is not None:
                account.password_hash = get_password_hash(emp_update.new_password)
        elif emp_update.new_password is not None:
            account = UserAccount(
                employee_id=emp.employee_id,
                login_email=str(emp.email),
                password_hash=get_password_hash(emp_update.new_password),
                is_active=emp.employment_status == "ACTIVE",
            )
            db.add(account)
            await db.flush()
            db.add(UserRoleAssignment(
                user_account_id=account.user_account_id,
                role_id=employee_role.role_id,
            ))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email đã tồn tại trong hệ thống")

    # Reload with relationships
    stmt_load = select(Employee).where(Employee.employee_id == employee_id).options(
        selectinload(Employee.department),
        selectinload(Employee.position),
        selectinload(Employee.user_account)
    )
    loaded_emp = (await db.execute(stmt_load)).scalar_one()
    return loaded_emp


@router.post("/{employee_id}/deactivate", response_model=EmployeeResponse)
async def deactivate_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["HR", "ADMIN"]))
):
    """Deactivate both the employee profile and login account."""
    return await update_employee(
        employee_id,
        EmployeeUpdate(employment_status="INACTIVE", termination_date=date.today()),
        db,
        current_user,
    )


@router.post("/{employee_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_employee_password(
    employee_id: int,
    password_in: EmployeePasswordReset,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["ADMIN"]))
):
    """Allow an administrator to set a new password on an existing employee account."""
    account = (await db.execute(
        select(UserAccount).where(UserAccount.employee_id == employee_id)
    )).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Nhân viên chưa có tài khoản đăng nhập")

    if account.login_email.lower() in DEMO_EMAILS:
        raise HTTPException(status_code=400, detail="Không được đổi mật khẩu của tài khoản demo")

    account.password_hash = get_password_hash(password_in.new_password)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{employee_id}/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee_account(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_roles(["ADMIN"]))
):
    """Delete a login account and its role assignments, keeping the employee profile."""
    account = (await db.execute(
        select(UserAccount).where(UserAccount.employee_id == employee_id)
    )).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Nhân viên chưa có tài khoản đăng nhập")
    if account.login_email.lower() in DEMO_EMAILS:
        raise HTTPException(status_code=400, detail="Không được xóa tài khoản demo")
    if account.user_account_id == current_user.user_account_id:
        raise HTTPException(status_code=400, detail="Không thể xóa tài khoản đang đăng nhập")
    try:
        await db.execute(delete(UserRoleAssignment).where(
            UserRoleAssignment.user_account_id == account.user_account_id
        ))
        await db.delete(account)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Tài khoản đang được tham chiếu trong dữ liệu lịch sử nên không thể xóa. Bạn có thể chuyển nhân viên sang Tạm ngưng để khóa đăng nhập.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
