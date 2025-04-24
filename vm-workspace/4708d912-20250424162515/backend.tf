
# Local backend configuration
terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
