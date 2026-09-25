#!/usr/bin/env ruby

require "fileutils"
require_relative '../../../core/xcode_project_manager'
require_relative '../../../core/project_finder'
require_relative '../../../core/pbxproj_manager'
require_relative '../../../core/logger'
require_relative '../../../core/converter_generator_core'

module SjuiTools
  module UIKit
    module XcodeProject
      module Generators
        class CollectionGenerator < ::SjuiTools::Core::PbxprojManager
          def initialize(project_file_path = nil, options = {})
            super(project_file_path)
            @options = options

            # Setup paths using ProjectFinder
            Core::ProjectFinder.setup_paths(@project_file_path)
            
            # Get configuration
            config = Core::ConfigManager.load_config
            
            # Set paths
            source_path = Core::ProjectFinder.get_full_source_path
            @view_path = File.join(source_path, config['view_directory'] || 'View')
            @core_path = File.join(source_path, 'Core')
            @layouts_path = File.join(source_path, config['layouts_directory'] || 'Layouts')
            @bindings_path = File.join(source_path, config['bindings_directory'] || 'Bindings')
            
            @xcode_manager = SjuiTools::Core::XcodeProjectManager.new(@project_file_path)
          end

          def generate(args)
            # 引数をパース: Sample/SampleList形式 または Sample/Footer/SampleList形式
            if args.nil? || args.empty?
              raise "Usage: sjui g collection <ViewFolder>/<CellName>\nExample: sjui g collection Sample/SampleList"
            end

            parts = args.split('/')
            if parts.length < 2
              raise "Invalid format. Use: <ViewFolder>/<CellName> or <ViewFolder>/<SubFolder>/<CellName>"
            end

            # 最後の要素がセル名、それより前がフォルダパス
            cell_name = parts.last
            view_folder_parts = parts[0..-2]

            # 名前の正規化
            camel_view_folders = view_folder_parts.map { |p| p.split('_').map(&:capitalize).join }
            snake_layout_folders = view_folder_parts.map { |p| p.gsub(/([A-Z])/, '_\1').downcase.sub(/^_/, '') }
            camel_cell_name = cell_name.split('_').map(&:capitalize).join

            puts "Generating collection cell: #{camel_cell_name} in #{camel_view_folders.join('/')}"

            # 1. Viewフォルダ/Collectionフォルダの確認/作成
            collection_folder_path = ensure_view_folder(camel_view_folders)

            # Both files through the one overwrite decision the generate
            # commands share (until 1.8.121 --force and --skip-existing were
            # not read here). The record also says what this run created: the
            # only files the rollbacks below may delete.
            @record = JsonUIShared::ConverterGeneratorCore.scaffold_record

            # 2. Collection cellファイルの作成
            cell_file_path = create_collection_cell(collection_folder_path, camel_cell_name)

            # 3. Xcodeプロジェクトに追加
            add_to_xcode_project(cell_file_path, camel_view_folders)

            # 4. JSONレイアウトファイルの作成 (snake_case folders)
            json_file_path = create_cell_json_file(camel_cell_name, snake_layout_folders)

            # 5. JSONファイルをXcodeプロジェクトに追加 (snake_case folders)
            add_json_to_xcode_project(json_file_path, snake_layout_folders)

            # 6. Bindingファイルの生成
            generate_binding_file(camel_cell_name)

            # The counts, from the record — each file has been said as it was
            # decided (until 1.8.121 "Successfully generated" and "Files
            # created:" after a run that kept both — ticket
            # kjui-g-view-reports-what-it-did-not-do).
            puts
            JsonUIShared::ConverterGeneratorCore.report_scaffold_record("collection cell #{camel_cell_name}", @record, Core::Logger)
            puts "\nNext steps:"
            puts "  1. Edit #{json_file_path} to design your cell layout"
            puts "  2. Run 'sjui build' to generate binding files"
            puts "  3. Implement your cell logic in the generated files"
          end

          private

          def ensure_view_folder(view_folder_names)
            # view_folder_names can be array like ['Home', 'Footer'] or single string 'Home'
            folders = view_folder_names.is_a?(Array) ? view_folder_names : [view_folder_names]

            # Create nested view folders
            folder_path = File.join(@view_path, *folders)

            unless Dir.exist?(folder_path)
              FileUtils.mkdir_p(folder_path)
              puts "Created view folder: #{folder_path}"
            end

            # Create Collection subfolder
            collection_folder_path = File.join(folder_path, "Collection")

            unless Dir.exist?(collection_folder_path)
              FileUtils.mkdir_p(collection_folder_path)
              puts "Created collection folder: #{collection_folder_path}"
            end

            collection_folder_path  # Return the Collection folder path
          end

          def create_collection_cell(collection_folder_path, cell_name)
            file_path = File.join(collection_folder_path, "#{cell_name}CollectionViewCell.swift")
            scaffold(file_path, 'collection cell') { generate_collection_cell_content(cell_name) }
            file_path
          end

          def scaffold(file_path, noun, &content)
            JsonUIShared::ConverterGeneratorCore.write_scaffold(
              file_path, @options.merge(scaffold_files: @record), Core::Logger,
              noun: noun, label: noun, exists_label: noun.sub(/\A\w/, &:upcase), &content
            )
          end

          # Deletes `file_path` only when this run created it: until 1.8.121
          # a failed Xcode step deleted the cell / the layout whatever they
          # were, one the app had written too.
          def roll_back(file_path)
            if JsonUIShared::ConverterGeneratorCore.created_scaffold_files(@record).include?(file_path)
              File.delete(file_path) if File.exist?(file_path)
              puts "Deleted: #{file_path} (this run created it)"
            elsif File.exist?(file_path)
              puts "Not deleted: #{file_path} (it was there before this run)"
            end
          end

          def generate_collection_cell_content(cell_name)
            snake_name = cell_name.gsub(/([A-Z])/, '_\1').downcase.sub(/^_/, '')
            
            <<~SWIFT
import UIKit
import SwiftJsonUI

class #{cell_name}CollectionViewCell: BaseCollectionViewCell {
    
    var layoutPath: String {
        return "#{snake_name}_cell"
    }
    
    private lazy var _binding = #{cell_name}CellBinding(viewHolder: self)
    
    override init(frame: CGRect) {
        super.init(frame: frame)
        setupViews()
    }
    
    required init?(coder: NSCoder) {
        super.init(coder: coder)
        setupViews()
    }
    
    func setupViews() {
        // Add your cell's subview using SwiftJsonUI
        if let cellView = UIViewCreator.createView(layoutPath, target: self) {
            contentView.addSubview(cellView)
            
            // Setup constraints
            cellView.translatesAutoresizingMaskIntoConstraints = false
            NSLayoutConstraint.activate([
                cellView.topAnchor.constraint(equalTo: contentView.topAnchor),
                cellView.leadingAnchor.constraint(equalTo: contentView.leadingAnchor),
                cellView.trailingAnchor.constraint(equalTo: contentView.trailingAnchor),
                cellView.bottomAnchor.constraint(equalTo: contentView.bottomAnchor)
            ])
        }
        
        _binding.bindView()
    }
    
    override func prepareForReuse() {
        super.prepareForReuse()
        // Reset cell state here
    }
}
            SWIFT
          end

          def add_to_xcode_project(file_path, view_folder_names)
            begin
              # View/フォルダ名/Collection のグループ構造で追加
              folders = view_folder_names.is_a?(Array) ? view_folder_names : [view_folder_names]
              group_path = "View/#{folders.join('/')}/Collection"
              # Said as add_file did it (until 1.8.121 "Added …" followed
              # "File already in project").
              result = @xcode_manager.add_file(file_path, group_path)
              puts "Added collection cell to Xcode project" if result == :added
            rescue => e
              puts "Error adding file to Xcode project: #{e.message}"
              roll_back(file_path)
              raise e
            end
          end
          
          def add_json_to_xcode_project(json_file_path, view_folder_names)
            begin
              folders = view_folder_names.is_a?(Array) ? view_folder_names : [view_folder_names]
              group_path = "Layouts/#{folders.join('/')}"
              result = @xcode_manager.add_file(json_file_path, group_path)
              puts "Added JSON layout to Xcode project" if result == :added
            rescue => e
              puts "Error adding JSON to Xcode project: #{e.message}"
              roll_back(json_file_path)
              raise e
            end
          end

          def create_cell_json_file(cell_name, view_folder_names)
            snake_name = cell_name.gsub(/([A-Z])/, '_\1').downcase.sub(/^_/, '')
            folders = view_folder_names.is_a?(Array) ? view_folder_names : [view_folder_names]
            layouts_dir = File.join(@layouts_path, *folders)
            FileUtils.mkdir_p(layouts_dir) unless Dir.exist?(layouts_dir)
            file_path = File.join(layouts_dir, "#{snake_name}_cell.json")
            scaffold(file_path, 'JSON layout') { generate_cell_json_content(cell_name) }
            file_path
          end

          def generate_cell_json_content(cell_name)
            require 'json'
            content = {
              "type" => "View",
              "id" => "cell_view",
              "width" => "matchParent",
              "height" => "wrapContent",
              "padding" => 16,
              "background" => "#FFFFFF",
              "child" => [
                {
                  "type" => "Label",
                  "id" => "title_label",
                  "text" => "Cell Item",
                  "fontSize" => 16,
                  "fontColor" => "#000000"
                }
              ]
            }
            JSON.pretty_generate(content)
          end

          def generate_binding_file(cell_name)
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
              
              # The loader says what it wrote, and names a file it could not
              # (until 1.8.121 this line claimed success after such an error).
              puts "Binding generation ran: its lines above say what it wrote"
            rescue => e
              puts "Warning: Could not generate binding file: #{e.message}"
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
    puts "Usage: ruby collection_generator.rb <ViewFolder>/<CellName>"
    puts "Example: ruby collection_generator.rb Sample/SampleList"
    exit 1
  end

  begin
    # binding_builderディレクトリから検索開始
    binding_builder_dir = File.expand_path("../../", __FILE__)
    project_file_path = SjuiTools::Core::ProjectFinder.find_project_file(binding_builder_dir)
    generator = SjuiTools::UIKit::XcodeProject::Generators::CollectionGenerator.new(project_file_path)
    generator.generate(ARGV[0])
  rescue => e
    puts "Error: #{e.message}"
    exit 1
  end
end