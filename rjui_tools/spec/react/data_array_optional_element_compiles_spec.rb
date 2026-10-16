# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'stringio'

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/data_model_generator'

# A data item whose class is an array of optional elements — `[Double?]`,
# `[[Double?]]`, `Array(Int?)` — is written into the Data type with the
# element in parentheses: `(number | undefined)[]`. Through 1.9.33 rjui wrote
# `number | undefined[]`, which TypeScript reads as "a number, or an array of
# undefined": no array holding a value was assignable (TS2322 / TS2345), so a
# screen declaring one did not compile. The type is rendered in one place
# (Core::TypeConverter.to_typescript_type); this arm reads it in the file the
# build writes, under tsc --strict, with values assigned.
RSpec.describe 'a data array of optional elements (rjui)' do
  let(:dir) { Dir.mktmpdir('data_array_optional_element') }

  before do
    %w[Layouts Data Styles].each { |d| FileUtils.mkdir_p(File.join(dir, d)) }
    allow(RjuiTools::Core::ConfigManager).to receive(:load_config).and_return(
      'source_path' => dir, 'layouts_directory' => 'Layouts', 'data_directory' => 'Data',
      'styles_directory' => 'Styles', 'typescript' => true
    )
    File.write(File.join(dir, 'Layouts', 'grid.json'), JSON.generate(
      'type' => 'View', 'id' => 'root',
      'data' => [
        { 'name' => 'cells', 'class' => '[[Double?]]' },
        { 'name' => 'totals', 'class' => '[Double?]' },
        { 'name' => 'counts', 'class' => 'Array(Int?)' },
        { 'name' => 'actions', 'class' => '[(() -> Void)?]' }
      ],
      'child' => [{ 'type' => 'Label', 'id' => 'l', 'text' => 'x' }]
    ))
  end

  after { FileUtils.rm_rf(dir) }

  def data_file
    $stdout = StringIO.new
    RjuiTools::React::DataModelGenerator.new.send(:process_json_file, File.join(dir, 'Layouts', 'grid.json'))
    File.read(File.join(dir, 'Data', 'GridData.ts'))
  ensure
    $stdout = STDOUT
  end

  # Values a consumer's ViewModel hands the screen: an element present and
  # an element absent, in each declared array.
  ASSIGNMENTS = <<~TS
    const assigned: Partial<GridData> = {
      cells: [[1, undefined], [2.5]],
      totals: [1, undefined],
      counts: [3, undefined],
      actions: [() => {}, undefined],
    };
    export { assigned };
  TS

  it 'writes the element in parentheses' do
    data = data_file

    expect(data).to include('cells?: (number | undefined)[][];', 'totals?: (number | undefined)[];',
                            'counts?: (number | undefined)[];', 'actions?: ((() => void) | undefined)[];')
  end

  it 'compiles with values assigned', :typescript_compile do
    expect("#{data_file}\n#{ASSIGNMENTS}").to compile_as_typescript
  end

  # The compiler's own control: the spelling rjui wrote through 1.9.33 is
  # what tsc rejects, so the arm above reads the parentheses and not a
  # lenient tsc.
  it 'would not compile without the parentheses', :typescript_compile do
    unparenthesized = data_file.gsub('(number | undefined)', 'number | undefined')
    expect(unparenthesized).to include('cells?: number | undefined[][];')
    expect("#{unparenthesized}\n#{ASSIGNMENTS}").not_to compile_as_typescript
  end
end
