resource "cloudflare_workers_script" "edge" {
  name    = "edge"
  content = file("../edge/dist/index.js")
  plain_text_binding {
    name = "ORIGIN"
    text = aws_lb.web.dns_name
  }
}

resource "cloudflare_r2_bucket" "assets" {
  name = "assets"
}
