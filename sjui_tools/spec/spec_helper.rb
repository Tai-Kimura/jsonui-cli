# frozen_string_literal: true

# SimpleCov must be started before any application code is loaded
require 'simplecov'
SimpleCov.start do
  # Output coverage to tools/coverage directory
  coverage_dir File.expand_path('../coverage', __dir__)

  # Only track sjui_tools/lib source files
  root File.expand_path('..', __dir__)

  add_filter '/spec/'
  add_filter '/vendor/'
  add_filter '/bin/'
  add_filter '/scripts/'
  add_filter '/config/'

  add_group 'Core', 'lib/core'
  add_group 'SwiftUI', 'lib/swiftui'
  add_group 'UIKit', 'lib/uikit'
  add_group 'CLI', 'lib/cli'

  # Note: Target is 80%, currently building up tests
  minimum_coverage 50
end

require 'json'
require 'tempfile'

# Add lib to load path (sjui_tools/lib)
$LOAD_PATH.unshift(File.expand_path('../lib', __dir__))

# Load support files
Dir[File.join(__dir__, 'support', '**', '*.rb')].sort.each { |f| require f }

RSpec.configure do |config|
  # Disable status persistence to prevent test filtering
  # config.example_status_persistence_file_path = '.rspec_status'

  # Disable RSpec exposing methods globally on `Module` and `main`
  config.disable_monkey_patching!

  config.expect_with :rspec do |c|
    c.syntax = :expect
  end

  # Run specs in defined order (disable random for stable results)
  # config.order = :random
  # Kernel.srand config.seed

  # `Core::Logger.level` is a class-level global. logger_spec sets it to :debug
  # and :warn and does not restore it, so every example that asserts on an
  # info/warn message passed or failed depending on rspec's seed — six of them
  # failed on seed 37213 while the suite was green on the next seed. Reset per
  # example; a spec that sets the level inside an example still works.
  config.before { SjuiTools::Core::Logger.level = :info if defined?(SjuiTools::Core::Logger) }

  # Filter configuration for slow tests
  config.filter_run_excluding slow: true unless ENV['RUN_SLOW_TESTS']

  # Tag swift_compile tests
  config.define_derived_metadata(file_path: %r{/swiftui/}) do |metadata|
    metadata[:swift_compile] = true unless metadata.key?(:swift_compile)
  end
end

# Helper to get fixture path
def fixture_path(name)
  File.join(__dir__, 'fixtures', name)
end

# Helper to load JSON fixture
def load_json_fixture(name)
  JSON.parse(File.read(fixture_path("json/#{name}")))
end
