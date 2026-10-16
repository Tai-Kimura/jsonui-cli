# frozen_string_literal: true

module KjuiTools
  module Compose
    # The test bridge (jsonui-test-runner spec section 10.3-10.4) in the
    # generated Kotlin: the Data class's `testDeclaredClasses`,
    # `applyTestInitialState(values, update)` and `testSnapshot()`, and the
    # GeneratedView's `rememberTestBridge` call that hands its JSON to the
    # screen marker.
    #
    # Whether a value fits its class is decided at run time by KotlinJsonUI's
    # JsonUITestValue.check, the one place that judges it, with the class as
    # the layout spells it (`declaredClass`). This file only writes the calls
    # and, for a Color field, the step that resolves an accepted spelling into
    # the colour the Data holds — so nothing here can make a value fit.
    module TestBridgeCode
      MIN_LIBRARY_VERSION = '2.44.0'

      COLOR_SPELLINGS = %w[Color color].freeze

      module_function

      # Whether a declared class is a Color, or a typed list of them: the
      # fields whose accepted spelling still has to be resolved.
      def color?(declared_class)
        base = declared_class.to_s.strip.sub(/\?\z/, '')
        element = base[/\AArray\((.+)\)\z/, 1] || base[/\AList<(.+)>\z/, 1] ||
                  (base.start_with?('[') && base.end_with?(']') && !base.include?(':') ? base[1...-1] : nil)
        COLOR_SPELLINGS.include?(base) || COLOR_SPELLINGS.include?(element.to_s.strip)
      end

      def kotlin_string(text)
        "\"#{text.to_s.gsub('\\', '\\\\\\\\').gsub('"', '\\"').gsub('$', '\\$')}\""
      end

      # props: [{ name:, declared: }] — the layout's declared Data fields, the
      # class as written. A field the generator adds by itself (`<id>IsFocused`)
      # is not one: an initialState names it as `not a data field`, which is
      # what validate says too (shared/core/layout_data_fields_vectors.json).
      def companion_members(props)
        lines = []
        lines << ''
        lines << '        // The class each Data field is declared with, as the layout spells it: what'
        lines << '        // the test bridge judges an initialState value by (jsonui-test-runner spec 10.3).'
        lines << "        // Requires KotlinJsonUI >= #{MIN_LIBRARY_VERSION} (test bridge)"
        if props.empty?
          lines << '        val testDeclaredClasses: Map<String, String> = emptyMap()'
        else
          lines << '        val testDeclaredClasses: Map<String, String> = mapOf('
          props.each_with_index do |prop, index|
            comma = index < props.length - 1 ? ',' : ''
            lines << "            #{kotlin_string(prop[:name])} to #{kotlin_string(prop[:declared])}#{comma}"
          end
          lines << '        )'
        end
        lines.join("\n") + "\n"
      end

      def member_functions(props)
        colors = props.select { |prop| color?(prop[:declared]) }
        lines = []
        lines << ''
        lines << '    // UI test initialState (jsonui-test-runner spec section 10.3): each value is judged by'
        lines << '    // JsonUITestValue.check against testDeclaredClasses, the accepted ones go to `update`'
        lines << '    // (the ViewModel\'s updateData) in one call, the rest come back with the reason.'
        lines << "    // Requires KotlinJsonUI >= #{MIN_LIBRARY_VERSION} (test bridge)"
        lines << '    fun applyTestInitialState(values: Map<String, Any?>, update: ((Map<String, Any?>) -> Unit)?): List<com.kotlinjsonui.core.RejectedKey> ='
        if colors.empty?
          lines << '        com.kotlinjsonui.core.JsonUITestValue.applyAll(values, testDeclaredClasses, update)'
        else
          lines << '        com.kotlinjsonui.core.JsonUITestValue.applyAll(values, testDeclaredClasses, update) { key, accepted ->'
          lines << '            when (key) {'
          colors.each do |prop|
            lines << "                #{kotlin_string(prop[:name])} -> com.kotlinjsonui.core.JsonUITestValue.resolveColor(accepted, #{kotlin_string(prop[:declared])}) {"
            lines << '                    com.kotlinjsonui.generated.ColorManager.compose.colorOrHex(it)'
            lines << '                }'
          end
          lines << '                else -> com.kotlinjsonui.core.TestValueVerdict.Accepted(accepted)'
          lines << '            }'
          lines << '        }'
        end
        lines << ''
        lines << '    // The state bridge\'s data (jsonui-test-runner spec section 10.4): the fields an'
        lines << '    // initialState can set, but not a Color (the Data holds the resolved colour).'
        lines << "    // Requires KotlinJsonUI >= #{MIN_LIBRARY_VERSION} (test bridge)"
        if props.empty?
          lines << '    fun testSnapshot(): Map<String, Any?> = emptyMap()'
        else
          lines << '    fun testSnapshot(): Map<String, Any?> = com.kotlinjsonui.core.JsonUITestValue.snapshot('
          lines << '        mapOf('
          props.each_with_index do |prop, index|
            comma = index < props.length - 1 ? ',' : ''
            lines << "            #{kotlin_string(prop[:name])} to #{prop[:name]}#{comma}"
          end
          lines << '        ),'
          lines << '        testDeclaredClasses'
          lines << '    )'
        end
        lines.join("\n") + "\n"
      end

      # The GeneratedView's call, inside the Box that holds the marker. With a
      # ViewModel that has no updateData the call passes no update: every key
      # the check accepts is then rejected with `viewModel has no updateData`.
      def bridge_call(screen_id, has_update_data:, indent:)
        update = has_update_data ? 'viewModel::updateData' : 'null'
        [
          "#{indent}// Requires KotlinJsonUI >= #{MIN_LIBRARY_VERSION} (test bridge: initialState and state)",
          "#{indent}val testBridge = rememberTestBridge(",
          "#{indent}    #{kotlin_string(screen_id)},",
          "#{indent}    snapshot = { data.testSnapshot() },",
          "#{indent}    apply = { data.applyTestInitialState(it, #{update}) }",
          "#{indent})"
        ].join("\n") + "\n"
      end
    end
  end
end
