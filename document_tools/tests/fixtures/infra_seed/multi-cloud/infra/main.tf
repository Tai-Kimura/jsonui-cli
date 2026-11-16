terraform {
  required_providers {
    aws        = { source = "hashicorp/aws" }
    google     = { source = "hashicorp/google" }
    cloudflare = { source = "cloudflare/cloudflare" }
  }
}

provider "aws" {
  region = "ap-northeast-1"
}

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "private" {
  vpc_id     = aws_vpc.main.id
  cidr_block = "10.0.1.0/24"
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.0.0/24"
  map_public_ip_on_launch = true
}

resource "aws_db_subnet_group" "db" {
  subnet_ids = [aws_subnet.private.id]
}

resource "aws_db_instance" "orders" {
  engine               = "postgres"
  engine_version       = "16"
  db_subnet_group_name = aws_db_subnet_group.db.name
  password             = var.db_password # a variable, never its value
}

resource "aws_ecs_cluster" "app" {
  name = "app"
}

resource "aws_ecs_service" "api" {
  cluster = aws_ecs_cluster.app.id
  network_configuration {
    subnets = [aws_subnet.private.id]
  }
  environment = jsonencode({ DB = aws_db_instance.orders.address, BUCKET = aws_s3_bucket.uploads.bucket })
}

resource "aws_lb" "web" {
  subnets = [aws_subnet.public.id]
}

resource "aws_s3_bucket" "uploads" {
  bucket = "example-uploads"
}

resource "aws_iam_role" "task" {
  name = "task"
}

resource "aws_cloudwatch_metric_alarm" "cpu" {
  alarm_name = "cpu"
}

resource "aws_route53_record" "www" {
  name = "www"
}

resource "aws_quantumledger_widget" "mystery" {
  name = "mystery"
}

resource "random_id" "suffix" {
  byte_length = 4
}

module "cdn" {
  source = "terraform-aws-modules/cloudfront/aws"
}
