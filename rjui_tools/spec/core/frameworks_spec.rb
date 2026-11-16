# frozen_string_literal: true

require_relative '../spec_helper'
require 'core/frameworks'

RSpec.describe RjuiTools::Core::Frameworks do
  describe '.for' do
    it 'defaults to the Next adapter when config is nil' do
      expect(described_class.for(nil)).to be_a(described_class::NextAdapter)
    end

    it 'defaults to the Next adapter when web_framework is absent' do
      expect(described_class.for({})).to be_a(described_class::NextAdapter)
    end

    it 'resolves the built-in next adapter by name' do
      expect(described_class.for({ 'web_framework' => 'next' })).to be_a(described_class::NextAdapter)
    end

    it 'rejects an unknown built-in name' do
      expect { described_class.for({ 'web_framework' => 'nuxt' }) }
        .to raise_error(ArgumentError, /Unknown web_framework 'nuxt'/)
    end

    it 'builds a custom adapter from an object declaration' do
      adapter = described_class.for({ 'web_framework' => { 'name' => 'remix' } })
      expect(adapter).to be_a(described_class::CustomAdapter)
      expect(adapter.name).to eq('remix')
    end

    it 'rejects non-string, non-object values' do
      expect { described_class.for({ 'web_framework' => 42 }) }
        .to raise_error(ArgumentError, /must be a built-in name string or a custom adapter object/)
    end
  end

  describe '.apply_directive (template copies)' do
    let(:next_adapter) { described_class.for(nil) }
    let(:bare_adapter) { described_class::CustomAdapter.new('name' => 'bare') }
    let(:top_directive) { %("use client";\n\nimport { x } from 'y';\n) }
    let(:mid_directive) { "// NetworkImage.tsx\n// comment\n\n\"use client\";\n\nimport React from 'react';\n" }

    it 'leaves Next templates unchanged, byte for byte' do
      expect(described_class.apply_directive(top_directive, next_adapter)).to eq(top_directive)
      expect(described_class.apply_directive(mid_directive, next_adapter)).to eq(mid_directive)
    end

    it 'drops the directive line and its trailing blank when the adapter declares none' do
      expect(described_class.apply_directive(top_directive, bare_adapter)).to eq(%(import { x } from 'y';\n))
      expect(described_class.apply_directive(mid_directive, bare_adapter))
        .to eq("// NetworkImage.tsx\n// comment\n\nimport React from 'react';\n")
    end

    it 'replaces the directive in place for a different non-empty declaration' do
      adapter = described_class::CustomAdapter.new('use_client_directive' => "'use client'")
      expect(described_class.apply_directive(top_directive, adapter))
        .to eq(%('use client'\n\nimport { x } from 'y';\n))
    end
  end

  describe RjuiTools::Core::Frameworks::NextAdapter do
    # The Next adapter is the reference emit: these strings are the
    # historical output, byte for byte. Changing any of them changes
    # every generated file in every Next consumer.
    subject(:adapter) { described_class.new }

    it 'pins the historical Next emit strings exactly' do
      expect(adapter.name).to eq('next')
      expect(adapter.use_client_directive).to eq('"use client";')
      expect(adapter.link_import_line).to eq("import Link from 'next/link';")
      expect(adapter.link_href_attribute).to eq('href')
      expect(adapter.router_hook_import).to eq('import { useRouter } from "next/navigation";')
      expect(adapter.router_hook_statement).to eq('const router = useRouter();')
      expect(adapter.router_type_import)
        .to eq('import { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";')
      expect(adapter.router_type).to eq('AppRouterInstance')
      expect(adapter.router_type_jsdoc)
        .to eq('import("next/dist/shared/lib/app-router-context.shared-runtime").AppRouterInstance')
    end

    it 'emits full line prefixes for the heredoc seams' do
      expect(adapter.use_client_prefix).to eq(%("use client";\n\n))
      expect(adapter.router_type_import_prefix)
        .to eq(%(import { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";\n))
      expect(adapter.router_hook_import_prefix).to eq(%(import { useRouter } from "next/navigation";\n))
      expect(adapter.router_hook_statement_line).to eq("  const router = useRouter();\n")
    end
  end

  describe RjuiTools::Core::Frameworks::CustomAdapter do
    it 'honors a full declaration (Remix-shaped)' do
      adapter = described_class.new(
        'name' => 'remix',
        'use_client_directive' => '',
        'link_import_line' => "import { Link } from '@remix-run/react';",
        'link_href_attribute' => 'to',
        'router_hook_import' => "import { useNavigate } from '@remix-run/react';",
        'router_hook_statement' => 'const router = useNavigate();',
        'router_type_import' => "import { NavigateFunction } from 'react-router-dom';",
        'router_type' => 'NavigateFunction',
        'router_type_jsdoc' => "import('react-router-dom').NavigateFunction"
      )
      expect(adapter.link_href_attribute).to eq('to')
      expect(adapter.router_hook_statement).to eq('const router = useNavigate();')
      expect(adapter.router_type).to eq('NavigateFunction')
    end

    it 'suppresses whole lines for empty declarations instead of emitting blanks' do
      adapter = described_class.new('name' => 'bare')
      expect(adapter.use_client_prefix).to eq('')
      expect(adapter.router_type_import_prefix).to eq('')
      expect(adapter.router_hook_import_prefix).to eq('')
      expect(adapter.router_hook_statement_line).to eq('')
    end

    it 'defaults: name custom, href attribute, untyped router, jsdoc falls back to router_type' do
      adapter = described_class.new({})
      expect(adapter.name).to eq('custom')
      expect(adapter.link_href_attribute).to eq('href')
      expect(adapter.router_type).to eq('any')
      expect(adapter.router_type_jsdoc).to eq('any')
    end

    it 'jsdoc falls back to a declared router_type' do
      adapter = described_class.new('router_type' => 'NavigateFunction')
      expect(adapter.router_type_jsdoc).to eq('NavigateFunction')
    end

    it 'rejects unknown keys (typo protection)' do
      expect { described_class.new('router_import' => 'x') }
        .to raise_error(ArgumentError, /Unknown web_framework key\(s\) router_import/)
    end

    it 'rejects non-string values' do
      expect { described_class.new('router_type' => 3) }
        .to raise_error(ArgumentError, /must be strings/)
    end
  end
end
