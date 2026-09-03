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
      return @available unless @available.nil?

      @available = system('which swiftc > /dev/null 2>&1')
    end

    # Whether `import SwiftUI` type-checks here. A toolchain can exist
    # without the SDK: ubuntu's CI image ships swiftc, so `available?` is
    # true there and every check then fails on its first line with
    # "no such module 'SwiftUI'" — a toolchain finding wearing a
    # converter finding's clothes (four label examples, 2026-09-03).
    # Probed once, by compiling the import itself.
    def swiftui_available?
      return @swiftui_available unless @swiftui_available.nil?

      @swiftui_available = available? && run_swiftc("import SwiftUI\n", '-typecheck')[:status].success?
    end

    # Why a check cannot run here, or nil when it can. The matcher turns
    # this into a skip — visible in the count — never into a pass.
    def unavailable_reason
      return 'swiftc is not on PATH' unless available?
      return "swiftc cannot import SwiftUI here (SDK: #{sdk_path.empty? ? 'none' : sdk_path})" unless swiftui_available?

      nil
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
      # A check that cannot run is not a check that passed. This used to
      # answer success when swiftc was missing, which read as "compiles"
      # to every caller. The matcher skips before it gets here; a direct
      # caller gets the reason as the error.
      if (reason = unavailable_reason)
        return CompileResult.new(success: false, output: reason, errors: [reason])
      end

      flag = mode == :parse ? '-parse' : '-typecheck'
      run = run_swiftc(build_compilable_code(swift_code, imports), flag)
      CompileResult.new(
        success: run[:status].success?,
        output: run[:output],
        errors: parse_errors(run[:output])
      )
    end

    # Check if code compiles (returns boolean)
    def compiles?(swift_code, imports: [], mode: :typecheck)
      compile_check(swift_code, imports: imports, mode: mode).success?
    end

    private

    # SDK path for framework resolution; empty where xcrun is absent.
    def sdk_path
      @sdk_path ||= `xcrun --show-sdk-path 2>/dev/null`.strip
    end

    # Run swiftc over `source` with `flag`; returns { status:, output: }.
    def run_swiftc(source, flag)
      temp_file = Tempfile.new(['sjui_test', '.swift'])
      begin
        temp_file.write(source)
        temp_file.close
        cmd = if sdk_path.empty?
                "swiftc #{flag} #{temp_file.path} 2>&1"
              else
                "swiftc #{flag} -sdk #{sdk_path} #{temp_file.path} 2>&1"
              end
        stdout, stderr, status = Open3.capture3(cmd)
        { status: status, output: stdout + stderr }
      ensure
        temp_file.unlink
      end
    end

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
    # Skipped, not passed and not failed: the example asserts what swiftc
    # says about the emitted Swift, and here swiftc cannot say it. The
    # skip shows in the count, so a leg that ran none of these says so.
    # The macOS leg, where the SDK is, still runs every one.
    if (reason = SwiftCompiler.unavailable_reason)
      message = "compile_as_swift: #{reason}; this example runs where the SwiftUI SDK is present"
      # Record the skip BEFORE raising, as `skip` itself does. The runner
      # treats SkipDeclaredInExample as already recorded and rescues it
      # as a no-op, so a bare raise ends the example as PASSED — measured:
      # four label examples went green under an SDK-less swiftc.
      example = RSpec.current_example
      RSpec::Core::Pending.mark_skipped!(example, message) if example
      raise RSpec::Core::Pending::SkipDeclaredInExample, message
    end

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
