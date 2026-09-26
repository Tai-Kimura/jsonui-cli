# frozen_string_literal: true

require 'json'
require 'fileutils'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/logger'
require_relative '../../core/converter_generator_core'

module KjuiTools
  module Compose
    module Generators
      class CellGenerator
        def initialize(name, options = {})
          @name = name
          @options = options
          @config = Core::ConfigManager.load_config
        end

        def generate
          # Parse name for subdirectories
          parts = @name.split('/')
          cell_name = parts.last
          subdirectory = parts[0...-1].join('/') if parts.length > 1
          # Convert subdirectory to snake_case for JSON layouts
          snake_subdirectory = parts[0...-1].map { |p| to_snake_case(p) }.join('/') if parts.length > 1

          # The names `kjui build` gives this layout (ComposeBuilder#build_file,
          # #view_subdir_for): the class from the layout's snake_case name in
          # PascalCase, the view folder snake_case under the layout's snake_case
          # subdirectory. Until 1.8.121 the class was the name as typed
          # (`g collection item_cell` wrote item_cellView.kt / item_cellViewModel.kt)
          # and the folder kept the subdirectory's casing (views/MyProducts/…):
          # the build did not find either, scaffolded a second set of files
          # beside them, and a PascalCase name in a PascalCase folder left two
          # files declaring the same Composable in one package (measured on
          # 32785ce8, ticket generate-commands-overwrite-edited-files-and-ignore-their-flags).
          json_file_name = to_snake_case(cell_name)
          cell_class_name = to_pascal_case(json_file_name)
          # The layout's name in Dynamic mode: its path under Layouts/, as
          # `kjui build` writes into the GeneratedView (`layoutName =
          # "my_products/product_cell"`) and `g view` into the ViewModel.
          # Until 1.8.121 the scaffold said "product_cell" until the first
          # build rewrote it, and the ViewModel kept saying it (ticket
          # dynamic-layout-name-drops-the-subdirectory-of-a-nested-cell).
          layout_reference = snake_subdirectory ? "#{snake_subdirectory}/#{json_file_name}" : json_file_name

          # Get directories from config
          source_dir = @config['source_directory'] || 'src/main'
          layouts_dir = @config['layouts_directory'] || 'assets/Layouts'
          view_dir = @config['view_directory'] || 'kotlin/com/example/kotlinjsonui/sample/views'
          viewmodel_dir = @config['viewmodel_directory'] || 'kotlin/com/example/kotlinjsonui/sample/viewmodels'
          data_dir = @config['data_directory'] || 'kotlin/com/example/kotlinjsonui/sample/data'
          package_name = @config['package_name'] || 'com.example.kotlinjsonui.sample'

          # Create full paths with subdirectory support
          # Each cell gets its own directory (using snake_case for Android)
          cell_folder_name = to_snake_case(cell_name)

          if subdirectory
            # JSON uses snake_case subdirectory
            # Views use subdirectory structure, but data and viewmodels are flat
            json_path = File.join(source_dir, layouts_dir, snake_subdirectory)
            swift_path = File.join(source_dir, view_dir, snake_subdirectory, cell_folder_name)
            viewmodel_path = File.join(source_dir, viewmodel_dir)
            data_path = File.join(source_dir, data_dir)
          else
            json_path = File.join(source_dir, layouts_dir)
            swift_path = File.join(source_dir, view_dir, cell_folder_name)
            viewmodel_path = File.join(source_dir, viewmodel_dir)
            data_path = File.join(source_dir, data_dir)
          end
          
          # Create directories if they don't exist
          FileUtils.mkdir_p(json_path)
          FileUtils.mkdir_p(swift_path)
          FileUtils.mkdir_p(viewmodel_path)
          FileUtils.mkdir_p(data_path)
          
          # Each file through the one overwrite decision the generate
          # commands share: an existing one is the app's — kept unless
          # --force (or "y" at the prompt); a closed stdin and --skip-existing
          # keep it. Until 1.8.121 --force / --skip-existing were not read.
          json_file = File.join(json_path, "#{json_file_name}.json")
          main_kotlin_file = File.join(swift_path, "#{cell_class_name}View.kt")
          generated_kotlin_file = File.join(swift_path, "#{cell_class_name}GeneratedView.kt")
          data_file = File.join(data_path, "#{cell_class_name}Data.kt")
          viewmodel_file = File.join(viewmodel_path, "#{cell_class_name}ViewModel.kt")
          core = JsonUIShared::ConverterGeneratorCore
          record = core.scaffold_record
          options = @options.merge(scaffold_files: record)
          scaffold = lambda do |path, noun, &content|
            core.write_scaffold(path, options, Core::Logger,
                                noun: noun, label: noun, exists_label: noun.sub(/\A\w/, &:upcase), &content)
          end

          scaffold.call(json_file, 'JSON layout') { json_content }
          scaffold.call(main_kotlin_file, 'cell view') { main_cell_content(cell_class_name, subdirectory, package_name) }
          scaffold.call(generated_kotlin_file, 'generated cell view') do
            generated_cell_content(cell_class_name, layout_reference, subdirectory, package_name)
          end
          scaffold.call(data_file, 'data file') { cell_data_content(cell_class_name, package_name) }
          scaffold.call(viewmodel_file, 'ViewModel') { cell_viewmodel_content(cell_class_name, layout_reference, package_name) }

          # The counts, from the record (until 1.8.121 a list whatever the run
          # had done — ticket kjui-g-view-reports-what-it-did-not-do).
          core.report_scaffold_record("collection cell #{cell_class_name}", record, Core::Logger)
          puts ""
          puts "Next steps:"
          puts "  1. Edit the JSON layout in #{json_file}"
          puts "  2. Run 'kjui build' to generate the Compose code"
          puts "  3. Use this cell in Collection components with cellClasses: [\"#{cell_class_name}\"]"
        end

        private

        def json_content
          json_content = {
            "type" => "View",
            "orientation" => "horizontal",
            "padding" => 12,
            "background" => "#F9F9F9",
            "cornerRadius" => 6,
            "child" => [
              {
                # Canonical collection-cell scope: the item object's own
                # fields, flat (plus reserved `index`). An `item.` prefix is
                # non-canonical — see shared/core/binding_semantics.json
                # collectionCellScope.
                "type" => "Text",
                "text" => "@{title}",
                "fontSize" => 14,
                "weight" => 1
              },
              {
                "type" => "Text",
                "text" => "@{value}",
                "fontSize" => 14,
                "fontWeight" => "bold"
              }
            ]
          }
          
          JSON.pretty_generate(json_content)
        end

        def main_cell_content(class_name, subdirectory, package_name)
          # Calculate relative package path (must use snake_case for subdirectory in package names)
          snake_subdir = subdirectory&.split('/')&.map { |p| to_snake_case(p) }&.join('.')
          view_package = if snake_subdir
            "#{package_name}.views.#{snake_subdir}.#{to_snake_case(class_name)}"
          else
            "#{package_name}.views.#{to_snake_case(class_name)}"
          end

          content = <<~KOTLIN
            package #{view_package}

            import androidx.compose.runtime.Composable
            import androidx.compose.runtime.collectAsState
            import androidx.compose.runtime.getValue
            import androidx.compose.ui.Modifier
            import #{package_name}.viewmodels.#{class_name}ViewModel

            @Composable
            fun #{class_name}View(
                viewModel: #{class_name}ViewModel,
                modifier: Modifier = Modifier
            ) {
                // This is a cell view for use in Collection components
                // Data is observed from viewModel using collectAsState
                val data by viewModel.data.collectAsState()

                #{class_name}GeneratedView(
                    data = data,
                    viewModel = viewModel,
                    modifier = modifier
                )
            }
          KOTLIN
          content
        end

        def generated_cell_content(class_name, json_name, subdirectory, package_name)
          # Calculate relative package path (must use snake_case for subdirectory in package names)
          snake_subdir = subdirectory&.split('/')&.map { |p| to_snake_case(p) }&.join('.')
          view_package = if snake_subdir
            "#{package_name}.views.#{snake_subdir}.#{to_snake_case(class_name)}"
          else
            "#{package_name}.views.#{to_snake_case(class_name)}"
          end

          content = <<~KOTLIN
            package #{view_package}

            import androidx.compose.foundation.background
            import androidx.compose.foundation.layout.*
            import androidx.compose.material3.*
            import androidx.compose.runtime.Composable
            import androidx.compose.ui.Alignment
            import androidx.compose.ui.Modifier
            import androidx.compose.ui.graphics.Color
            import androidx.compose.ui.text.font.FontWeight
            import androidx.compose.ui.text.style.TextAlign
            import androidx.compose.ui.unit.dp
            import androidx.compose.ui.unit.sp
            import #{package_name}.data.#{class_name}Data
            import #{package_name}.viewmodels.#{class_name}ViewModel
            import androidx.compose.material3.CircularProgressIndicator
            import androidx.compose.foundation.layout.Box
            import com.kotlinjsonui.core.DynamicModeManager
            import com.kotlinjsonui.components.SafeDynamicView

            @Composable
            fun #{class_name}GeneratedView(
                data: #{class_name}Data,
                viewModel: #{class_name}ViewModel,
                modifier: Modifier = Modifier
            ) {
                // Generated Compose code from #{json_name}.json
                // This will be updated when you run 'kjui build'
                // >>> GENERATED_CODE_START
                // Check if Dynamic Mode is active
                if (DynamicModeManager.isActive()) {
                    // Dynamic Mode - use SafeDynamicView for real-time updates
                    SafeDynamicView(
                        layoutName = "#{json_name}",
                        data = data.toMap(),
                        modifier = modifier,
                        fallback = {
                            // Show error or loading state when dynamic view is not available
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = "Dynamic view not available",
                                    color = Color.Gray
                                )
                            }
                        },
                        onError = { error ->
                            // Log error or show error UI
                            android.util.Log.e("DynamicView", "Error loading #{json_name}: \\$error")
                        },
                        onLoading = {
                            // Show loading indicator
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center
                            ) {
                                CircularProgressIndicator()
                            }
                        }
                    ) { jsonContent ->
                        // Parse and render the dynamic JSON content
                        // This will be handled by the DynamicView implementation
                    }
                } else {
                    // Static Mode - use generated code
                    // TODO: Generated content will appear here when you run 'kjui build'
                    Box(
                        modifier = modifier
                            .fillMaxWidth()
                            .padding(16.dp)
                    ) {
                        Text("Cell content will be generated from #{json_name}.json")
                    }
                }
                // >>> GENERATED_CODE_END
            }
          KOTLIN
          content
        end

        def cell_data_content(class_name, package_name)
          content = <<~KOTLIN
            package #{package_name}.data

            data class #{class_name}Data(
                var item: Map<String, Any> = emptyMap()
            ) {
                companion object {
                    // Update properties from map
                    @Suppress("UNCHECKED_CAST")
                    fun fromMap(map: Map<String, Any>): #{class_name}Data {
                        return #{class_name}Data(
                            item = map["item"] as? Map<String, Any> ?: emptyMap()
                        )
                    }
                }

                // Convert properties to map for runtime use
                fun toMap(): MutableMap<String, Any> {
                    val map = mutableMapOf<String, Any>()

                    // Data properties
                    map["item"] = item

                    return map
                }
            }
          KOTLIN
          content
        end

        def cell_viewmodel_content(class_name, json_name, package_name)
          content = <<~KOTLIN
            package #{package_name}.viewmodels

            import android.app.Application
            import androidx.lifecycle.AndroidViewModel
            import androidx.lifecycle.viewModelScope
            import androidx.compose.runtime.mutableStateOf
            import androidx.compose.runtime.getValue
            import androidx.compose.runtime.setValue
            import kotlinx.coroutines.flow.MutableStateFlow
            import kotlinx.coroutines.flow.StateFlow
            import kotlinx.coroutines.flow.asStateFlow
            import kotlinx.coroutines.flow.update
            import kotlinx.coroutines.launch
            import #{package_name}.data.#{class_name}Data

            class #{class_name}ViewModel(application: Application) : AndroidViewModel(application) {
                // JSON file reference for hot reload
                val jsonFileName = "#{json_name}"

                // Data model
                private val _data = MutableStateFlow(#{class_name}Data())
                val data: StateFlow<#{class_name}Data> = _data.asStateFlow()

                // >>> GENERATED_CODE_START
                // Auto-generated updateData function - updated by 'kjui build'
                fun updateData(updates: Map<String, Any>) {
                    _data.update { current ->
                        var updated = current
                        updates.forEach { (key, value) ->
                            updated = when (key) {
                                else -> updated
                            }
                        }
                        updated
                    }
                }
                // >>> GENERATED_CODE_END
            }
          KOTLIN
          content
        end

        def to_pascal_case(str)
          str.split(/[_\-]/).map(&:capitalize).join
        end

        def to_snake_case(str)
          str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
             .gsub(/([a-z\d])([A-Z])/, '\1_\2')
             .downcase
        end

        def to_camel_case(str)
          pascal = to_pascal_case(str)
          pascal[0].downcase + pascal[1..-1]
        end
      end
    end
  end
end