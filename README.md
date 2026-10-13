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
2. **Add a Source Code Repository** for this private repo: Admin > Source Code Repositories > Add.
   - Type: GitHub, Label: `akumar_terraform`
   - URL: `https://github.com/Ajitcloudbolt/akumar_terraform`
   - Credentials: your GitHub token (read access to this repo is enough)
3. **Create the blueprints** (from the CloudBolt `src` dir, e.g. `/opt/cloudbolt`):
   ```bash
   TF_REPRO_REPO=akumar_terraform python manage.py shell < cloudbolt_setup/create_blueprints.py
   ```
   Optional: `TF_REPRO_ENV="<environment name>"` to pick the environment.
   Alternatives to a Source Code Repository: `TF_REPRO_CONN=<Connection Info name>` (Remote
   Source [Git] with the token as the Connection Info password), or `TF_REPRO_SOURCE=/path/to/clone`
   if the server can't reach github.com.

   **Or create them by hand in the UI:** Catalog > New Blueprint, add a **Terraform** build item,
   Source = *Source Code Repository* `akumar_terraform`, branch `main`, Subdirectory
   `apply_fails_with_backend` (and a second blueprint with `apply_fails_no_backend`), then enable an
   environment on the build item.
4. **Order** "TF Repro - Apply Fails (Backend)" from the Catalog. The order shows
   *Completed successfully* while its log says *Terraform apply failed*. Order
   "TF Repro - Apply Fails (No Backend)" to compare: it correctly shows *Failed*.
