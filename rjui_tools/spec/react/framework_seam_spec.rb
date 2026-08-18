# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/react_generator'
require 'react/converters/button_converter'

# The web_framework seam: emitters ask the resolved adapter for every
# framework-specific string. `next` (the default) must reproduce the
# historical emit byte for byte; a custom adapter declared in config
# swaps the wiring without touching the emitters.
RSpec.describe 'web_framework seam' do
  let(:remix_framework) do
    {
      'name' => 'remix',
      'use_client_directive' => '',
      'link_import_line' => "import { Link } from '@remix-run/react';",
      'link_href_attribute' => 'to',
      'router_hook_import' => "import { useNavigate } from '@remix-run/react';",
      'router_hook_statement' => 'const router = useNavigate();',
      'router_type' => 'NavigateFunction'
    }
  end

  describe 'component Link emission (react_generator)' do
    let(:json_with_href) do
      { 'type' => 'View', 'child' => [{ 'type' => 'Button', 'text' => 'Go', 'href' => '/about' }] }
    end

    it 'emits the Next Link import by default' do
      generator = RjuiTools::React::ReactGenerator.new({ 'use_tailwind' => true, 'typescript' => true })
      result = generator.send(:generate_component_file, 'Nav', '      <div />', json_with_href)
      expect(result).to include("import Link from 'next/link';")
    end

    it 'emits the custom Link import when a custom adapter is declared' do
      generator = RjuiTools::React::ReactGenerator.new(
        { 'use_tailwind' => true, 'typescript' => true, 'web_framework' => remix_framework }
      )
      result = generator.send(:generate_component_file, 'Nav', '      <div />', json_with_href)
      expect(result).to include("import { Link } from '@remix-run/react';")
      expect(result).not_to include('next/link')
    end

    it 'suppresses the Link import entirely when the custom adapter declares none' do
      generator = RjuiTools::React::ReactGenerator.new(
        { 'use_tailwind' => true, 'typescript' => true, 'web_framework' => { 'name' => 'bare' } }
      )
      result = generator.send(:generate_component_file, 'Nav', '      <div />', json_with_href)
      expect(result).not_to include('import Link')
    end
  end

  describe 'use client directive (react_generator)' do
    let(:stateful_jsx) { '      <TopBar brandLabel={StringManager.currentLanguage.brandName} />' }

    it 'leads with "use client" by default when the component needs the client runtime' do
      generator = RjuiTools::React::ReactGenerator.new({ 'use_tailwind' => true, 'typescript' => true })
      result = generator.send(:generate_component_file, 'Chrome', stateful_jsx, { 'type' => 'View' })
      expect(result).to start_with(%("use client";\n\n))
    end

    it 'omits the directive (line and all) when the custom adapter declares it empty' do
      generator = RjuiTools::React::ReactGenerator.new(
        { 'use_tailwind' => true, 'typescript' => true, 'web_framework' => remix_framework }
      )
      result = generator.send(:generate_component_file, 'Chrome', stateful_jsx, { 'type' => 'View' })
      expect(result).not_to include('use client')
      expect(result).not_to start_with("\n")
    end
  end

  describe 'Link href attribute (button_converter)' do
    let(:button_json) { { 'type' => 'Button', 'text' => 'Go', 'href' => '/about' } }

    it 'wraps with <Link href> by default' do
      converter = RjuiTools::React::Converters::ButtonConverter.new(button_json, { 'use_tailwind' => true })
      expect(converter.convert).to include('<Link href="/about">')
    end

    it 'wraps with the custom attribute (Remix/TanStack <Link to>) when declared' do
      converter = RjuiTools::React::Converters::ButtonConverter.new(
        button_json, { 'use_tailwind' => true, 'web_framework' => remix_framework }
      )
      result = converter.convert
      expect(result).to include('<Link to="/about">')
      expect(result).not_to include('href=')
    end
  end
end
