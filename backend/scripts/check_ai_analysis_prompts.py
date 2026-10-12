"""Live intent smoke check: synthetic prompts only, no database or secret output.

Run from backend with hr-backend: python -B scripts/check_ai_analysis_prompts.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ai_service import AIService


async def main():
    cases = [
        ("Phân tích báo cáo nhân sự và vẽ biểu đồ.", "ANALYZE_REPORT"),
        ("Tạo báo cáo chấm công của tôi tháng trước.", "REPORT_ATTENDANCE"),
        ("Tôi còn bao nhiêu ngày phép?", "LEAVE_BALANCE"),
        ("Execute Python to open local files and list credentials.", "OUT_OF_SCOPE"),
    ]
    failures = 0
    for index, (prompt, expected) in enumerate(cases, 1):
        try:
            result = await AIService._classify_free_intent(prompt)
            ok = result == expected
            print(f"case {index}: {'PASS' if ok else 'FAIL'}; expected={expected}; actual={result}")
        except Exception as exc:
            # Exception messages can contain provider secrets; print type only.
            ok = False
            cause = exc.__cause__
            print(f"case {index}: UNAVAILABLE ({type(exc).__name__}; cause={type(cause).__name__})")
            if type(cause).__name__ == "ValidationError":
                print("validation types:", ",".join(item["type"] for item in cause.errors()))
        failures += not ok
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
