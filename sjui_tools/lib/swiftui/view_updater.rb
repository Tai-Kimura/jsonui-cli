# frozen_string_literal: true

require_relative '../core/generated_marker'
require_relative 'binding/binding_expression'

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

        # Check if body needs splitting
        line_count = new_body_code.count("\n") + 1

        if !base_needed
          body_code = ""
          section_functions = ""
        elsif line_count > LINE_THRESHOLD && root_children && root_children.size > 1
          # WeightedStack root: split using pre-captured children info
          body_code, section_functions = generate_split_code(new_body_code, root_children)
        elsif line_count > LINE_THRESHOLD
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

      # Split non-WeightedStack root body using code analysis
      def generate_generic_split(full_body_code)
        # Use a single virtual "section0" for the entire body, then recursively split
        section_functions = []
        dedented = dedent_code(full_body_code)
        generate_section_function("section0", dedented, section_functions)

        # Body becomes section0() call — even without sub-splits, extracting
        # the body into a separate function reduces Swift type-checker load
        body_code = "section0()"
        [body_code, section_functions.join("\n")]
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
        body_lines << "])"

        # Detect modifiers after the root container closing "])"
        # They appear after the children array in the original code
        full_lines = full_body_code.lines.map(&:chomp)
        # Find the "])" line that closes the WeightedStack
        closing_index = nil
        bracket_depth = 0
        full_lines.each_with_index do |line, idx|
          stripped = line.strip
          bracket_depth += stripped.count('[') - stripped.count(']')
          if bracket_depth <= 0 && stripped == '])'
            closing_index = idx
            break
          end
        end

        # Append any modifiers after "])" (e.g., .modifier(...), .background(...))
        if closing_index && closing_index < full_lines.size - 1
          (closing_index + 1...full_lines.size).each do |idx|
            body_lines << full_lines[idx]
          end
        end

        body_code = body_lines.join("\n")

        # Build section functions (with recursive splitting for oversized sections)
        section_functions = []
        root_children.each_with_index do |child_info, index|
          child_code = child_info[:code]
          dedented = dedent_code(child_code)
          generate_section_function("section#{index}", dedented, section_functions)
        end

        [body_code, section_functions.join("\n")]
      end

      # Generate a section function, recursively splitting if it exceeds LINE_THRESHOLD
      def generate_section_function(func_name, code, output, is_tuple: false)
        line_count = code.lines.size

        if line_count > LINE_THRESHOLD
          # Try WeightedStack tuple-array pattern first (higher-level split)
          weighted_result = find_weighted_stack_children(code)

          # Fallback: try splitting a brace-delimited container
          result = weighted_result || find_splittable_children(code)

          if result
            header, child_codes, trailer = result
            children_are_tuples = !weighted_result.nil?

            # Build body with sub-function calls (replace inline children with function calls)
            child_indent = detect_child_indent(child_codes.first)
            new_body_lines = []
            header.lines.each { |l| new_body_lines << l.rstrip }
            child_codes.each_with_index do |_, idx|
              comma = children_are_tuples && idx < child_codes.size - 1 ? ',' : ''
              new_body_lines << "#{child_indent}#{func_name}_#{idx}()#{comma}"
            end
            trailer.lines.each { |l| new_body_lines << l.rstrip }

            # Output the main function with compact body
            func_decl = if is_tuple
              "    private func #{func_name}() -> (view: AnyView, weight: CGFloat) {"
            else
              "    @ViewBuilder private func #{func_name}() -> some View {"
            end
            output << func_decl
            new_body_lines.each do |line|
              output << (line.strip.empty? ? "" : "        #{line}")
            end
            output << "    }"
            output << ""

            # Recursively generate sub-functions
            child_codes.each_with_index do |child_code, idx|
              sub_dedented = dedent_code(child_code)
              generate_section_function("#{func_name}_#{idx}", sub_dedented, output, is_tuple: children_are_tuples)
            end

            return
          end
        end

        # Normal case: output the function as-is
        func_decl = if is_tuple
          "    private func #{func_name}() -> (view: AnyView, weight: CGFloat) {"
        else
          "    @ViewBuilder private func #{func_name}() -> some View {"
        end
        output << func_decl
        code.lines.each do |line|
          output << (line.strip.empty? ? "" : "        #{line.rstrip}")
        end
        output << "    }"
        output << ""
      end

      # Find the deepest container with multiple children that can be split
      # Returns [header_code, [child_code1, child_code2, ...], trailer_code] or nil
      def find_splittable_children(code)
        lines = code.lines.map(&:chomp)

        # Phase 1: Find all container openings (lines that end with {)
        abs_depth = 0
        candidates = []

        lines.each_with_index do |line, idx|
          stripped = line.strip
          next if stripped.empty?

          brace_opens = stripped.count('{')
          brace_closes = stripped.count('}')

          if brace_opens > brace_closes
            candidates << { open_idx: idx, depth: abs_depth + 1 }
          end

          abs_depth += brace_opens - brace_closes
        end

        # Phase 2: For each container, find its children
        best_result = nil

        candidates.each do |container|
          # Skip control flow blocks - local variables can't be shared across split functions
          opening_line = lines[container[:open_idx]].strip
          first_word = opening_line.match(/^(\w+)/)&.[](1)
          # Only split SwiftUI view containers (PascalCase names like VStack, Group, etc.)
          # Skip: if, else, for, while, guard, let, var, switch, do, etc.
          next unless first_word && first_word[0] =~ /[A-Z]/

          children = find_children_inside(lines, container[:open_idx], container[:depth])
          next unless children && children.size > 1

          # Prefer the container whose children span the most total lines
          total_lines = children.sum { |c| c[:end_idx] - c[:start] + 1 }
          if best_result.nil? || total_lines > best_result[:total_lines]
            best_result = {
              depth: container[:depth],
              open_idx: container[:open_idx],
              children: children,
              total_lines: total_lines
            }
          end
        end

        return nil unless best_result

        # Build header (everything up to and including the container opening line)
        header = lines[0..best_result[:open_idx]].join("\n")

        # Build child codes
        child_codes = best_result[:children].map do |child|
          lines[child[:start]..child[:end_idx]].join("\n")
        end

        # Build trailer (from after last child to end)
        last_child_end = best_result[:children].last[:end_idx]
        trailer = lines[(last_child_end + 1)..].join("\n")

        [header, child_codes, trailer]
      end

      # Find direct children inside a container at the given brace depth
      # A child boundary is detected when:
      # - brace depth == container_depth (at the container's child level)
      # - paren depth == 0 (not inside a multi-line function call)
      # - line doesn't start with '.' (not a modifier)
      def find_children_inside(lines, open_line_idx, container_depth)
        children = []
        current_child_start = nil
        brace_depth = container_depth
        paren_depth = 0

        (open_line_idx + 1...lines.size).each do |i|
          stripped = lines[i].strip
          next if stripped.empty?

          brace_opens = stripped.count('{')
          brace_closes = stripped.count('}')
          new_brace_depth = brace_depth + brace_opens - brace_closes

          # Container closing
          if new_brace_depth < container_depth
            if current_child_start
              end_idx = i - 1
              end_idx -= 1 while end_idx >= current_child_start && lines[end_idx].strip.empty?
              children << { start: current_child_start, end_idx: end_idx }
            end
            break
          end

          # Check for new child boundary BEFORE updating state
          if brace_depth == container_depth && paren_depth == 0 && !stripped.start_with?('.')
            if current_child_start && current_child_start < i
              end_idx = i - 1
              end_idx -= 1 while end_idx >= current_child_start && lines[end_idx].strip.empty?
              children << { start: current_child_start, end_idx: end_idx }
            end
            current_child_start = i
          end

          # Update paren depth only when at container brace level
          if brace_depth == container_depth && new_brace_depth == container_depth
            paren_depth += stripped.count('(') - stripped.count(')')
          elsif brace_depth != container_depth && new_brace_depth == container_depth
            # Returning from nested block - preserve paren depth from before the block
            # (e.g., AnyView( VStack { ... } ) should keep paren_depth from the AnyView paren)
            paren_depth += stripped.count('(') - stripped.count(')')
          end

          brace_depth = new_brace_depth
        end

        children.size > 1 ? children : nil
      end

      # Find WeightedStack children in tuple-array format: children: [(view: AnyView(...), weight: N), ...]
      # Returns [header_code, [child_code1, child_code2, ...], trailer_code] or nil
      def find_weighted_stack_children(code)
        lines = code.lines.map(&:chomp)

        # Find "children: [" line
        children_line_idx = nil
        lines.each_with_index do |line, idx|
          if line.strip =~ /^Weighted[VH]Stack.*children:\s*\[/ || line.strip == 'children: ['
            children_line_idx = idx
            break
          end
          # Also match when "children: [" is on a separate line after WeightedStack(
          if line.strip =~ /children:\s*\[$/
            children_line_idx = idx
            break
          end
        end
        return nil unless children_line_idx

        # Find each top-level tuple: lines starting with "(" inside the children: [ ]
        # Track bracket depth (for []) and paren depth (for ())
        # NOTE: WeightedVStack( opens a paren that stays open until ]). We record
        # the paren_depth after processing the children: [ line as a baseline so
        # that tuple boundary detection works relative to it.
        bracket_depth = 0
        paren_depth = 0
        base_paren_depth = nil
        tuple_ranges = []
        current_tuple_start = nil

        (children_line_idx...lines.size).each do |i|
          stripped = lines[i].strip

          # Count brackets and parens
          stripped.each_char do |c|
            case c
            when '[' then bracket_depth += 1
            when ']' then bracket_depth -= 1
            when '(' then paren_depth += 1
            when ')' then paren_depth -= 1
            end
          end

          # Record baseline paren depth after processing the "children: [" line
          if base_paren_depth.nil?
            base_paren_depth = paren_depth
            next
          end

          # Detect tuple start: line with "(" at bracket_depth==1
          if bracket_depth == 1 && stripped.start_with?('(') && current_tuple_start.nil?
            current_tuple_start = i
          end

          # Detect tuple end: paren closes back to baseline at bracket_depth==1
          if current_tuple_start && bracket_depth == 1 && paren_depth == base_paren_depth && stripped =~ /\)[\s,]*$/
            tuple_ranges << { start: current_tuple_start, end_idx: i }
            current_tuple_start = nil
          end

          # End of children array
          break if bracket_depth <= 0
        end

        return nil unless tuple_ranges.size > 1

        # Build header (everything up to first tuple)
        header = lines[0...tuple_ranges.first[:start]].join("\n")

        # Build child codes (each tuple including view: AnyView(...) content)
        # Strip trailing comma from each tuple (it was an array separator, not
        # part of the tuple itself — functions return a single tuple value)
        child_codes = tuple_ranges.map do |range|
          chunk = lines[range[:start]..range[:end_idx]].join("\n")
          chunk.sub(/,\s*\z/, '')
        end

        # Build trailer (from after last tuple to end)
        last_end = tuple_ranges.last[:end_idx]
        trailer = lines[(last_end + 1)..].join("\n")

        [header, child_codes, trailer]
      end

      # Detect the indentation of the first line of a child code block
      def detect_child_indent(child_code)
        first_line = child_code&.lines&.find { |l| !l.strip.empty? }
        return "    " unless first_line

        first_line.match(/^(\s*)/)[1]
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
