# akumar_terraform

Terraform configs that reproduce a CloudBolt bug: a Terraform Operation order shows
**Completed successfully** even though `terraform apply` failed.

| Folder | Backend block | Expected order status |
|---|---|---|
| `apply_fails_with_backend/` | `backend "local" {}` | **Completed successfully** (bug) |
| `apply_fails_no_backend/` | none | **Failed** (correct, control) |

Both configs use only the built-in `terraform_data` resource. They need no cloud credentials
or provider downloads, and Terraform >= 1.4.

## Why it happens

`TerraformRunner._execute_wrapper` (`jobengine/jobmodules/generic_job.py`) catches the failed
`terraform apply`. When the config defines a backend, it then runs `terraform state pull`.
`ExecutableWrapper.evaluate_output` reads the exit code of the *last* command, which is the
successful `state pull`, so the job is marked SUCCESS.

## Reproduce on another CloudBolt server

1. **Install Terraform >= 1.4** at the path CloudBolt uses (`settings.TERRAFORM_BINARY`, by default
   `/var/opt/cloudbolt/terraform/bin/terraform`), as the user that runs CloudBolt:
   ```bash
   V=1.9.8
   curl -sSLO https://releases.hashicorp.com/terraform/$V/terraform_${V}_linux_amd64.zip
   unzip -o terraform_${V}_linux_amd64.zip terraform
   install -m 755 terraform /var/opt/cloudbolt/terraform/bin/terraform
   ```
2. **Create the blueprints** from the CloudBolt dir, as the user that runs the jobengine
   (check with `ps -eo user,args | grep [j]obengine`):
   ```bash
   cd /opt/cloudbolt
   curl -sSLo /tmp/create_blueprints.py https://raw.githubusercontent.com/Ajitcloudbolt/akumar_terraform/main/cloudbolt_setup/create_blueprints.py
   sudo -u cloudbolt python3 manage.py shell < /tmp/create_blueprints.py
   ```
   This clones this public repo directly; no token is needed. Optional:
   `TF_REPRO_ENV="<environment name>"` to pick the environment, or `TF_REPRO_SOURCE=/path/to/clone`
   if the server can't reach github.com.

   **Or create them by hand in the UI:** Catalog > New Blueprint, add a **Terraform** build item,
   Source = *Remote Source [Git]* `https://github.com/Ajitcloudbolt/akumar_terraform.git`, branch
   `main`, Subdirectory
   `apply_fails_with_backend` (and a second blueprint with `apply_fails_no_backend`), then enable an
   environment on the build item.
3. **Order** "TF Repro - Apply Fails (Backend)" from the Catalog. The order shows
   *Completed successfully* while its log says *Terraform apply failed*. Order
   "TF Repro - Apply Fails (No Backend)" to compare: it correctly shows *Failed*.

## Azure repro (same failure as the customer)

`azure_apply_fails_with_backend/` creates a resource group, VNet and subnet, then a storage account
locked to that subnet. The subnet has no `Microsoft.Storage` service endpoint, so Azure rejects the
storage account at apply time (`plan` passes). It uses `backend "local"` so no state storage is
needed; an `azurerm` backend block is included, commented out, for an exact match.

Credentials come from CloudBolt's OOTB **Azure-to-Terraform Variable Map** (ARM_* env vars from the
environment's Azure resource handler). Create the blueprint with:
```bash
cd /opt/cloudbolt
curl -sSLo /tmp/create_blueprints.py https://raw.githubusercontent.com/Ajitcloudbolt/akumar_terraform/main/cloudbolt_setup/create_blueprints.py
sudo -u cloudbolt TF_REPRO_AZURE_ENV="<Azure environment name>" "$(which python)" manage.py shell < /tmp/create_blueprints.py
```
This only creates "TF Repro - Azure Apply Fails (Backend)". Order it: the order shows
*Completed successfully* although the storage account was rejected. Clean up by deleting the
CloudBolt resource or the `rg-cmp-apply-fail` resource group in Azure.

### Storage-account-only (exactly the customer's case: nothing gets created)

`azure_storage_account/` creates only a storage account on the existing subnet from the repro above
(`rg-cmp-apply-fail` / `vnet-cmp-apply-fail` / `snet-app`, no `Microsoft.Storage` endpoint). Azure
rejects it, so nothing is created, but the order shows *Completed successfully*. Keep that resource
group until you're done (order "TF Repro - Azure Apply Fails (Backend)" once first if it's gone).
```bash
sudo -u cloudbolt TF_REPRO_AZURE_ENV="<Azure environment name>" TF_REPRO_AZURE_CONFIG=storage \
  "$(which python)" manage.py shell < /tmp/create_blueprints.py
```
This creates the blueprint "Azure Storage Account (Repro)".
