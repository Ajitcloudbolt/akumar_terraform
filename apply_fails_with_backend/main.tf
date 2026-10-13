# Repro: Terraform apply fails, but CloudBolt order reports "Completed successfully".
# A "backend" block makes CloudBolt take the remote-backend path (uses_remote_backend=True),
# so it runs `terraform state pull` after the failed apply, and that exit code 0 masks the failure.
# The "local" backend behaves like azurerm/s3 for this code path but needs no cloud credentials.
terraform {
  backend "local" {}
}

# Simulates a resource that does get created (e.g. a resource group)
resource "terraform_data" "created_ok" {
  input = "partially deployed"
}

# Passes `terraform plan`, fails at `terraform apply` (like a storage-account name collision)
resource "terraform_data" "fails_on_apply" {
  depends_on = [terraform_data.created_ok]

  provisioner "local-exec" {
    command = "echo 'Simulated apply failure: StorageAccountAlreadyTaken' >&2; exit 1"
  }
}

output "status" {
  value = terraform_data.created_ok.output
}
