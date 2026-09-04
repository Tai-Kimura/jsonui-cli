# frozen_string_literal: true

require 'swiftui/data_model_updater'

# A declared dictionary or array default has to reach Swift as a Swift literal.
#
# It did not. `format_default_value` handled `String` and `CollectionDataSource`
# and returned everything else untouched, so a Ruby Hash was interpolated
# straight into the generated model:
#
#     var conformanceProfile: Object = {"name"=>"Grace", "meta"=>{"age"=>36}}
#
# Two things wrong in one line. `Object` is not a Swift type — class names were
# emitted verbatim — and `Hash#to_s` is not a Swift literal. The file did not
# compile, so nothing downstream of it ran.
#
# It survived because no fixture declaring one had ever been through a
# compiler: all three are `interactive`, and the codegen host excluded that
# class wholesale until the staging predicate changed to "needs a driver".
# The first run under the new predicate failed at build with exit 65 — which
# is the point of hosting them.
#
# ⚠️ What decides is the SHAPE of the value, not the declared class. Measured
# across the corpus: 77 fixtures declare a dict/list default, and the ones that
# compiled did so for two different reasons —
#
#     CollectionDataSource (72)  a correct emitter it already had
#     Array of scalars      (1)  `["alpha", "beta"].to_s` happens to READ as
#                                Swift — the same broken path, passing by
#                                coincidence
#
# so fixing only the dict case would leave arrays on the accidental path, with
# the scalar array unable to report a regression in it. Every container goes
# through the emitter now.
RSpec.describe 'data model JSON defaults' do
  let(:updater) { SjuiTools::SwiftUI::DataModelUpdater.allocate }

  def type_for(json_class)
    updater.send(:swift_data_type, json_class)
  end

  def value_for(value, json_class)
    updater.send(:format_default_value, value, json_class)
  end

  describe 'the declared type' do
    it 'spells the JSON container classes as Swift' do
      expect(type_for('Object')).to eq('[String: Any]')
      expect(type_for('Hash')).to eq('[String: Any]')
      expect(type_for('Array')).to eq('[Any]')
    end

    it 'keeps an optional marker' do
      expect(type_for('Object?')).to eq('[String: Any]?')
    end

    it 'leaves a project model type exactly as declared' do
      # Control. Class names are the project's own types; only the container
      # spellings name a shape with no Swift equivalent.
      expect(type_for('MyProfileModel')).to eq('MyProfileModel')
      expect(type_for('CollectionDataSource')).to eq('CollectionDataSource')
    end
  end

  describe 'the value' do
    it 'emits a nested dictionary as a Swift literal' do
      expect(value_for({ 'name' => 'Grace', 'meta' => { 'age' => 36 } }, 'Object'))
        .to eq('["name": "Grace", "meta": ["age": 36]]')
    end

    it 'emits an array of dictionaries' do
      expect(value_for([{ 'title' => 'First' }], 'Array'))
        .to eq('[["title": "First"]]')
    end

    it 'emits an array of scalars through the same path' do
      # This one passed before the fix, by coincidence — Array#to_s reads as a
      # Swift literal for scalars. Pinning it here means the coincidence is
      # now a route: if the emitter breaks, this fails with everything else
      # instead of staying green and hiding it.
      expect(value_for(%w[alpha beta], 'Array')).to eq('["alpha", "beta"]')
    end

    it 'carries the empty forms' do
      expect(value_for({}, 'Object')).to eq('[:]')
      expect(value_for([], 'Array')).to eq('[]')
    end

    it 'emits numbers, booleans and null unquoted' do
      expect(value_for({ 'n' => 1, 'f' => 2.5, 'b' => true, 'z' => nil }, 'Object'))
        .to eq('["n": 1, "f": 2.5, "b": true, "z": nil]')
    end

    it 'escapes quotes and backslashes' do
      # gsub's STRING replacement reads a backslash pair as a back-reference,
      # so the obvious spelling emitted one backslash where two were meant and
      # produced an invalid Swift escape. Caught by this example while writing
      # it, which is why the emitter uses block replacements.
      expect(value_for({ 'a"b' => 'c\\d' }, 'Object'))
        .to eq('["a\\"b": "c\\\\d"]')
    end

    it 'leaves CollectionDataSource on its own initializer path' do
      # Control: 72 fixtures depend on that shape and must not be rerouted.
      out = value_for([{ 'title' => 'Alpha' }], 'CollectionDataSource')
      expect(out).to start_with('CollectionDataSource(')
    end
  end

  describe 'the generated model compiles', :swift_compile do
    # The gate the unit examples cannot be: every failed candidate above
    # emitted *something*, and only a compiler says whether it is Swift.
    it 'accepts every declared container shape' do
      props = [
        { 'name' => 'profile',  'class' => 'Object',
          'defaultValue' => { 'name' => 'Grace', 'meta' => { 'age' => 36 } } },
        { 'name' => 'rows',     'class' => 'Array',
          'defaultValue' => [{ 'title' => 'First' }, { 'title' => 'Second' }] },
        { 'name' => 'tags',     'class' => 'Array',  'defaultValue' => %w[alpha beta] },
        { 'name' => 'blank',    'class' => 'Object', 'defaultValue' => {} },
        { 'name' => 'none',     'class' => 'Array',  'defaultValue' => [] },
        { 'name' => 'mixed',    'class' => 'Object',
          'defaultValue' => { 'n' => 1, 'f' => 2.5, 'b' => true, 's' => 'x' } },
        { 'name' => 'escaped',  'class' => 'Object',
          'defaultValue' => { 'a"b' => 'c\\d' } }
      ]
      body = props.map do |p|
        "    var #{p['name']}: #{type_for(p['class'])} = " \
          "#{value_for(p['defaultValue'], p['class'])}"
      end.join("\n")

      expect(<<~SWIFT).to compile_as_swift
        struct TestData {
        #{body}
        }
      SWIFT
    end
  end
end
