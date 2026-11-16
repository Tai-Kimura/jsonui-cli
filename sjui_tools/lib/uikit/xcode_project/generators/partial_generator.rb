#!/usr/bin/env ruby

require "fileutils"
require "json"
require_relative '../../../core/pbxproj_manager'
require_relative '../../../core/xcode_project_manager'
require_relative '../../../core/project_finder'
require_relative '../../../core/logger'
require_relative '../../../core/converter_generator_core'
require_relative 'scaffold_transaction'

module SjuiTools
  module UIKit
    module XcodeProject
      module Generators
        class PartialGenerator < ::SjuiTools::Core::PbxprojManager
          def initialize(project_file_path = nil, options = {})
            super(project_file_path)
            @options = options

            # Setup paths using ProjectFinder
            Core::ProjectFinder.setup_paths(@project_file_path)

            # Get configuration
            config = Core::ConfigManager.load_config

            # Set paths
            source_path = Core::ProjectFinder.get_full_source_path
            @layouts_path = File.join(source_path, config['layouts_directory'] || 'Layouts')

            @xcode_manager = SjuiTools::Core::XcodeProjectManager.new(@project_file_path)
          end

          def build_command_string(partial_name)
            "sjui g partial #{partial_name}"
          end

          def generate(partial_name)
            puts "Generating partial layout: #{partial_name}"
            puts "Debug: Original partial name: '#{partial_name}'"
            
            # 1. Partial JSONファイルの作成 — through the one overwrite
            # decision the generate commands share (until 1.9.0 --force and
            # --skip-existing were not read here).
            # The transaction's record says what this run created: what a
            # failed Xcode step deletes (until 1.9.0 this generator had no
            # rollback: the new layout stayed, out of the project).
            @txn = ScaffoldTransaction.new(@project_file_path)
            record = @txn.record
            json_file_path = create_partial_json(partial_name, record)
            puts "Debug: partial file path: '#{json_file_path}'"
            
            # 2. Xcodeプロジェクトに追加 — a raise or a :failed answer rolls
            # the run back and fails it.
            begin
              @txn.check!([[json_file_path, add_to_xcode_project(json_file_path)]])
            rescue => e
              puts "Error adding the partial to the Xcode project: #{e.message}"
              @txn.roll_back
              raise e
            end
            
            # 3. Bindingファイルの生成
            generate_binding_file
            
            # The counts, from the record (until 1.9.0 "Successfully
            # generated partial" and "File created" followed "Partial JSON
            # file already exists" — ticket kjui-g-view-reports-what-it-did-not-do).
            puts
            JsonUIShared::ConverterGeneratorCore.report_scaffold_record("partial #{partial_name}", record, Core::Logger)
            puts "\nTo use this partial, include it in your layout JSON:"
            puts '  { "include": "' + partial_name + '" }'
          end

          private

          def create_partial_json(partial_name, record)
            # Handle directory structure in partial name
            file_path = File.join(@layouts_path, "#{partial_name}.json")
            
            # Ensure parent directory exists
            parent_dir = File.dirname(file_path)
            puts "Created directory: #{parent_dir}" if @txn.mkdir_p(parent_dir)
            
            JsonUIShared::ConverterGeneratorCore.write_scaffold(
              file_path, @options.merge(scaffold_files: record), Core::Logger,
              noun: 'partial layout', label: 'partial layout', exists_label: 'Partial layout'
            ) { generate_partial_json_content(partial_name) }

            file_path
          end

          def generate_partial_json_content(partial_name)
            # Extract just the filename part for IDs (remove directory path)
            base_name = File.basename(partial_name)
            command = build_command_string(partial_name)

            content = {
              "generatedBy" => command,
              "type" => "View",
              "id" => "#{base_name}_root",
              "width" => "matchParent",
              "height" => "wrapContent",
              "padding" => 16,
              "background" => "#FFFFFF",
              "child" => [
                {
                  "type" => "Label",
                  "id" => "#{base_name}_label",
                  "text" => "This is the #{base_name} partial",
                  "fontSize" => 14,
                  "fontColor" => "#000000"
                }
              ]
            }
            JSON.pretty_generate(content)
          end

          def add_to_xcode_project(json_file_path)
            # バックアップとエラーハンドリングを含む安全な処理
            puts "Debug: Adding partial file to Xcode: #{json_file_path}"
            
            # Extract subdirectory structure from the path
            relative_to_layouts = Pathname.new(json_file_path).relative_path_from(Pathname.new(@layouts_path))
            subdirs = relative_to_layouts.dirname.to_s
            
            if subdirs == '.'
              # No subdirectory, add directly to Layouts
              @xcode_manager.add_file(json_file_path, "Layouts")
            else
              # Has subdirectory, add to Layouts/subdirectory
              group_path = "Layouts/#{subdirs}"
              puts "Debug: Adding to group: #{group_path}"
              @xcode_manager.add_file(json_file_path, group_path)
            end
          end

          def generate_binding_file
            begin
              # JsonLoaderとImportModuleManagerをrequire
              require_relative '../../json_loader'
              require_relative '../../import_module_manager'
              require_relative '../../../core/config_manager'
              
              # configから カスタムビュータイプを読み込んで設定
              custom_view_types = Core::ConfigManager.get_custom_view_types
              
              # カスタムビュータイプを設定
              view_type_mappings = {}
              import_mappings = {}
              
              custom_view_types.each do |view_type, config|
                if config['class_name']
                  view_type_mappings[view_type.to_sym] = config['class_name']
                end
                if config['import_module']
                  import_mappings[view_type] = config['import_module']
                end
              end
              
              # View typeの拡張
              JsonLoader.view_type_set.merge!(view_type_mappings) unless view_type_mappings.empty?
              
              # Importマッピングの追加
              import_mappings.each do |type, module_name|
                ImportModuleManager.add_type_import_mapping(type, module_name)
              end
              
              # JsonLoaderを実行
              loader = JsonLoader.new(nil, @project_file_path)
              loader.start_analyze
              
              # The loader says per file what it wrote, and names a file it
              # could not — until 1.9.0 this line claimed success after
              # such an error.
              puts "Binding generation ran: its lines above say what it wrote"
            rescue => e
              puts "Warning: Could not generate binding files: #{e.message}"
              puts "You can run 'sjui build' manually to generate binding files"
            end
          end
        end
      end
    end
  end
end

# コマンドライン実行
if __FILE__ == $0
  if ARGV.length != 1
    puts "Usage: ruby partial_generator.rb <partial_name>"
    puts "Example: ruby partial_generator.rb navigation_bar"
    exit 1
  end

  begin
    # binding_builderディレクトリから検索開始
    binding_builder_dir = File.expand_path("../../", __FILE__)
    project_file_path = SjuiTools::Core::ProjectFinder.find_project_file(binding_builder_dir)
    generator = SjuiTools::UIKit::XcodeProject::Generators::PartialGenerator.new(project_file_path)
    generator.generate(ARGV[0])
  rescue => e
    puts "Error: #{e.message}"
    exit 1
  end
end