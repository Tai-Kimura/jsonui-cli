# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/react_generator'

RSpec.describe RjuiTools::React::ReactGenerator do
  let(:config) { { 'use_tailwind' => true, 'typescript' => true } }
  let(:generator) { described_class.new(config) }

  describe '#collect_lucide_icons' do
    it 'collects mapped icon names from TabView tabs' do
      json = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'Home', 'icon' => 'house' },
          { 'title' => 'Settings', 'icon' => 'gearshape' }
        ]
      }
      result = generator.send(:collect_lucide_icons, json).to_a.sort
      expect(result).to eq(%w[Home Settings])
    end

    it 'includes selectedIcon when present' do
      json = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'Home', 'icon' => 'house', 'selectedIcon' => 'house.fill' }
        ]
      }
      # Both 'house' and 'house.fill' map to 'Home' — de-duped by Set
      expect(generator.send(:collect_lucide_icons, json).to_a).to eq(['Home'])
    end

    it 'defaults missing icon to Circle (matches build_icon default)' do
      json = { 'type' => 'TabView', 'tabs' => [{ 'title' => 'Tab' }] }
      expect(generator.send(:collect_lucide_icons, json).to_a).to eq(['Circle'])
    end

    it 'skips iconType: resource tabs entirely' do
      json = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'Learn', 'iconType' => 'resource', 'icon' => 'learn' }
        ]
      }
      expect(generator.send(:collect_lucide_icons, json).to_a).to be_empty
    end

    it 'recurses into nested children' do
      json = {
        'type' => 'View',
        'child' => [
          {
            'type' => 'View',
            'child' => [
              { 'type' => 'TabView', 'tabs' => [{ 'title' => 'X', 'icon' => 'bell' }] }
            ]
          }
        ]
      }
      expect(generator.send(:collect_lucide_icons, json).to_a).to eq(['Bell'])
    end

    it 'returns an empty set when no TabView is present' do
      json = { 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'hi' }] }
      expect(generator.send(:collect_lucide_icons, json).to_a).to be_empty
    end
  end

  describe '#generate sets _current_json_name for StringManager scoping' do
    # Use a minimal View so generate returns quickly. The ASSERTion is about
    # the side effect on config['_current_json_name'], which StringManagerHelper
    # reads to scope bare key lookups to the current screen's namespace.
    let(:minimal_json) { { 'type' => 'View' } }

    it 'converts PascalCase component name to snake_case when no subdir is passed' do
      generator.generate('Installation', minimal_json)
      expect(config['_current_json_name']).to eq('installation')
    end

    it 'prepends subdir segments to form a directory-qualified namespace' do
      generator.generate('Installation', minimal_json, subdir: 'learn')
      expect(config['_current_json_name']).to eq('learn_installation')
    end

    it 'flattens multi-level subdir into underscore-joined namespace' do
      generator.generate('Advanced', minimal_json, subdir: 'learn/deep')
      expect(config['_current_json_name']).to eq('learn_deep_advanced')
    end

    it 'downcases every subdir part' do
      generator.generate('Page', minimal_json, subdir: 'Learn/Topic')
      expect(config['_current_json_name']).to eq('learn_topic_page')
    end

    it 'ignores empty subdir gracefully' do
      generator.generate('Home', minimal_json, subdir: '')
      expect(config['_current_json_name']).to eq('home')
    end

    it 'ignores File.dirname sentinel `.` for root-level layouts' do
      # build_command.rb passes `File.dirname(relative_path)` as the subdir.
      # For a root-level layout that returns the string "." — without this
      # guard the namespace becomes `._learn_index` and Phase 2 of
      # StringManager lookup can never match the strings.json namespace.
      generator.generate('LearnIndex', minimal_json, subdir: '.')
      expect(config['_current_json_name']).to eq('learn_index')
    end

    it 'strips leading `.` while keeping real subdir parts' do
      generator.generate('Index', minimal_json, subdir: './learn')
      expect(config['_current_json_name']).to eq('learn_index')
    end
  end

  describe '#generate_component_file StringManager import emission' do
    # `uses_string_manager?(json)` only inspects a hard-coded attribute
    # whitelist (text / hint / placeholder / label / title / src / url),
    # so it misses snake_case values on custom component props (e.g.
    # `TopBar brandLabel="chrome_brand_name"` — `brandLabel` is not in
    # the whitelist). The scaffold-generated converter emits
    # `StringManager.currentLanguage.xxx` for those props anyway via
    # `convert_string_key`, so the downstream JSX references the global
    # but the file header's `import { useStringManager } …` would be
    # missing — TS `TS2304: Cannot find name '$s'`.
    #
    # The fix: also scan the already-converted `jsx_content` for
    # `StringManager.` so any converter path that lands a reference
    # in the JSX stream gets its import emitted AND the reference
    # rewritten to `$s.` (the subscribed snapshot).
    let(:minimal_json) { { 'type' => 'View' } }

    it 'emits the useStringManager import + $s declaration and rewrites references when jsx_content contains a StringManager reference (custom component prop path)' do
      jsx = "      <TopBar brandLabel={StringManager.currentLanguage.chromeBrandName} />"
      result = generator.send(:generate_component_file, 'Chrome', jsx, minimal_json)
      expect(result).to include("import { useStringManager } from '@/generated/StringManager';")
      expect(result).to include('const $s = useStringManager();')
      expect(result).to include('{$s.chromeBrandName}')
      expect(result).not_to include('StringManager.currentLanguage.')
    end

    it 'still emits the import via the JSON walk when a standard Label text uses a snake_case key' do
      jsx = '' # jsx_content is empty here on purpose — we rely on uses_string_manager?(json)
      json_with_label = { 'type' => 'Label', 'text' => 'hero_eyebrow' }
      result = generator.send(:generate_component_file, 'Home', jsx, json_with_label)
      expect(result).to include("import { useStringManager } from '@/generated/StringManager';")
      expect(result).to include('const $s = useStringManager();')
    end

    it 'omits the import when neither the JSON tree nor the jsx_content references StringManager' do
      jsx = '      <div>static content</div>'
      result = generator.send(:generate_component_file, 'Static', jsx, minimal_json)
      expect(result).not_to include('StringManager')
      expect(result).not_to include('$s')
    end
  end

  describe '#generate_component_file Configuration (FontSpec) import emission' do
    # The generator scans the already-converted JSX for the
    # Configuration.Font.resolve(...) emission BaseConverter produces when
    # `fontFamily` is set. If found, it imports `Configuration` from the
    # synced template path so the spread compiles and the host-supplied
    # fontProvider can intercept.
    let(:minimal_json) { { 'type' => 'View' } }

    it 'emits the Configuration import when jsx_content contains Configuration.Font.resolve(...)' do
      jsx = "      <span style={{ ...Configuration.Font.resolve({ family: 'Inter', italic: false }) }}>Hi</span>"
      result = generator.send(:generate_component_file, 'Hero', jsx, minimal_json)
      expect(result).to include("import { Configuration } from '@/lib/jsonui/Configuration';")
    end

    it 'omits the Configuration import when no FontSpec emission is present in the JSX stream' do
      jsx = '      <span>plain text</span>'
      result = generator.send(:generate_component_file, 'Plain', jsx, minimal_json)
      expect(result).not_to include("from '@/lib/jsonui/Configuration'")
      expect(result).not_to include('Configuration.Font')
    end
  end

  describe '#generate_component_file data prop requiredness (regression: rjui-include-partial-requires-data-prop-not-passed)' do
    # A binding-less partial (static logo header) never reads `data`, but
    # include sites render it as `<Name />` with no props — a required
    # `data` prop makes the generated files fail each other with TS2741.
    let(:minimal_json) { { 'type' => 'View' } }

    it 'makes data optional when the body never reads data' do
      jsx = '      <header>logo + service name</header>'
      result = generator.send(:generate_component_file, 'UserHeader', jsx, minimal_json)
      expect(result).to include('data?: UserHeaderData;')
    end

    it 'keeps data required when the JSX reads data' do
      jsx = '      <span>{data.title}</span>'
      result = generator.send(:generate_component_file, 'Titled', jsx, minimal_json)
      expect(result).to include('data: TitledData;')
      expect(result).not_to include('data?:')
    end

    it 'keeps data required when focus bindings reference data' do
      json = { 'type' => 'View', 'child' => [
        { 'type' => 'TextField', 'id' => 'email_input' }
      ] }
      jsx = '      <input />'
      result = generator.send(:generate_component_file, 'Form', jsx, json)
      expect(result).to include('data: FormData;')
    end

    it 'does not mistake cellData references for data usage' do
      jsx = '      <Cell data={cellData} />'
      result = generator.send(:generate_component_file, 'ListHost', jsx, minimal_json)
      expect(result).to include('data?: ListHostData;')
    end
  end

  describe '#generate_component_file root visibility wrapper (regression: rjui-root-visibility-binding-emits-bare-jsx-expression-container)' do
    # A root element with a visibility binding arrives as a bare JSX
    # expression container (`{cond && (...)}`), which is not legal directly
    # under `return (` — it must be wrapped in a fragment.
    let(:minimal_json) { { 'type' => 'View' } }

    it 'wraps a root-level expression container in a fragment' do
      jsx = "    {data.drawerVisibility !== \"gone\" && (\n    <div id=\"adminDrawerView\">x</div>\n    )}"
      result = generator.send(:generate_component_file, 'AdminDrawer', jsx, minimal_json)
      expect(result).to match(/return \(\s*\n\s*<>\s*\n\s*\{data\.drawerVisibility/)
      expect(result).to include('</>')
    end

    it 'leaves element-rooted JSX unwrapped' do
      jsx = '      <div>plain</div>'
      result = generator.send(:generate_component_file, 'Plain2', jsx, minimal_json)
      expect(result).not_to include('<>')
    end
  end
end
RSpec.describe RjuiTools::React::ReactGenerator, 'focus-state declarations' do
  let(:generator) do
    described_class.new({ 'use_tailwind' => true, 'layouts_directory' => '/tmp/x', 'generated_directory' => '/tmp/x/out' })
  end

  it 'hoists a ref + effect per id-bearing editable field and imports the hooks' do
    json = { 'type' => 'View', 'child' => [
      { 'type' => 'TextField', 'id' => 'email_field' },
      { 'type' => 'TextView', 'id' => 'note_input' }
    ] }
    out = generator.generate('FocusScreen', json)
    expect(out).to include("import React, { useRef, useEffect } from 'react';")
    expect(out).to include('const emailFieldRef = useRef<HTMLInputElement | null>(null);')
    expect(out).to include('const noteInputRef = useRef<HTMLTextAreaElement | null>(null);')
    expect(out).to include('useEffect(() => { if (data.emailFieldIsFocused) { emailFieldRef.current?.focus(); } }, [data.emailFieldIsFocused]);')
    expect(out).to include('"use client"')
  end

  it 'emits nothing focus-related without editable ids' do
    json = { 'type' => 'View', 'child' => [{ 'type' => 'Text', 'text' => 'hi' }] }
    out = generator.generate('PlainScreen', json)
    expect(out).not_to include('useRef')
    expect(out).not_to include('IsFocused')
  end
end
