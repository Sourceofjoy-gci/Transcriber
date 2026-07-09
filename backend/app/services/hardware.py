import os
import subprocess


def detect_hardware() -> dict:
    ram_bytes = _ram_bytes()
    gpus = _nvidia_gpus()
    return {
        "cpu_cores": os.cpu_count() or 1,
        "ram_bytes": ram_bytes,
        "gpus": gpus,
        "total_memory_bytes": ram_bytes or 0,
        "has_cuda": bool(gpus),
        "has_metal": sys_platform_has_metal(),
        "detected_gpus": [
            {
                "name": gpu["name"],
                "memory_bytes": gpu["vram_mb"] * 1024 * 1024 if gpu.get("vram_mb") is not None else None,
                "driver_version": gpu.get("driver_version"),
            }
            for gpu in gpus
        ],
    }


def assess_model_compatibility(requirements: dict | None, hardware: dict | None = None) -> dict:
    hardware = hardware or detect_hardware()
    requirements = requirements or {}
    reasons: list[str] = []
    recommendations: list[str] = []
    labels = ["cpu"]

    if hardware.get("has_cuda"):
        labels.append("cuda")
    if hardware.get("has_metal"):
        labels.append("metal")

    min_ram = _as_int(requirements.get("min_ram_bytes"))
    total_memory = _as_int(hardware.get("total_memory_bytes") or hardware.get("ram_bytes"))
    if min_ram is not None and total_memory is not None and total_memory < min_ram:
        reasons.append(f"Requires at least {min_ram} bytes of RAM")

    if requirements.get("requires_cuda") and not hardware.get("has_cuda"):
        reasons.append("Requires CUDA GPU")

    recommended_device = str(requirements.get("recommended_device") or "cpu_or_cuda")
    if recommended_device == "cuda" and not hardware.get("has_cuda"):
        recommendations.append("CUDA is recommended; CPU execution may be slower")
    elif recommended_device == "metal" and not hardware.get("has_metal"):
        recommendations.append("Metal acceleration is recommended on supported macOS workers")

    if min_ram is not None:
        labels.append(f"ram>={min_ram}")

    return {
        "compatible": not reasons,
        "reasons": reasons,
        "recommendations": recommendations,
        "recommended_device": recommended_device,
        "worker_labels": labels,
    }


def _ram_bytes() -> int | None:
    try:
        if os.name == "nt":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return int(status.total_physical)
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError):
        return None


def _nvidia_gpus() -> list[dict]:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    return [
        {"name": fields[0], "vram_mb": int(fields[1]), "driver_version": fields[2]}
        for line in completed.stdout.splitlines()
        if len(fields := [value.strip() for value in line.split(",")]) == 3 and fields[1].isdigit()
    ]


def sys_platform_has_metal() -> bool:
    return os.name == "posix" and os.uname().sysname == "Darwin" if hasattr(os, "uname") else False


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
