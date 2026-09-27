from __future__ import annotations

from pathlib import Path

_GENERATED = Path(__file__).resolve().parent
_ROOT = Path(__file__).resolve().parents[3]
_PROTO = _ROOT / "proto"


def _ensure_generated() -> None:
    if (_GENERATED / "geyser_pb2.py").exists() and (_GENERATED / "geyser_pb2_grpc.py").exists():
        return

    from grpc_tools import protoc

    _GENERATED.mkdir(parents=True, exist_ok=True)
    result = protoc.main([
        "grpc_tools.protoc",
        f"-I{_PROTO}",
        f"--python_out={_GENERATED}",
        f"--grpc_python_out={_GENERATED}",
        str(_PROTO / "geyser.proto"),
        str(_PROTO / "solana-storage.proto"),
    ])
    if result != 0:
        raise RuntimeError(f"Unable to generate Yellowstone protobuf stubs (protoc exit {result})")

    grpc_stub = _GENERATED / "geyser_pb2_grpc.py"
    grpc_stub.write_text(
        grpc_stub.read_text(encoding="utf-8").replace(
            "import geyser_pb2 as geyser__pb2",
            "from . import geyser_pb2 as geyser__pb2",
        ),
        encoding="utf-8",
    )

    pb_stub = _GENERATED / "geyser_pb2.py"
    pb_stub.write_text(
        pb_stub.read_text(encoding="utf-8").replace(
            "import solana_storage_pb2 as solana__storage__pb2",
            "from . import solana_storage_pb2 as solana__storage__pb2",
        ),
        encoding="utf-8",
    )


_ensure_generated()
