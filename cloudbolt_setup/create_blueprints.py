"""
Creates two Terraform Operation blueprints on a CloudBolt server to reproduce the bug where a
failed `terraform apply` still shows the order as "Completed successfully".

  * "TF Repro - Apply Fails (Backend)"     -> BUG: order shows "Completed successfully"
  * "TF Repro - Apply Fails (No Backend)"  -> CONTROL: order correctly shows "Failed"

Run on the CloudBolt server as the user that runs the jobengine, from the CloudBolt src dir:
    cd /opt/cloudbolt
    sudo -u cloudbolt python3 manage.py shell < /path/to/create_blueprints.py

By default the Terraform files are cloned straight from the public GitHub repo, with no token.
To use something else instead, set one of these (checked in this order):
    TF_REPRO_REPO    Label of a Source Code Repository (Admin > Source Code Repositories) whose
                     URL is this repo and whose credentials hold a token that can read it.
                     This is the same as choosing "Source Code Repository" in the blueprint UI.
    TF_REPRO_CONN    Name of a Connection Info for github.com whose password is a token that can
                     read this repo (the "Remote Source [Git]" option in the UI).
    TF_REPRO_SOURCE  Local path to a checkout of this repo, for servers that can't reach github.

Optional:
    TF_REPRO_ENV     Name of the Environment to enable (default: first env with a resource handler)
    TF_REPRO_BRANCH  Branch to use (default: main)

Azure mode (customer-like failure against real Azure):
    TF_REPRO_AZURE_ENV  Name of an Environment of an Azure resource handler. When set, ONLY the
                        blueprint "TF Repro - Azure Apply Fails (Backend)" is created (the other
                        two are left untouched). It uses the OOTB "Azure-to-Terraform Variable Map"
                        so Terraform gets the resource handler's credentials as ARM_* env vars.

Safe to re-run: deletes and recreates the blueprints it manages each time.
"""
import os
import uuid

from django.conf import settings

from accounts.models import Group
from infrastructure.models import Environment
from resources.models import ResourceType
from generic_jobs.models import VariableMap
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
# Otherwise: public Git clone (WorkingDirectory finds or creates a token-less github.com
# Connection Info on its own)

variable_maps = []
if os.environ.get("TF_REPRO_AZURE_ENV"):
    environment = Environment.objects.get(name=os.environ["TF_REPRO_AZURE_ENV"])
    rh = environment.resource_handler and environment.resource_handler.cast()
    if not rh or type(rh).__name__ != "AzureARMHandler":
        raise SystemExit(f"Environment '{environment.name}' does not belong to an Azure handler.")
    variable_maps = [VariableMap.objects.get(name="Azure-to-Terraform Variable Map")]
    BLUEPRINTS = [
        ("TF Repro - Azure Apply Fails (Backend)", "azure_apply_fails_with_backend"),
    ]
elif os.environ.get("TF_REPRO_ENV"):
    environment = Environment.objects.get(name=os.environ["TF_REPRO_ENV"])
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
    elif local_source:
        wd_kwargs.update(source_type="LOCAL", source_path_or_url=local_source)
    else:
        wd_kwargs.update(
            source_type="GIT",
            source_path_or_url=REPO_URL,
            git_branch=branch,
            connection_info=connection_info,
        )
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
    si.variable_maps.add(*variable_maps)
    print(
        f"Blueprint id={bp.id} '{bp.name}' -> source={si.source_directory}, "
        f"groups={[g.name for g in groups]}, env={environment.name}, "
        f"variable_maps={[vm.name for vm in variable_maps]}"
    )
