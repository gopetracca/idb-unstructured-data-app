#!/usr/bin/env python3
"""Build a Container App update payload with health probes (AIA-479).

Reads the output of ``az containerapp show -o json`` on stdin and writes a
trimmed ContainerApp resource JSON (valid YAML) to stdout with:

- ``properties.template.containers[0].probes`` set to the standard
  liveness/readiness/startup probes pointing at ``/health/live`` and
  ``/health/ready`` on the ingress target port,
- optionally a new image (``--image``), ``DD_VERSION`` env value
  (``--dd-version``) and revision suffix (``--revision-suffix``),

so the deploy script can apply image + probes in a single
``az containerapp update --yaml`` call (one new revision).

Only stdlib is used — runs on any CI runner or workstation python3.
"""

import argparse
import json
import sys


def build_probes(target_port: int) -> list[dict]:
    def http_get(path: str) -> dict:
        return {"path": path, "port": target_port, "scheme": "HTTP"}

    return [
        {
            "type": "Liveness",
            "httpGet": http_get("/health/live"),
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "failureThreshold": 3,
        },
        {
            "type": "Readiness",
            "httpGet": http_get("/health/ready"),
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "failureThreshold": 3,
        },
        {
            # Generous threshold: cold starts load the ODBC driver and tiktoken
            # cache; the app gets periodSeconds * failureThreshold to come up.
            "type": "Startup",
            "httpGet": http_get("/health/ready"),
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "failureThreshold": 30,
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", help="Full image reference to deploy (registry/repo:tag)")
    parser.add_argument("--dd-version", help="Value for the DD_VERSION env var")
    parser.add_argument("--revision-suffix", help="Revision suffix for the new revision")
    args = parser.parse_args()

    app = json.load(sys.stdin)
    properties = app["properties"]
    template = properties["template"]
    containers = template.get("containers") or []
    if not containers:
        print("error: container app has no containers", file=sys.stderr)
        return 1

    ingress = (properties.get("configuration") or {}).get("ingress") or {}
    target_port = ingress.get("targetPort")
    if not target_port:
        print(
            "error: container app has no ingress targetPort — cannot set HTTP probes",
            file=sys.stderr,
        )
        return 1

    container = containers[0]
    container["probes"] = build_probes(int(target_port))

    if args.image:
        container["image"] = args.image
    if args.dd_version is not None:
        env = [e for e in (container.get("env") or []) if e.get("name") != "DD_VERSION"]
        env.append({"name": "DD_VERSION", "value": args.dd_version})
        container["env"] = env
    if args.revision_suffix:
        template["revisionSuffix"] = args.revision_suffix

    # Keep only what `az containerapp update --yaml` needs; system metadata and
    # read-only fields (identity, fqdn, provisioning state…) are dropped so the
    # update cannot trip over immutable properties.
    payload = {
        "location": app.get("location"),
        "name": app.get("name"),
        "resourceGroup": app.get("resourceGroup"),
        "type": app.get("type", "Microsoft.App/containerApps"),
        "properties": {
            "environmentId": properties.get("environmentId"),
            "configuration": properties.get("configuration"),
            "template": template,
        },
    }

    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
