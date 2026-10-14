# akumar_terraform

Reproduces a CloudBolt bug: a Terraform build item order shows **Completed successfully** even
though `terraform apply` failed in Azure.

| Folder | What it does | Result in CloudBolt |
|---|---|---|
| `azure_apply_fails_with_backend/` | Creates a resource group, VNet and subnet (no `Microsoft.Storage` service endpoint), then a storage account locked to that subnet. Azure rejects the storage account. | **Completed successfully** (bug) |
| `azure_storage_account/` | Creates only a storage account on that existing subnet. Azure rejects it, so nothing is created (the customer's case). | **Completed successfully** (bug) |

Both configs define a `backend` block, which is what triggers the bug. They use `backend "local"`
so no state storage is needed; an `azurerm` backend block is included, commented out, for an exact
match with the customer. The same config without a backend block correctly ends as **Failed**.

## Set up in CloudBolt

Prerequisite: Terraform >= 1.4 at `/var/opt/cloudbolt/terraform/bin/terraform`.

For each folder, create a blueprint (Catalog > New Blueprint) with one **Terraform** build item:

| Setting | Value |
|---|---|
| Source | Remote Source [Git]: `https://github.com/Ajitcloudbolt/akumar_terraform.git` |
| Branch | `main` |
| Subdirectory | `azure_apply_fails_with_backend` or `azure_storage_account` |
| Variable maps | **Azure-to-Terraform Variable Map** (passes the Azure resource handler's credentials as `ARM_*` env vars) |
| Enabled environment | An environment of an Azure resource handler |

Order `azure_apply_fails_with_backend` first: `azure_storage_account` uses the subnet it creates
(`rg-cmp-apply-fail` / `vnet-cmp-apply-fail` / `snet-app`). When ordering, pick a group that has the
Azure environment.

## What you'll see

```
Terraform apply failed
Pulled state from remote backend
Parsing output with Parse Terraform State
Job completed with status 'SUCCESS'
```
The order shows **Completed successfully**, and the job Output shows `returncode: 0` and an empty
`std_err`: the Azure error from the failed apply is not shown anywhere in CloudBolt (see the resource
group's Activity log in Azure for it).

## Why it happens

`TerraformRunner._execute_wrapper` (`jobengine/jobmodules/generic_job.py`) catches the failed
`terraform apply`. Because the config defines a backend, it then runs `terraform state pull`.
`ExecutableWrapper.evaluate_output()` / `build_content()` (`generic_jobs/wrapper/wrappers.py`) use
the *last* command run, the successful `state pull`, so the job is marked SUCCESS and the apply's
exit code and error are discarded. Introduced by [CMP-8] (`419a65f3c9`, v2023.4.10).

## Clean up

Delete the CloudBolt resources from the orders (runs `terraform destroy`), or delete the
`rg-cmp-apply-fail` resource group in Azure.
