# frozen_string_literal: true

require 'uikit/binding_file_manager'
require 'fileutils'
require 'tmpdir'

RSpec.describe SjuiTools::UIKit::BindingFileManager do
  let(:temp_dir) { Dir.mktmpdir('binding_file_manager_test') }
  let(:view_path) { File.join(temp_dir, 'View') }
  let(:binding_path) { File.join(temp_dir, 'Bindings') }
  let(:manager) { described_class.new(view_path, binding_path) }

  before do
    FileUtils.mkdir_p(view_path)
    FileUtils.mkdir_p(binding_path)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'stores view_path and binding_path' do
      expect(manager.instance_variable_get(:@view_path)).to eq(view_path)
      expect(manager.instance_variable_get(:@binding_path)).to eq(binding_path)
    end
  end

  describe '#setup_binding_file_info' do
    context 'with snake_case file name' do
      it 'returns camelized binding info' do
        result = manager.setup_binding_file_info('my_view')

        expect(result[:base_name]).to eq('MyView')
        expect(result[:binding_class_name]).to eq('MyViewBinding')
        expect(result[:binding_file_name]).to eq('MyViewBinding.swift')
        expect(result[:binding_file_path]).to eq("#{binding_path}/MyViewBinding.swift")
        expect(result[:super_binding]).to eq('Binding')
      end
    end

    context 'with existing binding file' do
      it 'creates backup' do
        existing_file = File.join(binding_path, 'TestBinding.swift')
        File.write(existing_file, 'existing content')

        result = manager.setup_binding_file_info('test')

        expect(result[:backup_file_path]).to eq("#{existing_file}.backup")
        expect(File.exist?("#{existing_file}.backup")).to be true
        expect(File.read("#{existing_file}.backup")).to eq('existing content')
      end
    end

    context 'with existing ViewController' do
      it 'uses BaseBinding as super class' do
        view_dir = File.join(view_path, 'MyView')
        FileUtils.mkdir_p(view_dir)
        File.write(File.join(view_dir, 'MyViewViewController.swift'), '')

        result = manager.setup_binding_file_info('my_view')

        expect(result[:super_binding]).to eq('BaseBinding')
      end
    end

    context 'without existing ViewController' do
      it 'uses Binding as super class' do
        result = manager.setup_binding_file_info('simple')

        expect(result[:super_binding]).to eq('Binding')
      end
    end

    it 'sets reader attributes' do
      manager.setup_binding_file_info('test_view')

      expect(manager.base_name).to eq('TestView')
      expect(manager.binding_class_name).to eq('TestViewBinding')
      expect(manager.binding_file_name).to eq('TestViewBinding.swift')
      expect(manager.binding_file_path).to eq("#{binding_path}/TestViewBinding.swift")
      expect(manager.super_binding).to eq('Binding')
    end
  end

  describe '#cleanup_backup' do
    context 'when backup exists' do
      it 'deletes the backup' do
        backup_path = File.join(temp_dir, 'backup.swift')
        File.write(backup_path, 'backup content')

        manager.cleanup_backup(backup_path)

        expect(File.exist?(backup_path)).to be false
      end
    end

    context 'when backup does not exist' do
      it 'does nothing' do
        expect { manager.cleanup_backup('/nonexistent/backup') }.not_to raise_error
      end
    end

    context 'when backup_path is nil' do
      it 'does nothing' do
        expect { manager.cleanup_backup(nil) }.not_to raise_error
      end
    end
  end

  describe '#restore_backup' do
    context 'when backup exists' do
      it 'restores backup to target path' do
        backup_path = File.join(temp_dir, 'backup.swift')
        target_path = File.join(temp_dir, 'target.swift')
        File.write(backup_path, 'backup content')

        manager.restore_backup(backup_path, target_path)

        expect(File.exist?(target_path)).to be true
        expect(File.read(target_path)).to eq('backup content')
        expect(File.exist?(backup_path)).to be false
      end
    end

    context 'when backup does not exist' do
      it 'does nothing' do
        expect { manager.restore_backup('/nonexistent/backup', '/some/target') }.not_to raise_error
      end
    end

    context 'when backup_path is nil' do
      it 'does nothing' do
        expect { manager.restore_backup(nil, '/some/target') }.not_to raise_error
      end
    end
  end
end
