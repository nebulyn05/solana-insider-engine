from pathlib import Path

from grpc_tools import protoc

ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "proto"
OUT_DIR = ROOT / "app" / "ingestion" / "helius" / "proto"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "__init__.py").touch()
    result = protoc.main([
        "grpc_tools.protoc",
        f"-I{PROTO_DIR}",
        f"--python_out={OUT_DIR}",
        f"--grpc_python_out={OUT_DIR}",
        str(PROTO_DIR / "geyser.proto"),
        str(PROTO_DIR / "solana-storage.proto"),
    ])
    if result != 0:
        raise SystemExit(result)

    geyser_grpc = OUT_DIR / "geyser_pb2_grpc.py"
    text = geyser_grpc.read_text(encoding="utf-8")
    geyser_grpc.write_text(
        text.replace(
            "import geyser_pb2 as geyser__pb2",
            "from . import geyser_pb2 as geyser__pb2",
        ),
        encoding="utf-8",
    )

    geyser_pb2 = OUT_DIR / "geyser_pb2.py"
    text = geyser_pb2.read_text(encoding="utf-8")
    geyser_pb2.write_text(
        text.replace(
            "import solana_storage_pb2 as solana__storage__pb2",
            "from . import solana_storage_pb2 as solana__storage__pb2",
        ),
        encoding="utf-8",
    )
    print("Generated Yellowstone-compatible Python gRPC stubs.")


if __name__ == "__main__":
    main()
