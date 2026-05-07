# frozen_string_literal: true

require 'tempfile'
require 'open3'

module SwiftCompiler
  class CompileResult
    attr_reader :success, :output, :errors

    def initialize(success:, output:, errors:)
      @success = success
      @output = output
      @errors = errors
    end

    def success?
      @success
    end
  end

  class << self
    # Check if Swift compiler is available
    def available?
      @available ||= system('which swiftc > /dev/null 2>&1')
    end

    # Perform syntax check only (fast)
    def syntax_check(swift_code, imports: [])
      compile_check(swift_code, imports: imports, mode: :parse)
    end

    # Perform type check (includes syntax)
    def type_check(swift_code, imports: [])
      compile_check(swift_code, imports: imports, mode: :typecheck)
    end

    # Main compile check method
    # @param swift_code [String] The Swift code to check
    # @param imports [Array<String>] Additional imports (SwiftUI is always included)
    # @param mode [Symbol] :parse for syntax only, :typecheck for full type check
    # @return [CompileResult] The result of the compilation
    def compile_check(swift_code, imports: [], mode: :typecheck)
      unless available?
        return CompileResult.new(
          success: true,
          output: 'Swift compiler not available, skipping check',
          errors: []
        )
      end

      temp_file = Tempfile.new(['sjui_test', '.swift'])
      begin
        full_code = build_compilable_code(swift_code, imports)
        temp_file.write(full_code)
        temp_file.close

        flag = mode == :parse ? '-parse' : '-typecheck'

        # Use SDK path for proper framework resolution
        sdk_path = `xcrun --show-sdk-path 2>/dev/null`.strip
        cmd = if sdk_path.empty?
                "swiftc #{flag} #{temp_file.path} 2>&1"
              else
                "swiftc #{flag} -sdk #{sdk_path} #{temp_file.path} 2>&1"
              end

        stdout, stderr, status = Open3.capture3(cmd)
        output = stdout + stderr

        CompileResult.new(
          success: status.success?,
          output: output,
          errors: parse_errors(output)
        )
      ensure
        temp_file.unlink
      end
    end

    # Check if code compiles (returns boolean)
    def compiles?(swift_code, imports: [], mode: :typecheck)
      compile_check(swift_code, imports: imports, mode: mode).success?
    end

    private

    def build_compilable_code(code, imports)
      import_statements = (['SwiftUI'] + imports).uniq.map { |i| "import #{i}" }.join("\n")

      # Add mock types for SwiftJsonUI-specific components
      mock_types = <<~SWIFT
        // Mock types for testing (simulating SwiftJsonUI types)
        struct PartialAttributedText: View {
            init(_ text: String, partialAttributes: [PartialAttribute] = [], fontSize: CGFloat? = nil, fontWeight: String? = nil, fontColor: Color? = nil, highlightColor: Color? = nil, underline: Bool = false, strikethrough: Bool = false, lineSpacing: CGFloat? = nil, lineLimit: Int? = nil, textAlignment: TextAlignment = .leading, linkable: Bool = false) {}
            var body: some View { Text("") }
        }
        struct PartialAttribute {
            init(range: Range<Int>? = nil, textPattern: String? = nil, fontColor: Color? = nil, fontSize: CGFloat? = nil, fontWeight: Font.Weight? = nil, underline: Bool = false, strikethrough: Bool = false, backgroundColor: Color? = nil, onClick: (() -> Void)? = nil) {}
        }
        struct SwiftJsonUIConfiguration {
            static let shared = SwiftJsonUIConfiguration()
            func getColor(for hex: String) -> Color? { Color.black }
        }
        class ViewModel: ObservableObject {}
      SWIFT

      <<~SWIFT
        #{import_statements}

        #{mock_types}

        // Generated code for testing
        #{code}
      SWIFT
    end

    def parse_errors(output)
      output.lines.select { |line| line.include?('error:') }.map(&:strip)
    end
  end
end

# RSpec matcher for Swift compilation
RSpec::Matchers.define :compile_as_swift do
  match do |swift_code|
    @result = SwiftCompiler.compile_check(swift_code, imports: @imports || [], mode: @mode || :typecheck)
    @result.success?
  end

  chain :with_imports do |*imports|
    @imports = imports.flatten
  end

  chain :syntax_only do
    @mode = :parse
  end

  failure_message do |swift_code|
    msg = "expected Swift code to compile, but got errors:\n"
    msg += @result.errors.map { |e| "  #{e}" }.join("\n")
    msg += "\n\nCode:\n#{swift_code}"
    msg
  end

  failure_message_when_negated do |swift_code|
    "expected Swift code NOT to compile, but it did"
  end
end
