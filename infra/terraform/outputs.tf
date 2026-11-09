output "frontend_bucket_name" {
  description = "S3 bucket for frontend files"
  value       = aws_s3_bucket.frontend.bucket
}

output "aws_region" {
  description = "AWS deployment region"
  value       = var.aws_region
}
output "cloudfront_domain_name" {
  description = "Public CloudFront URL"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.frontend.id
}