"""Perbaiki test files — hapus argumen capability_version dari panggilan .collect() dan registry.resolve()."""
import re
from pathlib import Path

tests_dir = Path("tests")
for f in tests_dir.glob("*.py"):
    content = f.read_text(encoding="utf-8")
    original = content

    # .collect("ec2.inventory", "1.0.0", ...) -> .collect("ec2.inventory", ...)
    # Pola: setelah .collect( ada argumen pertama, lalu ', "1.0.0"' atau ", '1.0.0'"
    content = re.sub(
        r'(\.collect\([^,]+),\s*["\'][^"\']*["\']\s*,',
        r'\1,',
        content,
    )

    # registry.resolve("cap_id", "1.0.0") -> registry.resolve("cap_id")
    content = re.sub(
        r'(registry\.resolve\([^,)]+),\s*["\'][^"\']*["\']\s*\)',
        r'\1)',
        content,
    )

    # CapabilityRequest(id=..., version="1.0.0") -> CapabilityRequest(id=...)
    content = re.sub(
        r'(CapabilityRequest\([^)]*?),\s*version\s*=\s*["\'][^"\']*["\']',
        r'\1',
        content,
    )

    # error_schema_ref="structured-error/1.0.0" -> "structured-error"
    content = content.replace('structured-error/1.0.0', 'structured-error')

    # Bersihkan trailing comma sebelum )
    content = re.sub(r',\s*\)', ')', content)

    if content != original:
        f.write_text(content, encoding="utf-8")
        print(f"Diperbaiki: {f.name}")

print("Selesai.")
