terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  public_subnets = {
    for index, cidr in var.public_subnet_cidrs :
    tostring(index) => {
      cidr = cidr
      az   = var.availability_zones[index]
    }
  }

  private_subnets = {
    for index, cidr in var.private_subnet_cidrs :
    tostring(index) => {
      cidr = cidr
      az   = var.availability_zones[index]
    }
  }

  cluster_tags = var.kubernetes_cluster_name == "" ? {} : {
    "kubernetes.io/cluster/${var.kubernetes_cluster_name}" = "shared"
  }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, { Name = "${var.name}-vpc" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name}-igw" })
}

resource "aws_subnet" "public" {
  for_each                = local.public_subnets
  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr
  map_public_ip_on_launch = true
  availability_zone       = each.value.az

  tags = merge(
    var.tags,
    local.cluster_tags,
    {
      Name                     = "${var.name}-public-${each.key}"
      "kubernetes.io/role/elb" = "1"
    },
  )
}

resource "aws_subnet" "private" {
  for_each          = local.private_subnets
  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.az

  tags = merge(
    var.tags,
    local.cluster_tags,
    {
      Name                              = "${var.name}-private-${each.key}"
      "kubernetes.io/role/internal-elb" = "1"
    },
  )
}

resource "aws_eip" "nat" {
  count  = var.enable_nat_gateway ? 1 : 0
  domain = "vpc"

  tags = merge(var.tags, { Name = "${var.name}-nat-eip" })
}

resource "aws_nat_gateway" "this" {
  count         = var.enable_nat_gateway ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public["0"].id

  depends_on = [aws_internet_gateway.this]

  tags = merge(var.tags, { Name = "${var.name}-nat" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name}-public-rt" })
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name}-private-rt" })
}

resource "aws_route" "private_default" {
  count                  = var.enable_nat_gateway ? 1 : 0
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}

resource "aws_route_table_association" "private" {
  for_each       = aws_subnet.private
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private.id
}
