# frozen_string_literal: true

require 'json'
require 'fileutils'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'

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

          # Keep original PascalCase if provided, otherwise convert
          # If the name is already in PascalCase (e.g., ProductCell), keep it
          cell_class_name = cell_name
          json_file_name = to_snake_case(cell_name)

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
            swift_path = File.join(source_dir, view_dir, subdirectory, cell_folder_name)
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
          
          # Create JSON file
          json_file = File.join(json_path, "#{json_file_name}.json")
          create_json_template(json_file, cell_class_name)
          
          # Create Main Cell View file (add View suffix to class name)
          main_kotlin_file = File.join(swift_path, "#{cell_class_name}View.kt")
          create_main_cell_template(main_kotlin_file, cell_class_name, json_file_name, subdirectory, package_name)
          
          # Create Generated View file
          generated_kotlin_file = File.join(swift_path, "#{cell_class_name}GeneratedView.kt")
          create_generated_cell_template(generated_kotlin_file, cell_class_name, json_file_name, subdirectory, package_name)
          
          # Create Data file with item property
          data_file = File.join(data_path, "#{cell_class_name}Data.kt")
          create_cell_data_template(data_file, cell_class_name, package_name)
          
          # Create ViewModel file
          viewmodel_file = File.join(viewmodel_path, "#{cell_class_name}ViewModel.kt")
          create_cell_viewmodel_template(viewmodel_file, cell_class_name, json_file_name, subdirectory, package_name)
          
          puts "Generated Collection Cell view:"
          puts "  JSON:           #{json_file}"
          puts "  Main View:      #{main_kotlin_file}"
          puts "  Generated View: #{generated_kotlin_file}"
          puts "  Data:           #{data_file}"
          puts "  ViewModel:      #{viewmodel_file}"
          puts ""
          puts "Next steps:"
          puts "  1. Edit the JSON layout in #{json_file}"
          puts "  2. Run 'kjui build' to generate the Compose code"
          puts "  3. Use this cell in Collection components with cellClasses: [\"#{cell_class_name}\"]"
        end

        private

        def create_json_template(file_path, class_name)
          return if File.exist?(file_path)
          
          json_content = {
            "type" => "View",
            "orientation" => "horizontal",
            "padding" => 12,
            "background" => "#F9F9F9",
            "cornerRadius" => 6,
            "child" => [
              {
                "type" => "Text",
                "text" => "@{item.title}",
                "fontSize" => 14,
                "weight" => 1
              },
              {
                "type" => "Text",
                "text" => "@{item.value}",
                "fontSize" => 14,
                "fontWeight" => "bold"
              }
            ]
          }
          
          File.write(file_path, JSON.pretty_generate(json_content))
        end

        def create_main_cell_template(file_path, class_name, json_name, subdirectory, package_name)
          return if File.exist?(file_path)

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

          File.write(file_path, content)
        end

        def create_generated_cell_template(file_path, class_name, json_name, subdirectory, package_name)
          return if File.exist?(file_path)

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

          File.write(file_path, content)
        end

        def create_cell_data_template(file_path, class_name, package_name)
          return if File.exist?(file_path)

          content = <<~KOTLIN
            package #{package_name}.data

            data class #{class_name}Data(
                var item: Map<String, Any> = emptyMap()
            ) {
                companion object {
                    // Update properties from map
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

          File.write(file_path, content)
        end

        def create_cell_viewmodel_template(file_path, class_name, json_name, subdirectory, package_name)
          return if File.exist?(file_path)

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

          File.write(file_path, content)
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