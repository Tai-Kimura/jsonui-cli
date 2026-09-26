# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/bundler_define'
require 'json'
require 'open3'
require 'stringio'
require 'tmpdir'
require 'core/config_manager'
require 'react/react_generator'
require 'react/converters/collection_converter'

# A JavaScript project's output parses as JavaScript.
#
# `typescript` is false by default (ConfigManager::DEFAULT_CONFIG), and then
# every component is a .jsx file (build_command: `@config['typescript'] ?
# '.tsx' : '.jsx'`). A type annotation or an `as` assertion there is not a
# harmless extra: the file does not parse, and the screen does not build.
# Until jsonui-cli 1.9.0 four emit sites wrote them whatever the project was —
# `as React.CSSProperties` on a style holding a CSS custom property (on the
# root and on an inner element), `as React.CSSProperties['x']` on a bound CSS
# value, `as React.ComponentProps<typeof NetworkImage>['contentMode']`, and the
# class-list map's `index: number` — and SelectBox wrote its two casts
# whenever `typescript` was not literally false (a config without the key: its
# components are .jsx too). Measured before the fix: a `rjui build` of every
# conformance layout wrote 20 components that did not parse; one layout at a
# time with the four consumer trees, 45.
#
# THE ARM: every conformance layout, and one layout per emit site, generated
# for a JavaScript project (typescript false, and a config without the key)
# and parsed by esbuild as JSX. THE CONTROLS: each per-site layout writes its
# site's TypeScript for a TypeScript project (so it reaches the site — a
# TypeScript project's whole file fails a JavaScript parse anyway, its props
# interface first, so a parse failure there would prove nothing), and the
# parser rejects a cast and an annotation while it takes the same JSX
# without them.
RSpec.describe 'rjui output for a JavaScript project parses as JavaScript' do
  JS_MODE_ROOT = File.expand_path('../../..', __dir__)

  # One layout per emit site that wrote TypeScript regardless, and the
  # TypeScript that site writes for a TypeScript project.
  JS_MODE_SITES = {
    'a style with a CSS custom property (build_style_attr)' => [{
      'type' => 'Button', 'id' => 'target', 'text' => 'Sample', 'tapBackground' => '@{boundTapBackground}',
      'data' => [{ 'name' => 'boundTapBackground', 'class' => 'String', 'defaultValue' => '#FF0000' }]
    }, '} as React.CSSProperties}'],
    "an inner element's style with a CSS custom property (style_attr_for)" => [{
      'type' => 'Switch', 'id' => 'target', 'isOn' => true, 'tint' => '@{boundTint}',
      'data' => [{ 'name' => 'boundTint', 'class' => 'String', 'defaultValue' => '#FF0000' }]
    }, '} as React.CSSProperties} />'],
    'a bound CSS value (css_assert)' => [{
      'type' => 'Label', 'id' => 'target', 'text' => 'Sample', 'textAlign' => '@{boundTextAlign}',
      'data' => [{ 'name' => 'boundTextAlign', 'class' => 'String', 'defaultValue' => 'Left' }]
    }, "as React.CSSProperties['textAlign']"],
    "a NetworkImage's bound contentMode (under a root: a root NetworkImage is an <img>)" => [{
      'type' => 'View', 'id' => 'root',
      'data' => [{ 'name' => 'boundContentMode', 'class' => 'String', 'defaultValue' => 'fit' }],
      'child' => [{ 'type' => 'NetworkImage', 'id' => 'target', 'width' => 140, 'height' => 80,
                    'defaultImage' => 'conformance_sample', 'contentMode' => '@{boundContentMode}' }]
    }, "as React.ComponentProps<typeof NetworkImage>['contentMode']"],
    "a class-list Collection's declared list (the map's index)" => [{
      'type' => 'View', 'id' => 'root',
      'data' => [{ 'name' => 'rows', 'class' => 'Array' }],
      'child' => [{ 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['row_cell'], 'items' => '@{rows}' }]
    }, 'index: number) =>'],
    "a SelectBox's bound items and index" => [{
      'type' => 'SelectBox', 'id' => 'target', 'items' => '@{options}', 'selectedIndex' => '@{index}',
      'data' => [{ 'name' => 'options', 'class' => 'Array' }, { 'name' => 'index', 'class' => 'Int', 'defaultValue' => 0 }]
    }, ' as string | number | { value?: string | number; id?: string | number } | undefined']
  }.freeze

  before { BundlerDefine.skip_unless_available! }

  def generate(json, config, name)
    $stderr = StringIO.new
    Dir.mktmpdir do |dir|
      Dir.chdir(dir) { RjuiTools::React::ReactGenerator.new(config).generate(name, json) }
    end
  ensure
    $stderr = STDERR
  end

  # { file => first error, with its source line } for every file esbuild does
  # not parse as JSX, or that holds TypeScript syntax JavaScript also parses
  # (a type argument, `f<T>(x)`, reads as two comparisons): such a file
  # transforms differently as TSX than as JSX — imports kept verbatim, so an
  # unused import is not the difference. One node process for the lot.
  def unparsed(sources)
    Dir.mktmpdir do |dir|
      sources.each { |name, code| File.write(File.join(dir, "#{name}.jsx"), code) }
      script = <<~JS
        const fs = require('fs'), path = require('path');
        const esbuild = require(#{JSON.generate(File.join(BundlerDefine::SUPPORT_DIR, 'node_modules', 'esbuild'))});
        const opts = { jsx: 'preserve', charset: 'utf8', tsconfigRaw: { compilerOptions: { verbatimModuleSyntax: true } } };
        const dir = process.argv[1], out = { parsed: 0, failed: {} };
        for (const f of fs.readdirSync(dir).sort()) {
          const src = fs.readFileSync(path.join(dir, f), 'utf8');
          try {
            const js = esbuild.transformSync(src, { ...opts, loader: 'jsx' }).code;
            if (js !== esbuild.transformSync(src, { ...opts, loader: 'tsx' }).code) { out.failed[f] = 'TypeScript syntax (TSX and JSX transforms differ)'; continue; }
            out.parsed++;
          } catch (e) { const m = e.errors && e.errors[0];
            out.failed[f] = m ? `${m.text} — ${m.location ? m.location.lineText.trim().slice(0, 160) : ''}` : String(e); }
        }
        console.log(JSON.stringify(out));
      JS
      stdout, stderr, status = Open3.capture3('node', '-e', script, dir)
      raise "node failed: #{stderr}" unless status.success?

      result = JSON.parse(stdout)
      expect(result['parsed'] + result['failed'].size).to eq(sources.size)
      result['failed']
    end
  end

  let(:javascript) { RjuiTools::Core::ConfigManager::DEFAULT_CONFIG.merge('typescript' => false) }
  let(:no_key) { RjuiTools::Core::ConfigManager::DEFAULT_CONFIG.reject { |key, _| key == 'typescript' } }
  let(:typescript) { RjuiTools::Core::ConfigManager::DEFAULT_CONFIG.merge('typescript' => true) }

  def sites(config)
    JS_MODE_SITES.each_with_index.to_h { |(_, (json, _)), i| ["site#{i}", generate(json, config, "Site#{i}")] }
  end

  it 'every emit site that wrote TypeScript regardless parses, typescript false and typescript absent' do
    { 'typescript: false' => javascript, 'no typescript key' => no_key }.each do |mode, config|
      failed = unparsed(sites(config))
      named = failed.transform_keys { |f| JS_MODE_SITES.keys[f[/\d+/].to_i] }
      expect(named).to be_empty, "#{mode}:\n#{named.map { |site, err| "  #{site}: #{err}" }.join("\n")}"
    end
  end

  # Each layout reaches its site: for a TypeScript project it writes the
  # site's TypeScript, and for a JavaScript project it does not.
  it 'control: each layout reaches its site — its TypeScript is written for a TypeScript project only' do
    ts = sites(typescript)
    js = sites(javascript).merge(sites(no_key).transform_keys { |k| "#{k}-no-key" })
    JS_MODE_SITES.each_with_index do |(site, (_, construct)), i|
      expect(ts["site#{i}"]).to include(construct), "#{site}: the TypeScript project's output lacks #{construct}"
      expect(js["site#{i}"]).not_to include(construct), "#{site}, typescript: false"
      expect(js["site#{i}-no-key"]).not_to include(construct), "#{site}, no typescript key"
    end
  end

  it 'control: the parser rejects what this arm exists to reject, and takes the same JSX without it' do
    failed = unparsed(
      'cast' => "export const A = () => <div style={{ '--c': 'red' } as React.CSSProperties} />;\n",
      'annotation' => "export const B = (rows) => rows.map((item, index: number) => <i key={index} />);\n",
      'typeArgument' => "import { useState } from 'react';\nexport const P = () => { const [d] = useState<PData>(make()); return <div>{d}</div>; };\n",
      'plain' => "import React from 'react';\nimport { unused } from './x';\n" \
                 "export const C = (rows) => rows.map((item, index) => <i key={index} style={{ '--c': 'red' }} />);\n"
    )
    expect(failed.keys.sort).to eq(%w[annotation.jsx cast.jsx typeArgument.jsx])
  end

  # The TypeScript twin keeps what the JavaScript project drops, and still
  # type-checks: the class-list map over a declared `[RowCellData]`.
  describe "the class-list map's TypeScript twin", :typescript_compile do
    def class_list(typescript)
      RjuiTools::React::Converters::CollectionConverter.new(
        { 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['row_cell'], 'items' => '@{rows}' },
        { 'use_tailwind' => true, 'typescript' => typescript, '_data_classes' => { 'rows' => '[RowCellData]' } }
      ).convert
    end

    it 'annotates the item and the index, and type-checks under --strict; the JavaScript one annotates neither' do
      ts = class_list(true)
      expect(ts).to include('(item: RowCellData, index: number) =>')
      expect(class_list(false)).to include('(item, index) =>')
      ambient = <<~TS
        interface RowCellData { readonly title?: string }
        declare const RowCell: (props: { key?: string | number; id?: string; data: RowCellData }) => JSX.Element;
        declare const data: { rows?: RowCellData[] };
      TS
      expect(<<~TSX).to compile_as_typescript.with_ambient(ambient)
        export const Emitted = (): JSX.Element => (
        #{ts}
        );
      TSX
    end
  end

  # The whole project, as the commands write it: `rjui init`, `rjui g view /
  # component / collection`, `rjui build`. A JavaScript project holds no .ts
  # or .tsx file, and every .js / .jsx parses as JavaScript. Until jsonui-cli
  # 1.9.0 (measured on deaead11, typescript false): 12 TypeScript files — the
  # page and ViewModel scaffolds (`g`), the ViewModel bases and hooks `build`
  # derived from them, and the built-ins `init` / `build` copy (NetworkImage,
  # LinkifyText, EmbedContainer, Configuration, useColorMode); with no
  # `typescript` key, 17 (the data models too: `!= false`).
  describe 'the files of a JavaScript project' do
    def project(config_edit)
      Dir.mktmpdir('rjui_js_project') do |dir|
        rjui = File.expand_path('../../bin/rjui', __dir__)
        run = lambda do |*args|
          out, status = Open3.capture2e(RbConfig.ruby, rjui, *args, chdir: dir)
          raise "rjui #{args.join(' ')}: #{out}" unless status.success?
        end
        run.call('init')
        config_path = File.join(dir, 'rjui.config.json')
        File.write(config_path, JSON.pretty_generate(config_edit.call(JSON.parse(File.read(config_path)))))
        run.call('g', 'view', 'home_screen')
        run.call('g', 'component', 'chip_card')
        run.call('g', 'collection', 'item_list')
        run.call('build')
        files = Dir.glob(File.join(dir, '**', '*')).select { |f| File.file?(f) }
        yield files.map { |f| f.sub("#{dir}/", '') }, files.to_h { |f| [f.sub("#{dir}/", ''), File.read(f)] }
      end
    end

    it 'typescript false, and no typescript key: no .ts or .tsx file, and every .js / .jsx parses' do
      { 'typescript: false' => ->(c) { c.merge('typescript' => false) },
        'no typescript key' => ->(c) { c.reject { |k, _| k == 'typescript' } } }.each do |mode, edit|
        project(edit) do |names, contents|
          expect(names.grep(/\.tsx?\z/)).to eq([]), mode
          scripts = contents.select { |name, _| name.match?(/\.jsx?\z/) }
          expect(scripts.size).to be >= 20 # the components, data, view models, hooks and built-ins are there
          failed = unparsed(scripts.transform_keys { |name| name.gsub(/[^A-Za-z0-9]/, '_') })
          expect(failed).to be_empty, "#{mode}:\n#{failed.map { |f, e| "  #{f}: #{e}" }.join("\n")}"
        end
      end
    end

    it 'control: a TypeScript project writes them as TypeScript' do
      project(->(c) { c.merge('typescript' => true) }) do |names, _|
        expect(names).to include('src/viewmodels/HomeScreenViewModel.ts', 'src/app/home-screen/page.tsx',
                                 'src/generated/data/HomeScreenData.ts', 'src/generated/hooks/useColorMode.ts',
                                 'src/components/extensions/NetworkImage.tsx')
      end
    end
  end

  it 'every conformance layout parses, generated for a JavaScript project' do
    layouts = Dir.glob(File.join(JS_MODE_ROOT, 'conformance', 'fixtures', '**', '*.layout.json')).sort
    expect(layouts.size).to be > 1000 # the corpus is there, not an empty glob
    sources = layouts.each_with_index.to_h do |path, i|
      [format('layout%04d', i), generate(JSON.parse(File.read(path)), javascript, "Layout#{i}")]
    end
    expect(sources.values.count { |code| code.is_a?(String) && !code.empty? }).to eq(layouts.size)
    failed = unparsed(sources)
    named = failed.map { |f, err| "  #{layouts[f[/\d+/].to_i].sub("#{JS_MODE_ROOT}/", '')}: #{err}" }
    expect(named).to be_empty, "#{named.size} of #{layouts.size} do not parse:\n#{named.first(20).join("\n")}"
  end
end
