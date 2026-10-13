# Repro: Terraform apply fails, but CloudBolt order reports "Completed successfully".
# CONTROL: no backend block, so CloudBolt uses -state=<file> and reports the failure correctly.

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
