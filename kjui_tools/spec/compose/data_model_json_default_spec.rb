# frozen_string_literal: true

require 'compose/data_model_updater'

# A declared dictionary or array default has to reach Kotlin as a Kotlin
# literal, under a type Kotlin has.
#
# It did neither. Both halves were broken, and they were broken in the same
# line:
#
#     var profile: Object = {"name"=>"Grace", "meta"=>{"age"=>36}}
#                  ^^^^^^   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#                  not a    Ruby's Hash#to_s
#                  Kotlin
#                  type
#
# `TYPE_MAPPING` carried no entry for `Object` / `Hash` / `Array`, so
# `TYPE_MAPPING[base] || base` emitted the declared spelling verbatim; and
# `format_default_value` had no arm for a dictionary, so the Hash was
# interpolated.
#
# ⚠️ The `Map<...>` / `List<...>` arms did exist — and returned
# `emptyMap()` / `emptyList()` on ALL THREE of their branches, so a declared
# dictionary would have been silently emptied even once the type was right.
# That is the same defect the CollectionDataSource arm was fixed for
# ("used to always emit an EMPTY CollectionDataSource(), silently dropping
# declared cells"). Two ways to lose the same data, in adjacent arms.
#
# This is sjui's defect (fixed in d2342ecc) on the Android face — the iceberg
# that memory predicts when one face has a defect. rjui was measured at the
# same time and is clean. What does NOT carry across is the literal spelling:
# `mapOf(k to v)` / `listOf(...)` / `emptyMap()`, not Swift's `[k: v]`.
RSpec.describe 'data model JSON defaults (Kotlin)' do
  let(:updater) { KjuiTools::Compose::DataModelUpdater.allocate }

  def type_for(json_class)
    updater.send(:map_to_kotlin_type, json_class)
  end

  def value_for(value, json_class)
    updater.send(:format_default_value, value, json_class)
  end

  describe 'the declared type' do
    it 'spells the JSON container classes as Kotlin' do
      expect(type_for('Object')).to eq('Map<String, Any?>')
      expect(type_for('Hash')).to eq('Map<String, Any?>')
      expect(type_for('Array')).to eq('List<Any?>')
    end

    it 'uses a NULLABLE value type' do
      # Not `Map<String, Any>`. JSON permits null, and `mapOf("z" to null)`
      # infers a nullable value type that does not satisfy `Map<String, Any>`
      # — "initializer type mismatch", measured with the Kotlin compiler.
      expect(type_for('Object')).to end_with('Any?>')
      expect(type_for('Array')).to end_with('Any?>')
    end

    it 'leaves a project model type exactly as declared' do
      # Control. Only the container spellings name a shape Kotlin has no
      # type for; a project's own class must pass through untouched.
      expect(type_for('MyProfileModel')).to eq('MyProfileModel')
      expect(type_for('String')).to eq('String')
    end
  end

  describe 'the value' do
    it 'emits a nested dictionary as a Kotlin literal' do
      expect(value_for({ 'name' => 'Grace', 'meta' => { 'age' => 36 } }, 'Object'))
        .to eq('mapOf("name" to "Grace", "meta" to mapOf("age" to 36))')
    end

    it 'emits an array of dictionaries' do
      expect(value_for([{ 'title' => 'First' }], 'Array'))
        .to eq('listOf(mapOf("title" to "First"))')
    end

    it 'emits an array of scalars' do
      expect(value_for(%w[alpha beta], 'Array')).to eq('listOf("alpha", "beta")')
    end

    it 'carries the empty forms' do
      # These two were the ONLY thing the old arms could return, for any
      # input. Keeping them here means the fix cannot regress into them
      # without the examples above going red first.
      expect(value_for({}, 'Object')).to eq('emptyMap()')
      expect(value_for([], 'Array')).to eq('emptyList()')
    end

    it 'emits numbers, booleans and null' do
      expect(value_for({ 'n' => 1, 'f' => 2.5, 'b' => true, 'z' => nil }, 'Object'))
        .to eq('mapOf("n" to 1, "f" to 2.5, "b" to true, "z" to null)')
    end

    it 'escapes quotes, backslashes and the template dollar' do
      # `$` matters in Kotlin and not in Swift: an unescaped `$name` inside a
      # string is a template expansion, so declared data containing a price
      # or a shell-ish token either fails to compile or silently interpolates
      # something else.
      expect(value_for({ 'a"b' => 'c\\d', 'price' => '$100' }, 'Object'))
        .to eq('mapOf("a\\"b" to "c\\\\d", "price" to "\\$100")')
    end

    it 'leaves CollectionDataSource on its own constructor path' do
      # Control: the arm above this one in the case statement, which already
      # had this defect and was already fixed. Rerouting it would undo that.
      out = value_for([{ 'title' => 'Alpha' }], 'CollectionDataSource')
      expect(out).to include('CollectionDataSource(')
    end
  end

  describe 'the generated model compiles', :kotlin_compile do
    # The gate the unit examples cannot be, and the one this face did not
    # have: `dev-guide/release/compile-emitted-kotlin.sh` covers only the
    # branch-test runtime, so nothing ever compiled the data model. Every
    # broken form above was emitted by code whose specs were green.
    it 'accepts every declared container shape' do
      props = [
        ['profile', { 'name' => 'Grace', 'meta' => { 'age' => 36 } }, 'Object'],
        ['rows',    [{ 'title' => 'First' }, { 'title' => 'Second' }], 'Array'],
        ['tags',    %w[alpha beta], 'Array'],
        ['blank',   {}, 'Object'],
        ['none',    [], 'Array'],
        ['mixed',   { 'n' => 1, 'f' => 2.5, 'b' => true, 'z' => nil }, 'Object'],
        ['escaped', { 'a"b' => 'c\\d', 'price' => '$100' }, 'Object'],
        ['nulls',   [1, nil], 'Array']
      ]
      body = props.map do |name, value, klass|
        "    var #{name}: #{type_for(klass)} = #{value_for(value, klass)}"
      end.join(",\n")

      expect(<<~KOTLIN).to compile_as_kotlin
        data class TestData(
        #{body}
        )
      KOTLIN
    end
  end
end
