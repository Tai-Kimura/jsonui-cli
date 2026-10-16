# frozen_string_literal: true

module SjuiTools
  module SwiftUI
    # The Data struct's two test-bridge functions (jsonui-test-runner spec
    # section 10.3-10.4): `applyTestInitialState(_:)` and `testSnapshot()`.
    #
    # Whether a value fits its class is decided at run time by SwiftJsonUI's
    # JsonUITestValue.check, the one place that judges it, with the class as
    # the layout spells it (`declaredClass`). This file only decides the SHAPE
    # of the Swift that assigns an accepted value and reads a field back:
    # which cast, whether a Color is resolved, whether the field appears in the
    # snapshot at all. A kind it does not know is left to check(), which
    # rejects it as unsupported — so nothing here can make a value fit.
    module TestBridgeCode
      MIN_LIBRARY_VERSION = '10.30.0'

      SCALARS = {
        'String' => :string, 'string' => :string,
        'Int' => :int, 'int' => :int, 'Integer' => :int, 'integer' => :int,
        'Double' => :double, 'double' => :double, 'Number' => :double, 'number' => :double,
        'Float' => :float, 'float' => :float,
        'CGFloat' => :cgfloat,
        'Bool' => :bool, 'bool' => :bool, 'Boolean' => :bool, 'boolean' => :bool,
        'Color' => :color, 'color' => :color
      }.freeze

      module_function

      # :scalar / :typed_array / :untyped_array / :object / :color / :color_array / :unsupported
      def kind(declared_class)
        base = declared_class.to_s.strip.sub(/\?\z/, '')
        return :unsupported if base.include?('->')

        scalar = SCALARS[base]
        return(scalar == :color ? :color : :scalar) if scalar
        return :untyped_array if %w[Array array].include?(base)
        return :object if %w[Object object Hash hash].include?(base)

        element = base[/\AArray\((.+)\)\z/, 1] || base[/\AList<(.+)>\z/, 1] ||
                  (base.start_with?('[') && base.end_with?(']') && !base.include?(':') ? base[1...-1] : nil)
        return(SCALARS[element] == :color ? :color_array : :typed_array) if element && SCALARS.key?(element)

        :unsupported
      end

      def swift_string(text)
        "\"#{text.to_s.gsub('\\', '\\\\\\\\').gsub('"', '\\"')}\""
      end

      # props: [{ name:, declared:, swift_type:, swift_optional: }]
      def apply_function(props)
        lines = []
        lines << ''
        lines << "    // UI test initialState (jsonui-test-runner spec section 10.3). Each value is judged by"
        lines << "    // JsonUITestValue.check against the class the layout declares; what it accepts is"
        lines << "    // assigned, the rest is returned with the reason."
        lines << "    // Requires SwiftJsonUI >= #{MIN_LIBRARY_VERSION} (test bridge)"
        lines << '    mutating func applyTestInitialState(_ values: [String: Any]) -> [JsonUIRejectedKey] {'
        lines << '        var rejected: [JsonUIRejectedKey] = []'
        lines << '        for (key, value) in values {'
        lines << '            switch key {'
        props.each do |prop|
          lines << "            case #{swift_string(prop[:name])}:"
          lines << "                switch JsonUITestValue.check(value, declaredClass: #{swift_string(prop[:declared])}) {"
          lines.concat(accept_lines(prop))
          lines << '                case .reject(let reason):'
          lines << '                    rejected.append(JsonUIRejectedKey(key: key, reason: reason))'
          lines << '                }'
        end
        lines << '            default:'
        lines << '                rejected.append(.notADataField(key))'
        lines << '            }'
        lines << '        }'
        lines << '        return rejected'
        lines << '    }'
        lines.join("\n") + "\n"
      end

      def accept_lines(prop)
        name = prop[:name]
        base = prop[:swift_type].sub(/\?\z/, '')
        case kind(prop[:declared])
        when :unsupported
          ['                case .accept:', '                    break']
        when :color
          # A Color arrives as its spelling and is resolved as update(dictionary:)
          # resolves it; a spelling that names no colour is not applied.
          resolve = "ColorManager.swiftui.color(for: spelling) ?? SwiftJsonUIConfiguration.shared.getColor(for: spelling)"
          null_line = prop[:swift_optional] ? ["                    guard let spelling = accepted as? String else { self.#{name} = nil; continue }"] :
                                               ["                    guard let spelling = accepted as? String else { continue }"]
          ['                case .accept(let accepted):'] + null_line + [
            "                    if let resolved = #{resolve} {",
            "                        self.#{name} = resolved",
            '                    } else {',
            "                        rejected.append(JsonUIRejectedKey(key: key, reason: #{swift_string("type mismatch: expected #{prop[:declared]}")}))",
            '                    }'
          ]
        when :color_array
          resolve = "ColorManager.swiftui.color(for: $0) ?? SwiftJsonUIConfiguration.shared.getColor(for: $0)"
          null_line = prop[:swift_optional] ? ["                    guard let spellings = accepted as? [String] else { self.#{name} = nil; continue }"] :
                                               ["                    guard let spellings = accepted as? [String] else { continue }"]
          ['                case .accept(let accepted):'] + null_line + [
            "                    let resolved = spellings.compactMap { #{resolve} }",
            '                    if resolved.count == spellings.count {',
            "                        self.#{name} = resolved",
            '                    } else {',
            "                        rejected.append(JsonUIRejectedKey(key: key, reason: #{swift_string("type mismatch: expected #{prop[:declared]}")}))",
            '                    }'
          ]
        else
          if prop[:swift_optional]
            ['                case .accept(let accepted):', "                    self.#{name} = accepted as? #{base}"]
          else
            ['                case .accept(let accepted):',
             "                    if let typed = accepted as? #{base} { self.#{name} = typed }"]
          end
        end
      end

      # The fields an initialState can set, as JSON values; a nil optional is
      # null. A Color (or an array of them) is left out: it cannot be spelled back.
      def snapshot_function(props)
        readable = props.reject { |p| %i[unsupported color color_array].include?(kind(p[:declared])) }
        lines = []
        lines << ''
        lines << '    // The state bridge\'s data (jsonui-test-runner spec section 10.4).'
        lines << "    // Requires SwiftJsonUI >= #{MIN_LIBRARY_VERSION} (test bridge)"
        lines << '    func testSnapshot() -> [String: Any] {'
        if readable.empty?
          lines << '        return [:]'
        else
          lines << '        var snapshot: [String: Any] = [:]'
          readable.each do |prop|
            value = prop[:swift_optional] ? "#{prop[:name]}.map { $0 as Any } ?? NSNull()" : prop[:name]
            lines << "        snapshot[#{swift_string(prop[:name])}] = #{value}"
          end
          lines << '        return snapshot'
        end
        lines << '    }'
        lines.join("\n") + "\n"
      end
    end
  end
end
