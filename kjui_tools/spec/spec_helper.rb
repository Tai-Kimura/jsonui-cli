# frozen_string_literal: true

require 'simplecov'
SimpleCov.start do
  add_filter '/spec/'
  add_group 'Core', 'lib/core'
  add_group 'CLI', 'lib/cli'
  add_group 'Compose', 'lib/compose'
  add_group 'XML', 'lib/xml'
end

$LOAD_PATH.unshift File.expand_path('../lib', __dir__)

require 'json'
require 'fileutils'
require 'tmpdir'

# Require support files
Dir[File.join(__dir__, 'support', '**', '*.rb')].sort.each { |f| require f }

RSpec.configure do |config|
  config.expect_with :rspec do |expectations|
    expectations.include_chain_clauses_in_custom_matcher_descriptions = true
  end

  config.mock_with :rspec do |mocks|
    mocks.verify_partial_doubles = true
  end

  config.shared_context_metadata_behavior = :apply_to_host_groups
  config.filter_run_when_matching :focus
  config.example_status_persistence_file_path = 'spec/.rspec_status'
  config.disable_monkey_patching!
  config.warnings = true

  config.default_formatter = 'doc' if config.files_to_run.one?

  config.order = :random
  Kernel.srand config.seed

  # Every spec file starts with an empty stage ledger (JsonUI::StageFailures,
  # which lives as long as the process: a build records into it and
  # `report!` writes it) and with the emitters' name counters at zero, as a
  # build starts each layout (ComposeBuilder: reset_counter!). The counters
  # were wherever the previous file left them, so a file's emitted names
  # depended on which files ran before it. spec/support/process_state_guard.rb
  # names these as reset here.
  config.before(:context) do
    next unless self.class.superclass == RSpec::Core::ExampleGroup

    JsonUI::StageFailures.clear! if defined?(JsonUI::StageFailures)
    %w[TextComponent TextFieldComponent TextViewComponent ButtonComponent ConstraintLayoutComponent].each do |name|
      next unless defined?(KjuiTools::Compose::Components) && KjuiTools::Compose::Components.const_defined?(name, false)

      KjuiTools::Compose::Components.const_get(name, false).reset_counter!
    end
  end
end
