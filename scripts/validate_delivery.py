from __future__ import annotations

from pathlib import Path

import hcl2
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> object:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _load_hcl(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return hcl2.load(handle)


def validate_workflows() -> list[str]:
    errors: list[str] = []
    workflow_dir = ROOT / ".github" / "workflows"
    required_workflows = {"ci.yml", "deploy.yml", "promote-prod.yml"}

    discovered = {path.name for path in workflow_dir.glob("*.yml")}
    missing = required_workflows - discovered
    for name in sorted(missing):
        errors.append(f"missing workflow: .github/workflows/{name}")

    for path in workflow_dir.glob("*.yml"):
        try:
            document = _load_yaml(path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"invalid workflow yaml {path.relative_to(ROOT)}: {exc}")
            continue
        if not isinstance(document, dict):
            errors.append(f"workflow is not a mapping: {path.relative_to(ROOT)}")
            continue
        for required_key in ("name", "on", "jobs"):
            if required_key not in document:
                errors.append(f"workflow missing '{required_key}': {path.relative_to(ROOT)}")
    return errors


def validate_helm() -> list[str]:
    errors: list[str] = []
    chart_root = ROOT / "infra" / "helm" / "sentinelstream"
    template_dir = chart_root / "templates"

    required_files = {
        "Chart.yaml",
        "values.yaml",
        "values-dev.yaml",
        "values-local.yaml",
        "values-prod.yaml",
    }
    required_templates = {
        "_helpers.tpl",
        "configmap.yaml",
        "deployment.yaml",
        "hpa.yaml",
        "ingress.yaml",
        "poddisruptionbudget.yaml",
        "secret.yaml",
        "service.yaml",
        "serviceaccount.yaml",
    }

    for name in sorted(required_files):
        if not (chart_root / name).exists():
            errors.append(f"missing Helm file: infra/helm/sentinelstream/{name}")
    for name in sorted(required_templates):
        if not (template_dir / name).exists():
            errors.append(f"missing Helm template: infra/helm/sentinelstream/templates/{name}")

    try:
        chart = _load_yaml(chart_root / "Chart.yaml")
        if not isinstance(chart, dict):
            errors.append("Chart.yaml must be a mapping")
        else:
            for required_key in ("apiVersion", "name", "version", "appVersion"):
                if required_key not in chart:
                    errors.append(f"Chart.yaml missing '{required_key}'")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"invalid Chart.yaml: {exc}")

    for values_name in ("values.yaml", "values-dev.yaml", "values-local.yaml", "values-prod.yaml"):
        path = chart_root / values_name
        try:
            values = _load_yaml(path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"invalid values yaml {path.relative_to(ROOT)}: {exc}")
            continue
        if not isinstance(values, dict):
            errors.append(f"values file is not a mapping: {path.relative_to(ROOT)}")
            continue
        if values_name == "values.yaml":
            for required_key in ("global", "config", "secrets", "services", "serviceDefaults"):
                if required_key not in values:
                    errors.append(f"{values_name} missing '{required_key}'")
            services = values.get("services", {})
            if not isinstance(services, dict) or not services:
                errors.append("values.yaml must declare service mappings")
            else:
                for service_name in (
                    "ingestion-service",
                    "feature-service",
                    "rule-engine",
                    "model-service",
                    "decision-service",
                    "feedback-service",
                    "analyst-console",
                ):
                    if service_name not in services:
                        errors.append(f"values.yaml missing service '{service_name}'")

    deployment_template = (template_dir / "deployment.yaml").read_text(encoding="utf-8")
    for required_snippet in (
        "checksum/config",
        "serviceAccountName:",
        "livenessProbe:",
        "readinessProbe:",
        "envFrom:",
    ):
        if required_snippet not in deployment_template:
            errors.append(f"deployment template missing '{required_snippet}'")
    return errors


def validate_terraform() -> list[str]:
    errors: list[str] = []
    terraform_root = ROOT / "infra" / "terraform"

    tf_files = list(terraform_root.rglob("*.tf"))
    if not tf_files:
        return ["no Terraform files found under infra/terraform"]

    for path in tf_files:
        try:
            document = _load_hcl(path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"invalid Terraform file {path.relative_to(ROOT)}: {exc}")
            continue
        if not isinstance(document, dict):
            errors.append(f"Terraform file did not parse to a mapping: {path.relative_to(ROOT)}")

    for environment in ("dev", "prod"):
        env_dir = terraform_root / "environments" / environment
        for name in (
            "main.tf",
            "variables.tf",
            "outputs.tf",
            "terraform.tfvars.example",
            "backend.hcl.example",
        ):
            if not (env_dir / name).exists():
                errors.append(f"missing Terraform env file: {env_dir.relative_to(ROOT) / name}")

    modules_dir = terraform_root / "modules"
    for module_name in ("network", "eks", "ecr", "artifact-store"):
        module_dir = modules_dir / module_name
        if not module_dir.exists():
            errors.append(f"missing Terraform module: {module_dir.relative_to(ROOT)}")
            continue
        if not (module_dir / "main.tf").exists():
            errors.append(f"module missing main.tf: {module_dir.relative_to(ROOT)}")
        if not (module_dir / "variables.tf").exists():
            errors.append(f"module missing variables.tf: {module_dir.relative_to(ROOT)}")
        if not (module_dir / "outputs.tf").exists():
            errors.append(f"module missing outputs.tf: {module_dir.relative_to(ROOT)}")
    return errors


def main() -> int:
    errors = [
        *validate_workflows(),
        *validate_helm(),
        *validate_terraform(),
    ]
    if errors:
        for error in errors:
            print(f"[delivery-validation] {error}")
        return 1
    print("delivery validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
