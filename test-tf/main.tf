# Simple test configuration for Atlantis
terraform {
  required_version = ">= 0.14.0"
}

variable "test_string" {
  description = "A test string variable"
  type        = string
  default     = "Hello Atlantis"
}

resource "null_resource" "test" {
  triggers = {
    test_string = var.test_string
  }

  provisioner "local-exec" {
    command = "echo ${var.test_string}"
  }
}

output "test_output" {
  value = var.test_string
}
