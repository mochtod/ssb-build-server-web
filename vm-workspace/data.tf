# Contents of rhel9-vm-workspace/data.tf

# ------------------------------------------------------------------------------  
# Data subnets
# ------------------------------------------------------------------------------  

# Placeholder for VMware network configurations
data "vsphere_network" "vm_network" {
  name          = "VM Network"
  datacenter_id = data.vsphere_datacenter.dc.id
}

locals {
   vm_name = "rhel9-ssbstester"
}

provider "vault" {
  address = "https://vault-prod-centralus-core.chrazure.cloud"
}

data "vault_generic_secret" "vm_credentials" {
  path = "secret/infra/vm/${local.vm_name}"
}

data "external" "next_ip" {
  program = ["python", "fetch_next_ip.py"]
  query = {
    range = "192.168.1.0/24"
    token = var.netbox_token
  }
}