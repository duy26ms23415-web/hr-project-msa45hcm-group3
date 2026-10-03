from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    employees,
    departments,
    holidays,
    attendance,
    leaves,
    payroll,
    ai,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(employees.router, prefix="/employees", tags=["Employees"])
api_router.include_router(departments.router, tags=["Organization"])
api_router.include_router(holidays.router, prefix="/holidays", tags=["Holidays"])
api_router.include_router(attendance.router, prefix="/attendance", tags=["Attendance & QR"])
api_router.include_router(leaves.router, prefix="/leave", tags=["Leave Management"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["Payroll"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI Assistant"])
