"""
Direct code deployment to Amazon Bedrock AgentCore Runtime (no Docker needed).

1. pip-install Linux ARM64 wheels for the agent dependencies (cached)
2. zip dependencies + agent file (as main.py)
3. upload the zip to the workshop artifacts bucket (S3)
4. create (or update) the AgentCore Runtime with codeConfiguration
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import workshop_kit as kit

BUILD_DIR = kit.ROOT / "workshop" / ".build"
REQUIREMENTS = kit.ROOT / "workshop" / "common" / "runtime-requirements.txt"
PYTHON_VERSION = "3.13"
RUNTIME = "PYTHON_3_13"


def _install_dependencies() -> Path:
    requirements = REQUIREMENTS.read_text()
    digest = hashlib.sha256(requirements.encode()).hexdigest()[:12]
    deps_dir = BUILD_DIR / f"deps-{digest}"
    if (deps_dir / ".complete").exists():
        print(f"   📦 Dependencias en caché: {deps_dir.name}")
        return deps_dir
    shutil.rmtree(deps_dir, ignore_errors=True)
    print("   📦 Instalando dependencias Linux ARM64 (solo la primera vez, ~1-2 min)...")
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install", "--quiet",
            "--platform", "manylinux2014_aarch64",
            "--implementation", "cp",
            "--python-version", PYTHON_VERSION,
            "--only-binary=:all:",
            "--target", str(deps_dir),
            "-r", str(REQUIREMENTS),
        ],
        check=True,
    )
    (deps_dir / ".complete").write_text(digest)
    return deps_dir


def build_package(agent_file: Path) -> Path:
    deps_dir = _install_dependencies()
    package = BUILD_DIR / f"{agent_file.stem}.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in deps_dir.rglob("*"):
            if path.is_file() and path.name != ".complete" and "__pycache__" not in path.parts:
                info = zipfile.ZipInfo.from_file(path, path.relative_to(deps_dir).as_posix())
                info.external_attr = 0o644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, path.read_bytes())
        info = zipfile.ZipInfo("main.py")
        info.external_attr = 0o644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(info, agent_file.read_bytes())
    print(f"   🗜️ Paquete: {package.name} ({package.stat().st_size / 1e6:.1f} MB)")
    return package


def find_runtime(runtime_name: str) -> dict | None:
    control = kit.client("bedrock-agentcore-control")
    for page in control.get_paginator("list_agent_runtimes").paginate():
        for item in page.get("agentRuntimes", []):
            if item["agentRuntimeName"] == runtime_name:
                return item
    return None


def deploy(agent_file: Path, runtime_name: str, env_vars: dict, description: str) -> dict:
    """Create or update the runtime and wait until READY. Returns {arn, id, version}."""
    control = kit.client("bedrock-agentcore-control")
    bucket = kit.outputs()["AgentArtifactsBucketName"]
    package = build_package(agent_file)
    key = f"agents/{runtime_name}/{agent_file.stem}.zip"
    kit.client("s3").upload_file(str(package), bucket, key)
    print(f"   ☁️ Subido a s3://{bucket}/{key}")

    config = dict(
        agentRuntimeArtifact={
            "codeConfiguration": {
                "code": {"s3": {"bucket": bucket, "prefix": key}},
                "runtime": RUNTIME,
                "entryPoint": ["opentelemetry-instrument", "main.py"],
            }
        },
        roleArn=kit.outputs()["RuntimeRoleArn"],
        networkConfiguration={"networkMode": "PUBLIC"},
        protocolConfiguration={"serverProtocol": "HTTP"},
        environmentVariables={k: str(v) for k, v in env_vars.items()},
        description=description,
    )
    existing = find_runtime(runtime_name)
    if existing:
        runtime_id = existing["agentRuntimeId"]
        response = control.update_agent_runtime(agentRuntimeId=runtime_id, **config)
        print(f"   ♻️ Runtime actualizado: {runtime_id}")
    else:
        response = control.create_agent_runtime(agentRuntimeName=runtime_name, **config)
        runtime_id = response["agentRuntimeId"]
        print(f"   ✅ Runtime creado: {runtime_id}")
    kit.wait_for(
        lambda: control.get_agent_runtime(agentRuntimeId=runtime_id)["status"],
        ("READY",), ("CREATE_FAILED", "UPDATE_FAILED"), "Runtime", every=10,
    )
    runtime = control.get_agent_runtime(agentRuntimeId=runtime_id)
    return {"arn": runtime["agentRuntimeArn"], "id": runtime_id, "version": runtime["agentRuntimeVersion"]}


def invoke(runtime_arn: str, prompt: str, session_id: str) -> dict:
    data = kit.client("bedrock-agentcore")
    response = data.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn,
        runtimeSessionId=session_id,
        qualifier="DEFAULT",
        contentType="application/json",
        accept="application/json",
        payload=json.dumps({"prompt": prompt}).encode(),
    )
    return json.loads(response["response"].read())
