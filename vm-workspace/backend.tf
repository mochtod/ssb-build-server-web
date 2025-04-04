terraform {
  backend "atlantis" {
    # Add Atlantis-specific backend configuration here
  }

  # Enable workspaces for managing multiple environments
  required_version = ">= 1.0.0"
}

variable "environment" {
  description = "The environment to deploy (e.g., dev, staging, prod)"
  type        = string
  default     = "development"
}

variable "host_group" {
  description = "The host group to deploy (e.g., web, database, app)"
  type        = string
  default     = "Server_Storage_Tech"
}

variable "host_collections" {
  description = "The host collections to deploy (e.g., collection1, collection2)"
  type        = list(string)
  default     = ["all-all"]
}

variable "registration_key" {
  description = "The content license to use for the environment"
  type        = string
  default     = "registration_key"
}

variable "organization" {
  description = "The organization to associate with the environment"
  type        = string
  default     = "CHR"
}