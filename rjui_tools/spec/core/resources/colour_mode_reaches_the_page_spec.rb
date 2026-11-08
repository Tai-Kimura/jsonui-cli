# frozen_string_literal: true

require 'tmpdir'
require 'json'
require 'fileutils'
require 'open3'
require_relative '../../../lib/core/resources/color_manager'
require_relative '../../../lib/core/logger'
require_relative '../../support/typescript_compiler'

# A colors.json with a dark mode did not reach the page. theme.css rebinds the
# colours under `:root[data-theme="dark"]`, and nothing wrote data-theme:
# ColorManager.setMode changed its own mode only, so every class colour stayed
# light whatever the OS or the user chose, while a bound colour took the mode
# at its render and was not drawn again (getComputedStyle in Chromium, ticket
# rjui-color-mode-never-sets-data-theme). Now theme.css follows the OS itself,
# and a mode chosen against it is a <style> in <head> holding that mode's
# variables — not an attribute on <html>, which React renders and which made a
# Next.js page report a hydration mismatch. Measured on the generated module run
# in node, against a stand-in window, document, localStorage and matchMedia.
RSpec.describe 'the colour mode reaches the page (web)' do
  let(:temp_dir) { Dir.mktmpdir('colour_mode') }
  let(:resources_dir) { File.join(temp_dir, 'Resources') }
  let(:generated) { File.join(temp_dir, 'src', 'generated') }

  before { FileUtils.mkdir_p(resources_dir) }
  after { FileUtils.rm_rf(temp_dir) }

  def build(typescript: false)
    File.write(File.join(resources_dir, 'colors.json'), JSON.generate(
      'modes' => %w[light dark], 'fallback_mode' => 'light', 'systemModeMapping' => { 'light' => 'light', 'dark' => 'dark' },
      'light' => { 'surface' => '#FFFFFF', 'ink' => '#111111' }, 'dark' => { 'surface' => '#202020', 'ink' => '#EEEEEE' }
    ))
    dummy = File.join(temp_dir, 'dummy.json')
    File.write(dummy, JSON.generate('type' => 'View'))
    cfg = { 'generated_directory' => 'src/generated', 'typescript' => typescript }
    RjuiTools::Core::Resources::ColorManager.new(cfg, temp_dir, resources_dir).process_colors([dummy], 1, 0, cfg)
  end

  # The steps run against the generated ColorManager.js; each returns the
  # mode, the <html data-theme> and the kept choice.
  def run_in_node(steps)
    module_path = File.join(temp_dir, 'cm.mjs')
    FileUtils.cp(File.join(generated, 'ColorManager.js'), module_path)
    script = <<~JS
      const store = {}; let dark = false; const listeners = []; const attrs = {}; const head = [];
      globalThis.window = {
        localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
        matchMedia: () => ({ get matches() { return dark; }, addEventListener: (_, cb) => listeners.push(cb) }),
      };
      globalThis.document = {
        documentElement: { setAttribute: (k, v) => { attrs[k] = v; }, getAttribute: (k) => attrs[k] },
        head: { appendChild: (el) => { head.push(el); } },
        createElement: (tag) => ({ tag, id: '', textContent: '', remove() { head.splice(head.indexOf(this), 1); } }),
        getElementById: (id) => head.find((el) => el.id === id) || null,
      };
      const os = (d) => { dark = d; listeners.forEach((cb) => cb()); };
      const out = [];
      // what draws: the <style> a chosen mode put in <head>, else what theme.css draws for the OS
      const drawn = () => { const el = head.find((e) => e.id === 'jsonui-color-mode');
        return el ? (el.textContent.includes('#202020') ? 'dark' : 'light') : (dark ? 'dark' : 'light'); };
      const snap = (cm, label) => out.push({ label, mode: cm.currentMode, theme: drawn(), html: attrs['data-theme'] ?? null, kept: store['jsonui-color-mode'] ?? null });
      const fresh = async (n) => (await import(#{module_path.to_json} + '?' + n)).ColorManager;
      #{steps}
      console.log(JSON.stringify(out));
    JS
    js = File.join(temp_dir, 'run.mjs')
    File.write(js, script)
    stdout, stderr, status = Open3.capture3('node', js)
    raise "node failed: #{stderr}" unless status.success?

    JSON.parse(stdout.lines.last)
  end

  it 'draws the OS mode at load and follows the OS, writing nothing on <html>' do
    build
    out = run_in_node(<<~JS)
      let cm = await fresh(1); snap(cm, 'load, light OS');
      os(true); snap(cm, 'the OS turns dark');
      os(false); snap(cm, 'and light again');
    JS
    expect(out.map { |o| [o['mode'], o['theme'], o['html']] }).to eq([['light', 'light', nil], ['dark', 'dark', nil], ['light', 'light', nil]])
  end

  it 'takes an explicit setMode over the OS, keeps it, and goes back to the OS on followSystemMode' do
    build
    out = run_in_node(<<~JS)
      let cm = await fresh(2);
      cm.setMode('dark'); snap(cm, 'chose dark');
      os(true); os(false); snap(cm, 'the OS moves');
      cm.setMode('light'); os(true); snap(cm, 'chose light, the OS turns dark');
      cm.followSystemMode = true; snap(cm, 'back to the OS');
      os(false); snap(cm, 'the OS turns light');
    JS
    expect(out.map { |o| [o['mode'], o['theme'], o['kept']] }).to eq(
      [%w[dark dark dark], %w[dark dark dark], %w[light light light], %w[dark dark system], %w[light light system]]
    )
  end

  it 'a kept choice wins over the OS at the next load' do
    build
    out = run_in_node(<<~JS)
      let cm = await fresh(3); cm.setMode('dark');
      os(false);
      let next = await fresh(4); snap(next, 'next load, light OS');
    JS
    expect(out.first.values_at('mode', 'theme')).to eq(%w[dark dark])
  end

  it 'cssColor hands a theme name to CSS as its variable, anything else as resolveColor does' do
    build
    out = run_in_node(<<~JS)
      let cm = await fresh(5); cm.setMode('dark');
      out.push({ v: cm.cssColor('surface') }, { v: cm.cssColor('#ABCDEF') }, { v: cm.cssColor('@{x}') ?? null }, { v: cm.resolveColor('surface') });
    JS
    expect(out.map { |o| o['v'] }).to eq(['var(--color-surface)', '#ABCDEF', nil, '#202020'])
  end

  # What is no theme name is what resolveColor gives, untouched by cssColor:
  # a hex as written (an 8-digit one reordered for CSS), a CSS colour name, a
  # name outside the palette, and a name some mode lacks (no variable for it).
  # The handwritten readers keep their hex: color(), resolveColor() and the
  # accessors still answer the current mode's value.
  it 'leaves what is no theme name, and the handwritten readers, as they were' do
    File.write(File.join(resources_dir, 'colors.json'), JSON.generate(
      'modes' => %w[light dark], 'fallback_mode' => 'light', 'systemModeMapping' => { 'light' => 'light', 'dark' => 'dark' },
      'light' => { 'surface' => '#FFFFFF', 'only_light' => '#ABCDEF' }, 'dark' => { 'surface' => '#202020' }
    ))
    dummy = File.join(temp_dir, 'dummy.json')
    File.write(dummy, JSON.generate('type' => 'View'))
    cfg = { 'generated_directory' => 'src/generated', 'typescript' => false }
    RjuiTools::Core::Resources::ColorManager.new(cfg, temp_dir, resources_dir).process_colors([dummy], 1, 0, cfg)
    out = run_in_node(<<~JS)
      let cm = await fresh(9); cm.setMode('dark');
      for (const v of ['#123456', '#80FF0000', 'red', 'brand_unknown', 'only_light']) out.push({ v: cm.cssColor(v) });
      out.push({ v: cm.color('surface') }, { v: cm.resolveColor('surface') }, { v: cm.surface });
    JS
    expect(out.map { |o| o['v'] }).to eq(['#123456', '#FF000080', 'red', 'brand_unknown', '#ABCDEF', '#202020', '#202020', '#202020'])
  end

  it 'theme.css emits every colour variable and answers the OS before any script' do
    build
    css = File.read(File.join(generated, 'theme.css'))
    expect(css).to include('@theme static {')
    expect(css).to include(":root[data-theme=\"dark\"] {\n  --color-ink: #EEEEEE;")
    expect(css).to match(/@media \(prefers-color-scheme: dark\) \{\n  :root:not\(\[data-theme\]\) \{\n    --color-ink: #EEEEEE;\n    --color-surface: #202020;\n  \}\n\}/)
  end

  it 'colorModeScript puts the kept choice in <head> before the first paint, and nothing on <html>' do
    build
    src = File.read(File.join(generated, 'colorModeScript.js'))
    body = JSON.parse(src[/colorModeScript = (".*");/, 1])
    out = run_in_node(<<~JS)
      store['jsonui-color-mode'] = 'dark';
      #{body}
      out.push({ theme: drawn(), html: attrs['data-theme'] ?? null, css: head[0] && head[0].textContent });
    JS
    expect(out.first.values_at('theme', 'html')).to eq(['dark', nil])
    # the browser's own parts take the mode's color-scheme in the same rule
    expect(out.first['css']).to eq(':root:root:root{--color-ink:#EEEEEE;--color-surface:#202020;color-scheme:dark}')
  end

  it 'the TypeScript faces compile', :typescript_compile do
    build(typescript: true)
    expect(File.read(File.join(generated, 'ColorManager.ts'))).to compile_as_typescript
    expect(File.read(File.join(generated, 'colorModeScript.ts'))).to compile_as_typescript
  end
end
