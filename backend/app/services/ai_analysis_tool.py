"""Deterministic analytics of an authorized report; never execute model code."""

import base64
from decimal import Decimal
from io import BytesIO
from threading import Lock

from fastapi import HTTPException

_plot_lock = Lock()
METRICS = {
    "ATTENDANCE": ("present_days", "incomplete_days", "absent_days", "worked_minutes"),
    "LEAVE": ("approved_days", "pending_requests", "rejected_requests", "remaining_annual_days"),
    "HEADCOUNT": ("employee_count",),
    "MY_PAYSLIP": ("gross_salary", "net_salary", "personal_income_tax"),
    "PAYROLL_SUMMARY": ("employee_count", "gross_salary", "net_salary", "personal_income_tax"),
}
STATUS_LABELS = {
    "ACTIVE": "Đang làm việc", "INACTIVE": "Ngừng hoạt động", "TERMINATED": "Đã nghỉ việc",
    "APPROVED": "Đã duyệt", "PENDING": "Chờ duyệt", "REJECTED": "Từ chối",
}


def _chart_data(report, metrics, frequencies):
    """Choose comparable business measures, preserving totals and currency units."""
    kind, rows = report["kind"], report["rows"]
    if kind in {"HEADCOUNT", "PAYROLL_SUMMARY"} and "employee_count" in metrics:
        money = kind == "PAYROLL_SUMMARY" and any(field in metrics for field in ("gross_salary", "net_salary"))
        fields = [field for field in ("gross_salary", "net_salary") if field in metrics] if money else ["employee_count"]
        groups = {}
        for row in rows:
            department = str(row.get("department_name") or (f"Phòng ban {row['department_id']}" if row.get("department_id") else "Chưa có phòng ban"))
            values = groups.setdefault(department, {})
            for field in fields:
                series = STATUS_LABELS.get(row.get("employment_status"), row.get("employment_status") or "Chưa rõ trạng thái") if kind == "HEADCOUNT" else {"gross_salary": "Lương GROSS", "net_salary": "Lương thực nhận", "employee_count": "Số nhân viên"}[field]
                value = Decimal(str(row.get(field) or 0))
                if value.is_finite():
                    values[series] = values.get(series, Decimal(0)) + value
        # Bound labels without silently dropping departments or their totals.
        ordered = sorted(groups, key=lambda key: sum(groups[key].values()), reverse=True)
        if len(ordered) > 20:
            remainder = {}
            for key in ordered[19:]:
                for series, amount in groups[key].items():
                    remainder[series] = remainder.get(series, Decimal(0)) + amount
            other = f"Các phòng ban còn lại ({len(ordered) - 19})"
            while other in groups:
                other += " ·"
            groups[other] = remainder
            ordered = ordered[:19] + [other]
        series_names = list(dict.fromkeys(name for key in ordered for name in groups[key]))
        currency = next(iter(frequencies.get("currency_code", {})), "")
        return {"title": "Cơ cấu nhân sự theo phòng ban" if kind == "HEADCOUNT" else ("Tổng lương theo phòng ban" if money else "Số nhân viên theo phòng ban"),
                "unit": currency if money else "Nhân viên", "stacked": kind == "HEADCOUNT", "horizontal": True,
                "labels": ordered, "series": [{"name": name, "values": [str(groups[key].get(name, 0)) for key in ordered]} for name in series_names]}
    choices = {
        "ATTENDANCE": ("Tổng ngày công trong kỳ", "Ngày công", (("present_days", "Có mặt"), ("incomplete_days", "Thiếu lượt công"), ("absent_days", "Vắng"))),
        "LEAVE": ("Ngày phép trong kỳ và số dư", "Ngày", (("approved_days", "Phép đã duyệt"), ("remaining_annual_days", "Phép năm còn lại"))),
        "MY_PAYSLIP": ("Các khoản lương trong kỳ", next(iter(frequencies.get("currency_code", {})), ""), (("gross_salary", "Lương GROSS"), ("net_salary", "Lương thực nhận"), ("personal_income_tax", "Thuế TNCN"))),
    }
    if kind in choices:
        title, unit, fields = choices[kind]
        selected = [(field, label) for field, label in fields if field in metrics]
        if selected:
            return {"title": title, "unit": unit, "stacked": False, "horizontal": False,
                    "labels": [label for _, label in selected], "series": [{"name": "Tổng", "values": [metrics[field]["sum"] for field, _ in selected]}]}
    if frequencies:
        field = next(iter(frequencies))
        labels = {"status": "Trạng thái", "event_type": "Loại lượt công", "request_type": "Loại yêu cầu", "employment_status": "Trạng thái nhân sự", "currency_code": "Loại tiền tệ"}
        return {"title": "Số dòng theo " + labels[field].lower(), "unit": "Dòng", "stacked": False, "horizontal": True,
                "labels": [STATUS_LABELS.get(key, key) for key in frequencies[field]],
                "series": [{"name": "Số dòng", "values": list(frequencies[field].values())}]}
    return None


class AIAnalysisTool:
    @staticmethod
    async def execute(db, user, run_id):
        import json
        from starlette.concurrency import run_in_threadpool
        from app.services.report_access import authorized_run
        from app.services.report_storage import resolve_report_path
        from app.services.ai_request_security import secured_operation

        async with secured_operation(db, user.user_account_id, "REPORT", "REPORT_ANALYSIS") as audit:
            run = await authorized_run(db, user, run_id)
            audit["scope"] = run.scope
            audit["command"] = run.kind
            try:
                report = json.loads(resolve_report_path(run.snapshot_storage_key or "").read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise HTTPException(404, "REPORT_UNAVAILABLE") from exc
            return await run_in_threadpool(analyze_report, report)


def analyze_report(report: dict) -> dict:
    try:
        import pandas as pd
        import numpy as np
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
    except ImportError as exc:
        raise HTTPException(503, "ANALYSIS_DEPENDENCIES_UNAVAILABLE") from exc
    rows = report["rows"]
    if len(rows) > 10000:
        raise HTTPException(422, "ANALYSIS_ROW_LIMIT")
    frame = pd.DataFrame(rows)
    metrics = {}
    for field in METRICS.get(report["kind"], ()):
        if field not in frame:
            continue
        values = [Decimal(str(value)) for value in frame[field].dropna()]
        values = [value for value in values if value.is_finite()]
        if not values:
            continue
        # Money calculations remain Decimal; floats are used only for plotting.
        ordered = sorted(values)
        count = len(values)
        median = (ordered[(count - 1) // 2] + ordered[count // 2]) / 2
        metrics[field] = {"count": count, "missing": len(rows) - count,
                          "sum": str(sum(values, Decimal(0))),
                          "mean": str(sum(values, Decimal(0)) / count),
                          "median": str(median), "min": str(ordered[0]), "max": str(ordered[-1])}
    frequencies = {}
    for field in ("status", "event_type", "request_type", "employment_status", "currency_code"):
        if field in frame:
            frequencies[field] = {str(key): int(value) for key, value in frame[field].value_counts().head(20).items()}
    # Never combine monetary amounts in different currencies.
    if len(frequencies.get("currency_code", {})) > 1:
        metrics = {key: value for key, value in metrics.items() if key == "employee_count"}
    if report["kind"] == "HEADCOUNT" and "employment_status" in frame and "employee_count" in frame:
        frequencies["employment_status"] = {}
        for row in rows:
            status = str(row.get("employment_status") or "UNKNOWN")
            frequencies["employment_status"][status] = frequencies["employment_status"].get(status, 0) + int(row.get("employee_count") or 0)
    chart = None
    chart_data = _chart_data(report, metrics, frequencies)
    if chart_data:
        amounts = [np.asarray(series["values"], dtype=float) for series in chart_data["series"]]
        if not all(np.isfinite(values).all() for values in amounts):
            raise HTTPException(422, "ANALYSIS_VALUE_OUT_OF_RANGE")
        with _plot_lock:
            labels = chart_data["labels"]
            figure = Figure(figsize=(10, max(4, len(labels) * 0.45 + 1.8) if chart_data["horizontal"] else 4.5), layout="constrained")
            canvas = FigureCanvasAgg(figure)
            axis = figure.subplots()
            positions = np.arange(len(labels))
            baseline = np.zeros(len(labels))
            width = 0.7 / len(amounts)
            colors = ("#1677ff", "#52c41a", "#faad14", "#8c8c8c", "#722ed1")
            for index, (series, values) in enumerate(zip(chart_data["series"], amounts)):
                color = colors[index % len(colors)]
                if chart_data["horizontal"]:
                    offset = positions if chart_data["stacked"] else positions + (index - (len(amounts) - 1) / 2) * width
                    bars = axis.barh(offset, values, height=0.7 if chart_data["stacked"] else width,
                                     left=baseline if chart_data["stacked"] else 0, label=series["name"], color=color)
                    if chart_data["stacked"]:
                        baseline += values
                else:
                    bars = axis.bar(positions, values, width=0.6, color=color)
                axis.bar_label(bars, labels=[("" if value == 0 else f"{value:,.0f}") if chart_data["unit"] == "Nhân viên" else f"{value:,.2f}".rstrip("0").rstrip(".") for value in values],
                               label_type="center" if chart_data["stacked"] else "edge",
                               padding=0 if chart_data["stacked"] else 3)
            axis.set_title(chart_data["title"], pad=14, fontweight="bold")
            axis.set_axisbelow(True)
            if chart_data["horizontal"]:
                axis.set_yticks(positions, labels)
                axis.invert_yaxis()
                axis.set_xlabel(chart_data["unit"])
                axis.grid(axis="x", alpha=0.2)
                axis.margins(x=0.15)
                if len(amounts) > 1 or chart_data["stacked"]:
                    axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=min(3, len(amounts)), frameon=False)
            else:
                axis.set_xticks(positions, labels)
                axis.set_ylabel(chart_data["unit"])
                axis.grid(axis="y", alpha=0.2)
                axis.margins(y=0.15)
            if chart_data["unit"] in {"Nhân viên", "Dòng"}:
                from matplotlib.ticker import MaxNLocator
                (axis.xaxis if chart_data["horizontal"] else axis.yaxis).set_major_locator(MaxNLocator(integer=True))
            axis.spines[["top", "right"]].set_visible(False)
            buffer = BytesIO()
            canvas.print_png(buffer)
            chart = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
            figure.clear()
    return {"row_count": len(rows), "metrics": metrics, "frequencies": frequencies,
            "chart": chart, "chart_data": chart_data,
            "note": "Descriptive statistics of the complete report snapshot; no predictions."}
