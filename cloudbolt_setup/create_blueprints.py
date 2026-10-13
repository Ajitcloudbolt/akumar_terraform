"""
Creates two Terraform Operation blueprints on a CloudBolt server to reproduce the bug where a
failed `terraform apply` still shows the order as "Completed successfully".

  * "TF Repro - Apply Fails (Backend)"     -> BUG: order shows "Completed successfully"
  * "TF Repro - Apply Fails (No Backend)"  -> CONTROL: order correctly shows "Failed"

Run on the CloudBolt server (as the user that runs CloudBolt):
    cd /opt/cloudbolt
    python manage.py shell < /path/to/create_blueprints.py

Optional environment variables:
    TF_REPRO_ENV     Name of the Environment to enable (default: first env with a resource handler)
    TF_REPRO_CONN    Name of the Connection Info holding the GitHub token (required for "git",
                     because the repo is private). Create it under Admin > Connection Info with
                     IP/Hostname "github.com", protocol "https", and the token as the password.
    TF_REPRO_SOURCE  "git" (default) to clone from GitHub, or a local path to a checkout of this
                     repo, for servers without internet access to github.com

Safe to re-run: deletes and recreates the two blueprints each time.
"""
import os
import uuid

from django.conf import settings

from accounts.models import Group
from infrastructure.models import Environment
from resources.models import ResourceType
from utilities.models import ConnectionInfo
from servicecatalog.models import ServiceBlueprint, TerraformOperationBlueprintItem
from working_directory.models import WorkingDirectory

REPO_URL = "https://github.com/Ajitcloudbolt/akumar_terraform.git"
BLUEPRINTS = [
    ("TF Repro - Apply Fails (Backend)", "apply_fails_with_backend"),
    ("TF Repro - Apply Fails (No Backend)", "apply_fails_no_backend"),
]

if not os.path.exists(settings.TERRAFORM_BINARY):
    raise SystemExit(
        f"Terraform binary not found at {settings.TERRAFORM_BINARY}. "
        "Install Terraform >= 1.4 there first (see README)."
    )

source = os.environ.get("TF_REPRO_SOURCE", "git")
connection_info = None
if source == "git":
    conn_name = os.environ.get("TF_REPRO_CONN")
    if not conn_name:
        raise SystemExit(
            "The repo is private: set TF_REPRO_CONN to the name of a Connection Info for "
            "github.com whose password is a GitHub token with read access to the repo."
        )
    connection_info = ConnectionInfo.objects.get(name=conn_name)

env_name = os.environ.get("TF_REPRO_ENV")
if env_name:
    environment = Environment.objects.get(name=env_name)
else:
    # TF Operation items can only be ordered into enabled environments, and those must have a
    # resource handler. The env is just a label here; the repro configs never talk to a cloud.
    environment = Environment.objects.exclude(resource_handler=None).order_by("id").first()
    if not environment:
        raise SystemExit("No Environment with a resource handler found; set TF_REPRO_ENV.")

resource_type, __ = ResourceType.objects.get_or_create(
    name="service", defaults={"label": "Service"}
)
groups = list(Group.objects.exclude(name="Unassigned"))

for bp_name, subdir in BLUEPRINTS:
    for old in ServiceBlueprint.objects.filter(name=bp_name):
        wds = [
            si.working_dir
            for si in TerraformOperationBlueprintItem.objects.filter(blueprint=old)
        ]
        old.delete()
        for wd in wds:
            wd.delete()

    bp = ServiceBlueprint.objects.create(
        name=bp_name,
        description="Repro for: Terraform apply fails but order completes successfully",
        status="ACTIVE",
        resource_type=resource_type,
    )
    bp.groups.add(*groups)

    wd_kwargs = dict(
        name=f"source_dir_for_tfoperation{uuid.uuid4()}",
        label=f"Automatically Generated Source Directory for Terraform Operation {bp_name}",
    )
    if source == "git":
        wd_kwargs.update(
            source_type="GIT",
            source_path_or_url=REPO_URL,
            git_branch="main",
            connection_info=connection_info,
        )
    else:
        wd_kwargs.update(source_type="LOCAL", source_path_or_url=source)
    wd = WorkingDirectory.objects.create(**wd_kwargs)

    si = TerraformOperationBlueprintItem.objects.create(
        blueprint=bp,
        name="Terraform Apply That Fails",
        working_dir=wd,
        plan_directory=subdir,
        resource_type=resource_type,
        deploy_seq=1,
    )
    si.enabled_environments.add(environment)
    print(
        f"Blueprint id={bp.id} '{bp.name}' -> source={si.source_directory}, "
        f"groups={[g.name for g in groups]}, env={environment.name}"
    )
