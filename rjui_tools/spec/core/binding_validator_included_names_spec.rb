# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require_relative '../../lib/core/binding_validator'

# The names a layout's includes bring into the screen's Data count as defined (ticket
# jui-shared-data-binding-ignores-names-from-included-partial). An include without an id brings its partial's data
# names as they are; a second include of the same partial, with an id, may bind them through shared_data — the screen's
# Data has them on every face, and the generated include reads them. The check read the layout as written and called
# each "not defined in data" (12 screens × 6 names in one consumer). The build hands the validator the layouts root and
# the include-expanded tree is read as the Data is built from it. This file is the same on sjui, kjui and rjui
# (shared/core).
RSpec.describe RjuiTools::Core::BindingValidator, '(names an include brings in are defined)' do
  subject(:validator) { described_class.new }

  # A method, not a constant: a constant in a spec file is a top-level one (spec_constants_are_scoped_spec).
  def names
    %w[pagerVisibility pagerSummaryText pagerPrevEnabled onPagerPrevTap]
  end

  around do |example|
    Dir.mktmpdir do |dir|
      @root = dir
      FileUtils.mkdir_p(File.join(dir, 'common'))
      File.write(File.join(dir, 'common', 'pager.json'), JSON.generate({
        'type' => 'View', 'visibility' => '@{pagerVisibility}',
        'data' => [{ 'name' => 'pagerVisibility', 'class' => 'String' }, { 'name' => 'pagerSummaryText', 'class' => 'String' },
                   { 'name' => 'pagerPrevEnabled', 'class' => 'Bool' }, { 'name' => 'onPagerPrevTap', 'class' => '(() -> Void)?' }],
        'child' => [{ 'type' => 'Label', 'id' => 'summary', 'text' => '@{pagerSummaryText}' }]
      }))
      File.write(File.join(dir, 'common', 'wrap.json'), JSON.generate({ 'type' => 'View', 'child' => [{ 'include' => 'common/pager' }] }))
      example.run
    end
  end

  let(:shared) { names.to_h { |n| [n, "@{#{n}}"] } }
  let(:with_id) { { 'include' => 'common/pager', 'id' => 'pager_top', 'shared_data' => shared } }

  def screen(*children, data: nil)
    root = { 'type' => 'View', 'id' => 'screen', 'child' => children }
    root['data'] = data if data
    root
  end

  def undefined(warnings)
    warnings.select { |w| w.include?('is not defined in data') }
  end

  it 'counts the names an include without an id brings, for a second include of the same partial' do
    expect(undefined(validator.validate(screen({ 'include' => 'common/pager' }, with_id), 's.json', @root))).to eq([])
  end

  it 'counts them whichever include comes first' do
    expect(undefined(validator.validate(screen(with_id, { 'include' => 'common/pager' }), 's.json', @root))).to eq([])
  end

  it 'counts them through a nested include' do
    expect(undefined(validator.validate(screen({ 'include' => 'common/wrap' }, with_id), 's.json', @root))).to eq([])
  end

  it "counts them for the screen's own bindings" do
    label = { 'type' => 'Label', 'id' => 'echo', 'text' => '@{pagerSummaryText}' }
    expect(undefined(validator.validate(screen({ 'include' => 'common/pager' }, label, data: []), 's.json', @root))).to eq([])
  end

  it 'counts the names an include with an id brings, as the Data spells them' do
    label = { 'type' => 'Label', 'id' => 'echo', 'text' => '@{pagerTopPagerSummaryText}' }
    expect(undefined(validator.validate(screen(with_id, label, data: names.map { |n| { 'name' => n, 'class' => 'String' } }),
                                        's.json', @root))).to eq([])
  end

  it 'still warns where no include brings the names (the Data has none of them)' do
    warnings = undefined(validator.validate(screen(with_id), 's.json', @root))
    expect(warnings.size).to eq(4)
    expect(warnings.first).to include("Binding variable 'pagerVisibility' in 'include:common/pager.shared_data.pagerVisibility'")
  end

  it "does not report the partial's names as this layout's unused data" do
    warnings = validator.validate(screen({ 'include' => 'common/pager' }, data: [{ 'name' => 'own', 'class' => 'String' }]), 's.json', @root)
    expect(warnings.grep(/never used/)).to eq(["[s.json] Data property 'own' is defined but never used in bindings, shared_data, or data."])
  end

  # The validator counts them only when handed the layouts root, so every build call hands it: read from the source,
  # as this tool's build is not run here (the probe project of the ticket ran jui build on all three faces).
  it "is handed the layouts root by every binding check of this tool's build" do
    build = Dir[File.expand_path('../../lib/cli/commands/build{,_command}.rb', __dir__)].first
    calls = File.read(build).scan(/binding_validator\.validate\([^\n]*\)/)
    expect(calls).not_to be_empty
    expect(calls).to all(match(/layouts_dir\)+\z/))
  end

  it 'reads the layout as written without a layouts root, or when an include cannot be expanded' do
    layout = screen({ 'include' => 'common/pager' }, with_id)
    expect(undefined(validator.validate(layout, 's.json')).size).to eq(4)
    missing = screen({ 'include' => 'common/nowhere' }, with_id)
    expect(undefined(validator.validate(missing, 's.json', @root)).size).to eq(4)
  end
end
