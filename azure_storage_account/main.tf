# Same failure as the customer's "Azure Storage Account" order: Azure rejects the storage account
# at apply time because the subnet it is locked to has no Microsoft.Storage service endpoint.
# Only the storage account is created here, so when apply fails NOTHING is created - yet CloudBolt
# marks the order "Completed successfully" because the config defines a backend.
#
# Uses an existing resource group / VNet / subnet without a Microsoft.Storage service endpoint
# (defaults: the ones created by the "TF Repro - Azure Apply Fails (Backend)" blueprint).
# Credentials come from CloudBolt's OOTB "Azure-to-Terraform Variable Map".

terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
  }

  # Any backend triggers the bug. "local" needs no extra Azure setup.
  backend "local" {}

  # For an exact match with the customer, use azurerm instead (needs an existing storage account
  # and container; backend settings can't use variables):
  # backend "azurerm" {
  #   resource_group_name  = "rg-tfstate"
  #   storage_account_name = "<state storage account>"
  #   container_name       = "tfstate"
  #   key                  = "cmp-storage-account.tfstate"
  # }
}

provider "azurerm" {
  features {}
  resource_provider_registrations = "none"
}

variable "resource_group_name" {
  type    = string
  default = "rg-cmp-apply-fail"
}

variable "virtual_network_name" {
  type    = string
  default = "vnet-cmp-apply-fail"
}

variable "subnet_name" {
  type    = string
  default = "snet-app"
}

data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

# Has no "Microsoft.Storage" service endpoint
data "azurerm_subnet" "app" {
  name                 = var.subnet_name
  virtual_network_name = var.virtual_network_name
  resource_group_name  = data.azurerm_resource_group.rg.name
}

# Fails at apply: the subnet has no Microsoft.Storage service endpoint
resource "azurerm_storage_account" "zvm" {
  name                     = "stzvm${substr(md5(data.azurerm_subnet.app.id), 0, 12)}"
  resource_group_name      = data.azurerm_resource_group.rg.name
  location                 = data.azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  network_rules {
    default_action             = "Deny"
    virtual_network_subnet_ids = [data.azurerm_subnet.app.id]
  }
}
