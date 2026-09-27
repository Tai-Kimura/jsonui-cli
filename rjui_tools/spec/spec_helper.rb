require 'rspec'

# Support files (matchers, compiler harnesses). sjui and kjui load theirs
# the same way; rjui had no support directory until the TypeScript
# type-check arm needed one.
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

  if config.files_to_run.one?
    config.default_formatter = "doc"
  end

  config.profile_examples = 10

  # JsonUI::StageFailures is the stage ledger a build records into and
  # `report!` writes; it lives as long as the process. Every spec file starts
  # with an empty one, so no file's build reports what another file's
  # recorded (spec/support/process_state_guard.rb names the ledger as reset
  # here).
  config.before(:context) do
    JsonUI::StageFailures.clear! if self.class.superclass == RSpec::Core::ExampleGroup && defined?(JsonUI::StageFailures)
  end
  config.order = :random

  Kernel.srand config.seed
end
