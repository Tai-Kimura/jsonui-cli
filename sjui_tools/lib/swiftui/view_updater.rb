# frozen_string_literal: true

require_relative '../core/generated_marker'
require_relative 'binding/binding_expression'
require_relative 'section_bounder'

module SjuiTools
  module SwiftUI
    class ViewUpdater
      LINE_THRESHOLD = 100  # Split body into sub-functions when exceeding this line count

      # Version-skew guard: generated code that carries a screen marker will
      # not compile against a library without the modifier, which is the
      # point — a silent "static has a marker, dynamic doesn't" split is far
      # harder to diagnose than a build error.
      SCREEN_MARKER_MIN_LIBRARY_VERSION = '10.8.1'

      def update_generated_body(swift_file_path, new_body_code, state_variables: [], root_children: nil, responsive_functions: [], variant_dispatch: nil, force_typed_view_model: false, view_model_type: nil, source_name: nil, screen_id: nil)
        unless File.exist?(swift_file_path)
          puts "Error: Swift file not found: #{swift_file_path}"
          return false
        end

        # Extract actual struct names from the existing file
        existing_content = File.read(swift_file_path)

        # Extract the actual struct name
        struct_match = existing_content.match(/struct\s+(\w+GeneratedView)\s*:\s*View/)
        unless struct_match
          puts "Error: Could not find struct definition in #{swift_file_path}"
          return false
        end

        generated_view_name = struct_match[1]
        view_name = generated_view_name.sub(/GeneratedView$/, '')

        # Extract the actual Data type from @Binding declaration (supports both @Binding and @SwiftUI.Binding)
        binding_match = existing_content.match(/@(?:SwiftUI\.)?Binding\s+var\s+data:\s+(\w+Data)/)
        data_name = binding_match ? binding_match[1] : "#{view_name}Data"

        # Convert view name to snake_case for JSON file name. Variant views
        # (home@regular.json) pass source_name explicitly — their struct
        # name (HomeRegularVariant) does not round-trip to the file stem.
        json_name = source_name || view_name.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
                                            .gsub(/([a-z\d])([A-Z])/, '\1_\2')
                                            .downcase

        # Build state variables block. A variant dispatch needs the
        # horizontal size class — inject it unless the converter already
        # declared it for inline `responsive` branches.
        state_variables = Array(state_variables)
        if variant_dispatch && variant_dispatch.any? &&
           state_variables.none? { |sv| sv.include?('horizontalSizeClass') }
          state_variables = state_variables +
                            ['@Environment(\.horizontalSizeClass) private var horizontalSizeClass']
        end
        state_vars_block = ""
        if state_variables.any?
          state_vars_block = state_variables.map { |sv| "    #{sv}" }.join("\n") + "\n"
        end

        # viewModel declaration. When the generated body references
        # viewModel.<method>(...) (embed_converter's eventBridge — the only
        # emitter of `viewModel.`), inject a typed @ObservedObject so it
        # resolves; mirrors KJUI's pattern of passing viewModel into the
        # generated function (compose_builder.rb:737-747).
        # Otherwise declare a type-erased optional slot (default keeps every
        # existing call site — including VM-less cell components that pass
        # `data: $data` — source compatible). Either way the declaration
        # feeds the unconditional `.receiveEmbedInitParams(to:)` child-side
        # embed wiring below (renderer-ssot-15-4).
        # Variant-file screens force the typed declaration on the base AND
        # every variant struct so the dispatch call sites always type-check
        # (the screen wrapper passes its @StateObject VM either way).
        if new_body_code.include?('viewModel.') || force_typed_view_model
          view_model_decl = "    @ObservedObject var viewModel: #{view_model_type || "#{view_name}ViewModel"}\n"
        else
          view_model_decl = "    var viewModel: Any = ()\n"
        end

        # A variant dispatch only embeds the base body when some size class
        # still resolves to it (regular branch without @regular, or the
        # compact branch without @compact/@medium).
        dispatch = variant_dispatch || {}
        regular_call = dispatch['regular'] &&
                       "#{dispatch['regular']}(data: $data, viewModel: viewModel)"
        compact_struct = dispatch['compact'] || dispatch['medium']
        compact_call = compact_struct &&
                       "#{compact_struct}(data: $data, viewModel: viewModel)"
        base_needed = dispatch.empty? || regular_call.nil? || compact_call.nil?

        # Check if body needs splitting. Depth triggers alongside line count:
        # the body sits inside `var body: some View {` (one brace), so its
        # own content must stay <= MAX_DEPTH - 1. A short-but-deep body is
        # exactly the shape the device-stack bound cares about.
        line_count = new_body_code.count("\n") + 1
        body_depth = SectionBounder.max_brace_depth(new_body_code.split("\n"))
        needs_split = line_count > LINE_THRESHOLD ||
                      body_depth > SectionBounder::MAX_DEPTH - 1

        if !base_needed
          body_code = ""
          section_functions = ""
        elsif needs_split && root_children && root_children.size > 1
          # WeightedStack root: split using pre-captured children info
          body_code, section_functions = generate_split_code(new_body_code, root_children)
        elsif needs_split
          # Non-WeightedStack root (ZStack, VStack, etc.): split using code analysis
          body_code, section_functions = generate_generic_split(new_body_code)
        else
          body_code = new_body_code
          section_functions = ""
        end

        # Wrap the (possibly split) body in the variant-file dispatch.
        # Whole-tree replacement: the same $data / viewModel feed every
        # branch, so VM-owned state survives a size-class swap while
        # view-local state is dropped by design (06a-design.md D4).
        if dispatch.any?
          branch_true = regular_call || body_code
          branch_false = compact_call || body_code
          body_code = [
            "if horizontalSizeClass == .regular {",
            indent_body_code(branch_true, "    "),
            "} else {",
            indent_body_code(branch_false, "    "),
            "}",
          ].join("\n")
        end

        # Append responsive functions if any (dropped when the base body is
        # unreachable — they are only referenced from the base tree)
        all_functions = [section_functions]
        if base_needed && responsive_functions && responsive_functions.any?
          all_functions.concat(responsive_functions)
        end
        combined_functions = all_functions.reject { |f| f.nil? || f.to_s.strip.empty? }.join("\n")

        # Screen marker: applied to the OUTER Group so the static branch and
        # the Dynamic-mode branch both carry it — a mode-dependent marker
        # would split test results by rendering mode. Applying it here also
        # keeps it off DynamicView's entry point, which cells, tabs, embeds
        # and dialogs re-enter (each would grow a false marker).
        screen_marker_line = if screen_id
          "\n            // Requires SwiftJsonUI >= #{SCREEN_MARKER_MIN_LIBRARY_VERSION} (screen marker)" \
          "\n            .jsonUIScreenMarker(\"#{screen_id}\")"
        else
          ""
        end

        marker_header = SjuiTools::Core::GeneratedMarker.comment_header(
          source: "#{json_name}.json",
          generator: "sjui build",
        )
        marker_footer = SjuiTools::Core::GeneratedMarker.comment_footer

        # GeneratedViewファイルの内容を完全に作り直す
        content = <<~SWIFT
        #{marker_header}

        import SwiftUI
        import SwiftJsonUI
        import Combine

        struct #{generated_view_name}: View {
            @SwiftUI.Binding var data: #{data_name}
        #{view_model_decl}#{state_vars_block}
            var body: some View {
                Group {
        #if DEBUG
                    if ViewSwitcher.isDynamicMode {
                        DynamicView(jsonName: "#{json_name}", viewId: "#{json_name}_view", data: data.toDictionary(binding: $data))
                    } else {
                        generatedBody
                    }
        #else
                    generatedBody
        #endif
                }
                // Requires SwiftJsonUI >= 10.6.0 (embed init-params child-side wiring)
                .receiveEmbedInitParams(to: viewModel)#{screen_marker_line}
            }

            @ViewBuilder
            private var generatedBody: some View {
                // Generated SwiftUI code from #{json_name}.json
                // This will be updated when you run 'sjui build'
                // >>> GENERATED_CODE_START
        #{indent_body_code(body_code, "            ")}
                // >>> GENERATED_CODE_END
            }
        #{combined_functions}
        }

        #{marker_footer}
        SWIFT

        # ファイルに書き込む
        File.write(swift_file_path, content)
        report_section_waivers(File.basename(swift_file_path))
        return true
      end

      def convert_json_to_view(json_file_path)
        # Simple conversion for now - this should be enhanced with actual JSON parsing
        json_content = File.read(json_file_path)
        json = JSON.parse(json_content)

        # Generate SwiftUI code based on JSON structure
        generate_swiftui_code(json)
      end

      private

      # Split non-WeightedStack root body via the depth-bounding engine.
      def generate_generic_split(full_body_code)
        dedented = dedent_code(full_body_code)
        bounder = section_bounder
        body_code, section_functions = bounder.bound(dedented, root_name: 'section0')
        [body_code, section_functions]
      end

      # One bounder per update call so waivers aggregate per file.
      def section_bounder
        @section_bounder ||= SectionBounder.new
      end

      def report_section_waivers(file_label)
        return unless @section_bounder
        @section_bounder.waivers.each do |w|
          puts "warning: [section-bounder] #{file_label} #{w.function}: " \
               "depth #{w.depth} / #{w.lines} lines exceeds the bound and has " \
               "no safe cut (#{w.reason}). The function is emitted oversized."
        end
        @section_bounder = nil
      end

      # Split root WeightedStack children into separate @ViewBuilder functions
      def generate_split_code(full_body_code, root_children)
        # Detect root container type (WeightedVStack or WeightedHStack)
        first_line = full_body_code.lines.first&.strip || ""
        container_match = first_line.match(/^(Weighted[VH]Stack)\((.+),\s*children:\s*\[$/)

        unless container_match
          # Not a WeightedStack root, return as-is
          return [full_body_code, ""]
        end

        container_type = container_match[1]
        container_params = container_match[2]

        # Find the line that closes the WeightedStack BEFORE rebuilding the
        # body, and keep its exact text. The closing line is not always a bare
        # "])": a horizontal weighted root with height matchParent closes as
        # "], hasMatchParentCrossAxis: true)" (view_converter emits the flag on
        # the closing line because it is the last named arg of the init).
        # Re-emitting a hardcoded "])" here silently dropped that flag — which
        # toggles the library's inner .fixedSize and collapses fill-height
        # children — and, because the old scan matched only the exact string
        # "])", the flagged line was never found, so every root trailing
        # modifier after it was silently deleted as well. Both regressions
        # fired purely on the body crossing LINE_THRESHOLD.
        full_lines = full_body_code.lines.map(&:chomp)
        closing_index = nil
        bracket_depth = 0
        full_lines.each_with_index do |line, idx|
          stripped = line.strip
          bracket_depth += stripped.count('[') - stripped.count(']')
          # Both emitted forms: "])" (bare) and "], hasMatchParentCrossAxis:
          # true)" (flag appended after the array close).
          if bracket_depth <= 0 && (stripped.start_with?('])') || stripped.start_with?('],'))
            closing_index = idx
            break
          end
        end
        closing_line = closing_index ? full_lines[closing_index].strip : '])'

        # Build compact body with section function calls
        body_lines = []
        body_lines << "#{container_type}(#{container_params}, children: ["
        root_children.each_with_index do |child_info, index|
          weight = child_info[:weight]
          comma = index < root_children.size - 1 ? ',' : ''
          # Preserve the call-site wrapContent contract (.fixedSize) captured at
          # inline-emit time. Without this, section extraction silently drops the
          # weight:0 wrapContent child's cross-axis fixedSize
          # (drops-weighted-child-call-site-fixed-size bug). Appending it to the
          # section#{index}() call is emit-equivalent to the inline placement
          # inside AnyView(...).
          fixed_size = child_info[:fixed_size]
          view_expr = fixed_size ? "section#{index}()#{fixed_size}" : "section#{index}()"
          body_lines << "    ("
          body_lines << "      view: AnyView(#{view_expr}),"
          body_lines << "      weight: #{weight}"
          body_lines << "    )#{comma}"
        end
        body_lines << closing_line

        # Append any modifiers after "])" (e.g., .modifier(...), .background(...))
        if closing_index && closing_index < full_lines.size - 1
          (closing_index + 1...full_lines.size).each do |idx|
            body_lines << full_lines[idx]
          end
        end

        body_code = body_lines.join("\n")

        # Build section functions through the depth-bounding engine. The
        # call sites above are already AnyView-erased by the tuple contract
        # (view: AnyView(sectionN())).
        bounder = section_bounder
        section_functions = root_children.each_with_index.map do |child_info, index|
          bounder.bound_child(dedent_code(child_info[:code]), "section#{index}")
        end

        [body_code, section_functions.join("\n")]
      end

      # Remove common leading whitespace from code block
      def dedent_code(code)
        lines = code.lines
        non_empty_lines = lines.reject { |l| l.strip.empty? }
        return code if non_empty_lines.empty?

        min_indent = non_empty_lines.map { |l| l.match(/^(\s*)/)[1].length }.min
        lines.map { |l| l.strip.empty? ? "\n" : l[min_indent..] }.join
      end

      def indent_body_code(code, indent)
        lines = code.split("\n")
        lines.map { |line| line.empty? ? line : "#{indent}#{line}" }.join("\n")
      end

      def generate_swiftui_code(json, indent_level = 0)
        indent = "    " * indent_level
        code = []

        view_type = json['type'] || 'View'

        case view_type
        when 'View'
          orientation = json['orientation'] || 'vertical'
          container = orientation == 'horizontal' ? 'HStack' : 'VStack'

          code << "#{container} {"

          # Process children
          if json['child']
            children = json['child'].is_a?(Array) ? json['child'] : [json['child']]
            children.each do |child|
              next if child['data'] # Skip data declarations
              child_code = generate_swiftui_code(child, indent_level + 1)
              code << child_code unless child_code.empty?
            end
          end

          code << "}"

          # Add modifiers
          modifiers = []
          modifiers << ".padding()" if json['paddings']
          modifiers << ".background(Color(hex: \"#{json['background']}\"))" if json['background']

          if modifiers.any?
            code[0] = code[0] + "\n" + modifiers.map { |m| "#{indent}#{m}" }.join("\n")
          end

        when 'Label'
          text = json['text'] || ""
          # Handle data binding (canonical expression parsing)
          if text.start_with?('@{') && text.end_with?('}')
            expr = SwiftUI::Binding::BindingExpression.swift_value_expr(text[2...-1])
            code << "Text(#{expr})"
          else
            code << "Text(\"#{text}\")"
          end

          # Add modifiers
          modifiers = []
          modifiers << ".font(.system(size: #{json['fontSize']}))" if json['fontSize']
          modifiers << ".foregroundColor(Color(hex: \"#{json['fontColor']}\"))" if json['fontColor']
          modifiers << ".padding(.top, #{json['topMargin']})" if json['topMargin']

          code[0] = code[0] + modifiers.map { |m| "\n#{indent}    #{m}" }.join("")

        when 'Button'
          text = json['text'] || "Button"
          action = json['onClick'] || "onTap"

          code << "Button(action: { data.#{action}?() }) {"
          code << "    Text(\"#{text}\")"
          code << "}"

          # Add modifiers
          if json['topMargin']
            code[-1] = code[-1] + "\n#{indent}    .padding(.top, #{json['topMargin']})"
          end
        end

        code.map { |line| "#{indent}#{line}" }.join("\n")
      end
    end
  end
end
