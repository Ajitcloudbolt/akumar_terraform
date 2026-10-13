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
