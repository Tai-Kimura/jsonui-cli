# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/js_templates'
require 'core/templates'

# The JavaScript twins of the built-in templates (lib/react/templates/js) are
# what spec/support/js_templates.rb renders from the TypeScript templates —
# header kept, body type-stripped by esbuild. A template changed without its
# twin regenerated fails here (regenerate: see js_templates.rb).
RSpec.describe 'the JavaScript twins of the built-in templates' do
  before { skip "js templates: #{JsTemplates.unavailable_reason}" if JsTemplates.unavailable_reason }

  JsTemplates::TWINS.each do |template, twin|
    it "#{twin} is #{template} without its types" do
      committed = File.read(File.join(JsTemplates::JS_DIR, twin), encoding: 'UTF-8')
      expect(committed).to eq(JsTemplates.render(template)), "regenerate: ruby -r ./rjui_tools/spec/support/js_templates -e 'JsTemplates.write!'"
    end
  end

  it 'every twin keeps its template header — the ownership marker rjui build reads' do
    JsTemplates::TWINS.each do |template, twin|
      header, = JsTemplates.split(File.read(File.join(JsTemplates::DIR, template), encoding: 'UTF-8'))
      expect(File.read(File.join(JsTemplates::JS_DIR, twin), encoding: 'UTF-8')).to start_with(header.sub(/\n*\z/, "\n")), twin
    end
  end

  it 'every template has a twin, and the project language picks the copy' do
    # use_media_query.ts has no twin: no command copies it into a project;
    # only the conformance web host (a TypeScript project) vendors it
    # (conformance/hosts/web/scripts/generate.mjs).
    expect(Dir.children(JsTemplates::DIR).grep(/\.tsx?\z/) - ['use_media_query.ts']).to match_array(JsTemplates::TWINS.keys)
    js = { 'typescript' => false }
    ts = { 'typescript' => true }
    expect(RjuiTools::Core::Templates.path('network_image.tsx', js)).to eq(File.join(JsTemplates::JS_DIR, 'network_image.jsx'))
    expect(RjuiTools::Core::Templates.path('network_image.tsx', ts)).to eq(File.join(JsTemplates::DIR, 'network_image.tsx'))
    expect(RjuiTools::Core::Templates.file_name('useColorMode.ts', {})).to eq('useColorMode.js')
    expect(RjuiTools::Core::Templates.file_name('useColorMode.ts', ts)).to eq('useColorMode.ts')
    JsTemplates::TWINS.each_value { |twin| expect(File.file?(File.join(JsTemplates::JS_DIR, twin))).to be(true), twin }
  end
end
