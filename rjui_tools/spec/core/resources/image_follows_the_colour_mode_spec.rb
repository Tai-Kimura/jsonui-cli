# frozen_string_literal: true

require 'tmpdir'
require 'json'
require 'fileutils'
require_relative '../../../lib/core/resources/color_manager'
require_relative '../../../lib/core/logger'
require_relative '../../../lib/react/converters/image_converter'
require_relative '../../../lib/react/converters/button_converter'
require_relative '../../../lib/react/converters/select_box_converter'
require_relative '../../support/typescript_compiler'

# An image could not follow the colour mode: jui build copied one <name>.svg
# and nothing chose another (ticket jui-images-no-per-color-mode-variants). Now
# <name>.<mode>.svg is copied beside it, jui build writes image_modes.json
# beside colors.json, and the page draws the mode's picture by CSS, by the
# rule a colour follows: theme.css binds --image-<name> under :root,
# :root[data-theme=…] and the OS's dark, a chosen mode's <style> binds it under
# :root:root:root, and an <img> keeps its src and takes
# content: var(--image-<name>). Measured in Chromium, WebKit and Firefox on the
# ticket's probe page; here, what is written.
RSpec.describe 'an image follows the colour mode (web)' do
  let(:temp_dir) { Dir.mktmpdir('image_modes') }
  let(:resources_dir) { File.join(temp_dir, 'Resources') }
  let(:generated) { File.join(temp_dir, 'src', 'generated') }
  let(:table) { { 'version' => 1, 'images' => { 'ic_probe' => { 'dark' => 'ic_probe__dark', 'sepia' => 'ic_probe__sepia' } } } }
  let(:config) { { 'generated_directory' => 'src/generated' } }

  before do
    FileUtils.mkdir_p(resources_dir)
    File.write(File.join(resources_dir, 'colors.json'), JSON.generate(
      'modes' => %w[light dark sepia], 'fallback_mode' => 'light', 'systemModeMapping' => { 'light' => 'light', 'dark' => 'dark' },
      'light' => { 'surface' => '#FFFFFF' }, 'dark' => { 'surface' => '#202020' }, 'sepia' => { 'surface' => '#F3E7D3' }
    ))
    allow(RjuiTools::React::ImageModes).to receive(:table_path).and_return(File.join(resources_dir, 'image_modes.json'))
    allow(RjuiTools::Core::Logger).to receive(:info)
  end
  after { FileUtils.rm_rf(temp_dir) }

  def with_table
    File.write(File.join(resources_dir, 'image_modes.json'), JSON.generate(table))
  end

  def manager
    dummy = File.join(temp_dir, 'dummy.json')
    File.write(dummy, JSON.generate('type' => 'View'))
    RjuiTools::Core::Resources::ColorManager.new(config, temp_dir, resources_dir).tap do |m|
      m.process_colors([dummy], 1, 0, config)
    end
  end

  def theme_css
    manager
    File.read(File.join(generated, 'theme.css'))
  end

  def convert(klass, json)
    klass.new(json, config.dup).convert
  end

  it 'writes nothing new for a project without a mode picture' do
    expect(theme_css).not_to include('--image-')
    expect(manager.mode_css('dark')).not_to include('--image-')
    expect(convert(RjuiTools::React::Converters::ImageConverter, 'type' => 'Image', 'srcName' => 'ic_probe')).not_to include('content')
  end

  it "binds each mode's picture under the selectors the colours use, and the base's own picture in a mode without one" do
    with_table
    css = theme_css
    root = css.scan(/^:root \{\n(.*?)\n\}/m).flatten.join("\n")
    expect(root).to include('--image-ic_probe:url("/images/ic_probe.svg")')
    # Its own blocks, after the colours' (theme.css may hold one rule per selector for each).
    blocks = ->(selector) { css.scan(/^#{Regexp.escape(selector)} \{\n(.*?)\n\}/m).flatten.join("\n") }
    expect(blocks.(':root[data-theme="dark"]')).to include('--image-ic_probe:url("/images/ic_probe.dark.svg")')
    expect(blocks.(':root[data-theme="sepia"]')).to include('--image-ic_probe:url("/images/ic_probe.sepia.svg")')
    expect(css.scan(/@media \(prefers-color-scheme: dark\) \{\n  :root:not\(\[data-theme\]\) \{\n(.*?)\n  \}/m).flatten.join("\n"))
      .to include('--image-ic_probe:url("/images/ic_probe.dark.svg")')
    m = manager
    expect(m.mode_css('sepia')).to start_with(':root:root:root{').and include('--image-ic_probe:url("/images/ic_probe.sepia.svg")')
    expect(m.mode_css('light')).to include('--image-ic_probe:url("/images/ic_probe.svg")')
  end

  it "draws an <img> with a mode's picture through content, and leaves any other <img> as it was" do
    with_table
    img = ->(json) { convert(RjuiTools::React::Converters::ImageConverter, { 'type' => 'Image' }.merge(json)) }
    expect(img.('srcName' => 'ic_probe')).to include("style={{ content: 'var(--image-ic_probe)' }}").and include('src="/images/ic_probe.svg"')
    expect(img.('srcName' => '@{icon}')).to include("content: `var(--image-${String(data.icon).replace(/\\.svg$/, '')})`")
    expect(img.('srcName' => 'ic_plain')).not_to include('content')
  end

  it "reads a Button's icon and a SelectBox's caret from the mode's variable, with the picture as the fallback" do
    with_table
    plain = convert(RjuiTools::React::Converters::ButtonConverter, 'type' => 'Button', 'image' => 'ic_probe')
    expect(plain).to include("style={{ content: 'var(--image-ic_probe)' }}")
    tinted = convert(RjuiTools::React::Converters::ButtonConverter, 'type' => 'Button', 'image' => 'ic_probe', 'tintColor' => '#FF0000')
    expect(tinted).to include('maskImage: `var(--image-ic_probe, url(/images/ic_probe.svg))`')
    other = convert(RjuiTools::React::Converters::ButtonConverter, 'type' => 'Button', 'image' => 'ic_plain', 'tintColor' => '#FF0000')
    expect(other).to include('maskImage: `url(/images/ic_plain.svg)`')
    select = convert(RjuiTools::React::Converters::SelectBoxConverter,
                     'type' => 'SelectBox', 'id' => 's', 'items' => %w[a b], 'caretAttributes' => { 'src' => 'ic_probe' })
    expect(select).to include('var(--image-ic_probe, url("/images/ic_probe.svg"))')
  end

  it 'the emit compiles as TypeScript', :typescript_compile do
    with_table
    cfg = config.merge('typescript' => true)
    elements = [
      RjuiTools::React::Converters::ImageConverter.new({ 'type' => 'Image', 'id' => 'a', 'srcName' => 'ic_probe' }, cfg.dup).convert,
      RjuiTools::React::Converters::ImageConverter.new({ 'type' => 'Image', 'id' => 'b', 'srcName' => '@{icon}' }, cfg.dup).convert,
      RjuiTools::React::Converters::ButtonConverter.new({ 'type' => 'Button', 'id' => 'c', 'image' => 'ic_probe' }, cfg.dup).convert,
      RjuiTools::React::Converters::ButtonConverter.new({ 'type' => 'Button', 'id' => 'd', 'image' => 'ic_probe', 'tintColor' => '#FF0000' }, cfg.dup).convert
    ]
    expect(elements.join).to include("content: 'var(--image-ic_probe)'", 'maskImage: `var(--image-ic_probe')
    expect("declare const data: { icon: string };\n#{TypeScriptCompiler.component(*elements)}").to compile_as_typescript
  end
end
