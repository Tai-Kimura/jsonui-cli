# frozen_string_literal: true

require 'json'
require 'open3'

# The JavaScript twins of rjui's TypeScript templates (lib/react/templates/js).
#
# A JavaScript project (`typescript` false or absent) gets .js / .jsx copies of
# the built-ins `rjui init` and `rjui build` write — NetworkImage, LinkifyText,
# EmbedContainer, Configuration, useColorMode — so its output holds no .ts and
# no type annotation (until jsonui-cli 1.9.0 these were copied as .ts / .tsx
# whatever the project was). The twins are DERIVED, never hand-edited: each is
# its template's leading header (directive, comments — the ownership markers
# `rjui build` reads live there) followed by esbuild's type-stripped body
# (loader ts / tsx, JSX preserved, UTF-8 kept). esbuild drops the body's
# comments; the TypeScript template stays the documented source.
#
# Regenerate after changing a template (esbuild from spec/support):
#   ruby -r ./rjui_tools/spec/support/js_templates -e 'JsTemplates.write!'
# spec/react/js_templates_spec.rb fails when a twin differs from what this
# renders.
module JsTemplates
  module_function

  DIR = File.expand_path('../../lib/react/templates', __dir__)
  JS_DIR = File.join(DIR, 'js')
  # template => its twin
  TWINS = {
    'Configuration.ts' => 'Configuration.js',
    'EmbedContainer.tsx' => 'EmbedContainer.jsx',
    'linkify_text.tsx' => 'linkify_text.jsx',
    'network_image.tsx' => 'network_image.jsx',
    'use_color_mode.ts' => 'use_color_mode.js'
  }.freeze

  def esbuild_module
    File.join(__dir__, 'node_modules', 'esbuild')
  end

  def unavailable_reason
    return 'node is not on PATH' unless system('which node > /dev/null 2>&1')
    return 'esbuild is not installed (npm ci --prefix rjui_tools/spec/support)' unless File.directory?(esbuild_module)

    nil
  end

  # [header, body]: the header is the run of directives, blank lines and
  # comments before the first line of code.
  def split(source)
    at = 0
    loop do
      rest = source[at..]
      skipped = rest[/\A\s+/].to_s.length
      rest = rest[skipped..]
      token = if rest.start_with?('//') then rest[/\A[^\n]*\n?/]
              elsif rest.start_with?('/*') then rest[%r{\A/\*.*?\*/[^\n]*\n?}m]
              elsif rest.start_with?('"use client";') then rest[/\A"use client";[^\n]*\n?/]
              end
      break unless token

      at += skipped + token.length
    end
    [source[0...at], source[at..]]
  end

  def strip_types(body, loader)
    script = <<~JS
      const esbuild = require(#{JSON.generate(esbuild_module)});
      let src = ''; process.stdin.on('data', d => { src += d; });
      process.stdin.on('end', () => {
        process.stdout.write(esbuild.transformSync(src, { loader: #{JSON.generate(loader)}, jsx: 'preserve', charset: 'utf8' }).code);
      });
    JS
    out, err, status = Open3.capture3('node', '-e', script, stdin_data: body)
    raise "esbuild: #{err}" unless status.success?

    out
  end

  def render(template)
    source = File.read(File.join(DIR, template), encoding: 'UTF-8')
    header, body = split(source)
    header = header.sub(/\n*\z/, "\n\n")
    header + strip_types(body, template.end_with?('.tsx') ? 'tsx' : 'ts')
  end

  def write!
    Dir.mkdir(JS_DIR) unless File.directory?(JS_DIR)
    TWINS.each { |template, twin| File.write(File.join(JS_DIR, twin), render(template)) }
  end
end
