"""
Creates two Terraform Operation blueprints on a CloudBolt server to reproduce the bug where a
failed `terraform apply` still shows the order as "Completed successfully".

  * "TF Repro - Apply Fails (Backend)"     -> BUG: order shows "Completed successfully"
  * "TF Repro - Apply Fails (No Backend)"  -> CONTROL: order correctly shows "Failed"

Run on the CloudBolt server (as the user that runs CloudBolt), from the CloudBolt src dir:
    TF_REPRO_REPO=akumar_terraform python manage.py shell < /path/to/create_blueprints.py

Source of the Terraform files (set exactly one; checked in this order):
    TF_REPRO_REPO    Label of a Source Code Repository (Admin > Source Code Repositories) whose
                     URL is this repo and whose credentials hold a token that can read it.
                     This is the same as choosing "Source Code Repository" in the blueprint UI.
    TF_REPRO_CONN    Name of a Connection Info for github.com whose password is a token that can
                     read this repo (the "Remote Source [Git]" option in the UI).
    TF_REPRO_SOURCE  Local path to a checkout of this repo, for servers that can't reach github.

Optional:
    TF_REPRO_ENV     Name of the Environment to enable (default: first env with a resource handler)
    TF_REPRO_BRANCH  Branch to use (default: main)

Safe to re-run: deletes and recreates the two blueprints each time.
"""
import os
import uuid

from django.conf import settings

from accounts.models import Group
from infrastructure.models import Environment
from resources.models import ResourceType
from servicecatalog.models import ServiceBlueprint, TerraformOperationBlueprintItem
from source_code_repos.models import SourceCodeRepo
from utilities.models import ConnectionInfo
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

branch = os.environ.get("TF_REPRO_BRANCH", "main")
source_code_repo = connection_info = local_source = None
if os.environ.get("TF_REPRO_REPO"):
    source_code_repo = SourceCodeRepo.objects.get(label=os.environ["TF_REPRO_REPO"]).cast()
    if "akumar_terraform" not in source_code_repo.repo_url:
        raise SystemExit(
            f"Source Code Repository '{source_code_repo.label}' points at "
            f"{source_code_repo.repo_url}, not the akumar_terraform repo."
        )
elif os.environ.get("TF_REPRO_CONN"):
    connection_info = ConnectionInfo.objects.get(name=os.environ["TF_REPRO_CONN"])
elif os.environ.get("TF_REPRO_SOURCE"):
    local_source = os.environ["TF_REPRO_SOURCE"]
else:
    raise SystemExit(
        "Set TF_REPRO_REPO (Source Code Repository label), TF_REPRO_CONN (Connection Info "
        "name), or TF_REPRO_SOURCE (local path). See the docstring at the top of this script."
    )

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
    if source_code_repo:
        # Mirrors TerraformOperationForm for the "Source Code Repository" option
        wd_kwargs.update(
            source_type="REPO",
            source_path_or_url=source_code_repo.get_repo_url_for_file(branch, subdir),
            source_code_repo=source_code_repo,
            git_branch=branch,
        )
    elif connection_info:
        wd_kwargs.update(
            source_type="GIT",
            source_path_or_url=REPO_URL,
            git_branch=branch,
            connection_info=connection_info,
        )
    else:
        wd_kwargs.update(source_type="LOCAL", source_path_or_url=local_source)
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
