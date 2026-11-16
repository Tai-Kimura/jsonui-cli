# frozen_string_literal: true

require 'core/xcode_target_helper'

RSpec.describe SjuiTools::Core::XcodeTargetHelper do
  describe '.get_app_targets' do
    let(:app_target) do
      double('AppTarget',
        name: 'MyApp',
        product_type: 'com.apple.product-type.application'
      )
    end

    let(:test_target) do
      double('TestTarget',
        name: 'MyAppTests',
        product_type: 'com.apple.product-type.bundle.unit-test'
      )
    end

    let(:ui_test_target) do
      double('UITestTarget',
        name: 'MyAppUITests',
        product_type: 'com.apple.product-type.bundle.ui-testing'
      )
    end

    let(:framework_target) do
      double('FrameworkTarget',
        name: 'MyFramework',
        product_type: 'com.apple.product-type.framework'
      )
    end

    let(:project) { double('Project', targets: [app_target, test_target, ui_test_target, framework_target]) }

    before do
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
        'project_name' => 'MyApp'
      })
    end

    it 'returns only app targets' do
      result = described_class.get_app_targets(project)

      expect(result).to include(app_target)
      expect(result).not_to include(framework_target)
    end

    it 'excludes test targets' do
      result = described_class.get_app_targets(project)

      expect(result).not_to include(test_target)
      expect(result).not_to include(ui_test_target)
    end

    it 'filters by project name' do
      other_app = double('OtherApp',
        name: 'OtherApp',
        product_type: 'com.apple.product-type.application'
      )
      project_with_other = double('Project', targets: [app_target, other_app])

      result = described_class.get_app_targets(project_with_other)

      expect(result).to include(app_target)
      expect(result).not_to include(other_app)
    end

    context 'when project_name is empty' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
      end

      it 'returns all app targets' do
        other_app = double('OtherApp',
          name: 'OtherApp',
          product_type: 'com.apple.product-type.application'
        )
        project_with_other = double('Project', targets: [app_target, other_app])

        result = described_class.get_app_targets(project_with_other)

        expect(result).to include(app_target)
        expect(result).to include(other_app)
      end
    end

    context 'when no app targets found' do
      let(:project_no_apps) { double('Project', targets: [test_target, framework_target]) }

      it 'returns empty array' do
        result = described_class.get_app_targets(project_no_apps)

        expect(result).to be_empty
      end

      it 'outputs warning' do
        expect { described_class.get_app_targets(project_no_apps) }.to output(/Warning: No matching app targets found/).to_stdout
      end
    end

    it 'outputs debug information' do
      expect { described_class.get_app_targets(project) }.to output(/Debug:/).to_stdout
    end

    it 'reports found targets' do
      expect { described_class.get_app_targets(project) }.to output(/Found \d+ app target/).to_stdout
    end
  end
end
