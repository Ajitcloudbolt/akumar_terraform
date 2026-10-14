# Customer-like repro: Azure rejects the storage account at apply time because the subnet it is
# locked to has no Microsoft.Storage service endpoint. `terraform plan` passes; `apply` fails.
# CloudBolt still marks the order "Completed successfully" because the config defines a backend.
#
# Credentials come from CloudBolt's OOTB "Azure-to-Terraform Variable Map" (ARM_* env vars from
# the environment's Azure resource handler). Nothing secret is stored here.

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
  #   key                  = "cmp-apply-fail.tfstate"
  # }
}

provider "azurerm" {
  features {}
  # Don't try to register Azure resource providers (needs subscription-level rights)
  resource_provider_registrations = "none"
}

variable "location" {
  type    = string
  default = "eastus"
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-cmp-apply-fail"
  location = var.location
}

resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-cmp-apply-fail"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = ["10.10.0.0/16"]
}

# Missing on purpose: service_endpoints = ["Microsoft.Storage"]
resource "azurerm_subnet" "app" {
  name                 = "snet-app"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.10.1.0/24"]
}

# Fails at apply: the subnet has no Microsoft.Storage service endpoint
resource "azurerm_storage_account" "data" {
  name                     = "stcmpfail${substr(md5(azurerm_resource_group.rg.id), 0, 10)}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  network_rules {
    default_action             = "Deny"
    virtual_network_subnet_ids = [azurerm_subnet.app.id]
  }
}
