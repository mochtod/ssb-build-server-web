terraform {
  required_providers {
    vsphere = {
      source  = "hashicorp/vsphere"
      version = "~> 2.4.0"
    }
    vault = {
      source  = "hashicorp/vault"
      version = "~> 3.0"
    }
  }
}

provider "vsphere" {
  user           = var.vsphere_user
  password       = var.vsphere_password
  vsphere_server = var.vsphere_server
  allow_unverified_ssl = true
}

provider "vault" {
  address = "https://vault-prod-centralus-core.chrazure.cloud"
  # Authentication can be configured using one of the following methods:
  # 1. Token authentication (recommended for development only)
  # token = var.vault_token
  
  # 2. AppRole authentication (recommended for production)
  # auth_login {
  #   path = "auth/approle/login"
  #   parameters = {
  #     role_id   = var.vault_role_id
  #     secret_id = var.vault_secret_id
  #   }
  # }
  
  # 3. Kubernetes authentication
  # auth_login {
  #   path = "auth/kubernetes/login"
  #   parameters = {
  #     role = var.vault_k8s_role
  #     jwt  = file("/var/run/secrets/kubernetes.io/serviceaccount/token")
  #   }
  # }
}
