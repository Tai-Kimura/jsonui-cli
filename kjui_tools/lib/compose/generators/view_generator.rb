# frozen_string_literal: true

require 'json'
require 'fileutils'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'

module KjuiTools
  module Compose
    module Generators
      class ViewGenerator
        def initialize(name, options = {})
          @name = name
          @options = options
          @config = Core::ConfigManager.load_config
        end

        def generate
          # Parse name for subdirectories
          parts = @name.split('/')
          view_name = parts.last
          subdirectory = parts[0...-1].join('/') if parts.length > 1
          snake_subdirectory = parts[0...-1].map { |p| to_snake_case(p) }.join('/') if parts.length > 1

          # Convert to proper case
          view_class_name = to_pascal_case(view_name)
          json_file_name = to_snake_case(view_name)
          
          # Get directories from config
          source_dir = @config['source_directory'] || 'src/main'
          layouts_dir = @config['layouts_directory'] || 'assets/Layouts'
          view_dir = @config['view_directory'] || 'kotlin/com/example/kotlinjsonui/sample/views'
          viewmodel_dir = @config['viewmodel_directory'] || 'kotlin/com/example/kotlinjsonui/sample/viewmodels'
          data_dir = @config['data_directory'] || 'kotlin/com/example/kotlinjsonui/sample/data'
          package_name = @config['package_name'] || 'com.example.kotlinjsonui.sample'
          
          # Create full paths with subdirectory support
          # Each view gets its own directory (using snake_case for Android)
          view_folder_name = to_snake_case(view_name)
          
          if subdirectory
            # Views use subdirectory structure, but data and viewmodels are flat
            json_path = File.join(source_dir, layouts_dir, snake_subdirectory)
            swift_path = File.join(source_dir, view_dir, snake_subdirectory, view_folder_name)
            viewmodel_path = File.join(source_dir, viewmodel_dir)
            data_path = File.join(source_dir, data_dir)
          else
            json_path = File.join(source_dir, layouts_dir)
            # Create a folder for each view (e.g., views/home_view/ for HomeView)
            swift_path = File.join(source_dir, view_dir, view_folder_name)
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
          create_json_template(json_file, view_class_name)
          
          # Create Main View file (add View suffix to class name)
          main_kotlin_file = File.join(swift_path, "#{view_class_name}View.kt")
          create_main_view_template(main_kotlin_file, view_class_name, json_file_name, subdirectory, package_name)
          
          # Create Generated View file
          generated_kotlin_file = File.join(swift_path, "#{view_class_name}GeneratedView.kt")
          create_generated_view_template(generated_kotlin_file, view_class_name, json_file_name, subdirectory, package_name)
          
          # Create Data file
          data_file = File.join(data_path, "#{view_class_name}Data.kt")
          create_data_template(data_file, view_class_name, package_name)
          
          # Create ViewModel file
          viewmodel_file = File.join(viewmodel_path, "#{view_class_name}ViewModel.kt")
          create_viewmodel_template(viewmodel_file, view_class_name, json_file_name, subdirectory, package_name)
          
          # Update MainActivity if --root option is specified
          if @options[:root]
            update_main_activity(view_class_name, package_name)
          end
          
          puts "Generated Compose view:"
          puts "  JSON:           #{json_file}"
          puts "  Main View:      #{main_kotlin_file}"
          puts "  Generated View: #{generated_kotlin_file}"
          puts "  Data:           #{data_file}"
          puts "  ViewModel:      #{viewmodel_file}"
          
          if @options[:root]
            puts "  Updated MainActivity to use #{view_class_name}View as root"
          end
          
          puts ""
          puts "Next steps:"
          puts "  1. Edit the JSON layout in #{json_file}"
          puts "  2. Run 'kjui build' to generate the Compose code"
        end

        # Create only the Kotlin scaffold files (MainView / GeneratedView /
        # Data / ViewModel) for an existing JSON layout. The JSON template
        # and MainActivity wiring are intentionally skipped — this is meant
        # for `kjui build` to recover when a layout exists on disk but its
        # paired .kt files were never generated (or were deleted). Each
        # underlying `create_*_template` is a no-op if the file already
        # exists, so this is safe to call on every build.
        def ensure_kotlin_files_exist(base_path: nil)
          parts = @name.split('/')
          view_name = parts.last
          subdirectory = parts[0...-1].join('/') if parts.length > 1
          snake_subdirectory = parts[0...-1].map { |p| to_snake_case(p) }.join('/') if parts.length > 1

          view_class_name = to_pascal_case(view_name)
          json_file_name = to_snake_case(view_name)

          source_dir = @config['source_directory'] || 'src/main'
          view_dir = @config['view_directory'] || 'kotlin/com/example/kotlinjsonui/sample/views'
          viewmodel_dir = @config['viewmodel_directory'] || 'kotlin/com/example/kotlinjsonui/sample/viewmodels'
          data_dir = @config['data_directory'] || 'kotlin/com/example/kotlinjsonui/sample/data'
          package_name = @config['package_name'] || 'com.example.kotlinjsonui.sample'

          # Path resolution mirrors the existing #generate flow which assumes
          # the user invoked `kjui` from the Android module root. Programmatic
          # callers (compose_builder) supply an explicit base_path so the
          # files land under the resolved project source root regardless of
          # the current working directory.
          source_root = base_path ? File.join(base_path, source_dir) : source_dir

          view_folder_name = to_snake_case(view_name)
          swift_path = if subdirectory
                         File.join(source_root, view_dir, snake_subdirectory, view_folder_name)
                       else
                         File.join(source_root, view_dir, view_folder_name)
                       end
          viewmodel_path = File.join(source_root, viewmodel_dir)
          data_path = File.join(source_root, data_dir)

          FileUtils.mkdir_p(swift_path)
          FileUtils.mkdir_p(viewmodel_path)
          FileUtils.mkdir_p(data_path)

          main_kotlin_file = File.join(swift_path, "#{view_class_name}View.kt")
          create_main_view_template(main_kotlin_file, view_class_name, json_file_name, subdirectory, package_name)

          generated_kotlin_file = File.join(swift_path, "#{view_class_name}GeneratedView.kt")
          create_generated_view_template(generated_kotlin_file, view_class_name, json_file_name, subdirectory, package_name)

          data_file = File.join(data_path, "#{view_class_name}Data.kt")
          create_data_template(data_file, view_class_name, package_name)

          viewmodel_file = File.join(viewmodel_path, "#{view_class_name}ViewModel.kt")
          create_viewmodel_template(viewmodel_file, view_class_name, json_file_name, subdirectory, package_name)
        end

        private

        def to_pascal_case(str)
          # Handle camelCase and PascalCase input
          # First convert to snake_case, then to PascalCase
          snake = str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
                     .gsub(/([a-z\d])([A-Z])/, '\1_\2')
                     .downcase
          snake.split(/[_\-]/).map(&:capitalize).join
        end

        def to_snake_case(str)
          str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
             .gsub(/([a-z\d])([A-Z])/, '\1_\2')
             .downcase
        end

        def create_json_template(file_path, view_name)
          return if File.exist?(file_path)
          
          template = {
            type: "SafeAreaView",
            background: "#FFFFFF",
            child: [
              {
                type: "View",
                orientation: "vertical",
                padding: 16,
                child: [
                  {
                    type: "Label",
                    text: "@{title}",
                    fontSize: 24,
                    fontWeight: "bold",
                    fontColor: "#000000",
                    marginBottom: 20
                  },
                  {
                    type: "Label",
                    text: "Welcome to #{view_name}",
                    fontSize: 16,
                    fontColor: "#666666",
                    marginBottom: 30
                  },
                  {
                    type: "Button",
                    text: "Get Started",
                    onclick: "onGetStarted",
                    background: "#6200EE",
                    fontColor: "#FFFFFF",
                    padding: [12, 24],
                    cornerRadius: 8
                  }
                ]
              }
            ],
            data: [
              {
                name: "title",
                class: "String",
                defaultValue: "'#{view_name}'"
              }
            ]
          }
          
          File.write(file_path, JSON.pretty_generate(template))
          puts "Created JSON template: #{file_path}"
        end

        def create_main_view_template(file_path, view_name, json_name, subdirectory, package_name)
          return if File.exist?(file_path)

          package_parts = package_name.split('.')
          # Each view has its own package (e.g., com.example.views.home_view)
          # Must use snake_case for subdirectory in package names
          view_folder_name = to_snake_case(view_name)
          snake_subdir = subdirectory&.split('/')&.map { |p| to_snake_case(p) }&.join('.')
          view_package = snake_subdir ? "#{package_name}.views.#{snake_subdir}.#{view_folder_name}" : "#{package_name}.views.#{view_folder_name}"
          
          template = <<~KOTLIN
            package #{view_package}

            import androidx.compose.runtime.Composable
            import androidx.compose.runtime.collectAsState
            import androidx.compose.runtime.getValue
            import androidx.lifecycle.viewmodel.compose.viewModel
            import #{package_name}.viewmodels.#{view_name}ViewModel

            @Composable
            fun #{view_name}View(
                viewModel: #{view_name}ViewModel = viewModel()
            ) {
                val data by viewModel.data.collectAsState()

                #{view_name}GeneratedView(data = data, viewModel = viewModel)
            }
          KOTLIN
          
          File.write(file_path, template)
          puts "Created Main View template: #{file_path}"
        end
        
        def create_generated_view_template(file_path, view_name, json_name, subdirectory, package_name)
          return if File.exist?(file_path)

          snake_subdir_path = subdirectory&.split('/')&.map { |p| to_snake_case(p) }&.join('/')
          json_reference = snake_subdir_path ? "#{snake_subdir_path}/#{json_name}" : json_name
          # Each view has its own package (using snake_case for folder)
          # Must use snake_case for subdirectory in package names
          view_folder_name = to_snake_case(view_name)
          snake_subdir = subdirectory&.split('/')&.map { |p| to_snake_case(p) }&.join('.')
          view_package = snake_subdir ? "#{package_name}.views.#{snake_subdir}.#{view_folder_name}" : "#{package_name}.views.#{view_folder_name}"
          
          template = <<~KOTLIN
            package #{view_package}

            import androidx.compose.foundation.background
            import androidx.compose.foundation.layout.*
            import androidx.compose.foundation.lazy.LazyColumn
            import androidx.compose.foundation.lazy.LazyRow
            import androidx.compose.material3.*
            import androidx.compose.runtime.Composable
            import androidx.compose.ui.Alignment
            import androidx.compose.ui.Modifier
            import androidx.compose.ui.graphics.Color
            import androidx.compose.ui.text.font.FontWeight
            import androidx.compose.ui.text.style.TextAlign
            import androidx.compose.ui.unit.dp
            import androidx.compose.ui.unit.sp
            import #{package_name}.data.#{view_name}Data
            import #{package_name}.viewmodels.#{view_name}ViewModel

            @Composable
            fun #{view_name}GeneratedView(
                data: #{view_name}Data,
                viewModel: #{view_name}ViewModel,
                modifier: Modifier = Modifier
            ) {
                // Generated Compose code from #{json_reference}.json
                // This will be updated when you run 'kjui build'
                // >>> GENERATED_CODE_START
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = data.title,
                        fontSize = 24.sp,
                        fontWeight = FontWeight.Bold
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    Text(
                        text = "Run 'kjui build' to generate Compose code",
                        fontSize = 14.sp,
                        color = Color.Gray
                    )
                }
                // >>> GENERATED_CODE_END
            }
          KOTLIN
          
          File.write(file_path, template)
          puts "Created Generated View template: #{file_path}"
        end
        
        def create_data_template(file_path, view_name, package_name)
          return if File.exist?(file_path)
          
          data_package = "#{package_name}.data"
          
          template = <<~KOTLIN
            package #{data_package}

            data class #{view_name}Data(
                var title: String = "#{view_name}",

                // Action closures (called from generated views)
                var onGetStarted: (() -> Unit)? = null
                // Add more data properties as needed based on your JSON structure
            ) {
                // Update properties from map
                fun update(map: Map<String, Any>) {
                    map["title"]?.let {
                        if (it is String) title = it
                    }
                }

                // Convert to map for dynamic mode
                fun toMap(): Map<String, Any> {
                    return mutableMapOf(
                        "title" to title
                    )
                }
            }
          KOTLIN
          
          File.write(file_path, template)
          puts "Created Data template: #{file_path}"
        end
        
        def create_viewmodel_template(file_path, view_name, json_name, subdirectory, package_name)
          return if File.exist?(file_path)

          snake_subdir_path = subdirectory&.split('/')&.map { |p| to_snake_case(p) }&.join('/')
          json_reference = snake_subdir_path ? "#{snake_subdir_path}/#{json_name}" : json_name
          viewmodel_package = "#{package_name}.viewmodels"

          template = <<~KOTLIN
            // Generated by kjui_tools - DO NOT EDIT between GENERATED_CODE markers
            package #{viewmodel_package}

            import android.app.Application
            import androidx.lifecycle.AndroidViewModel
            import kotlinx.coroutines.flow.MutableStateFlow
            import kotlinx.coroutines.flow.StateFlow
            import kotlinx.coroutines.flow.asStateFlow
            import kotlinx.coroutines.flow.update
            import #{package_name}.data.#{view_name}Data

            class #{view_name}ViewModel(application: Application) : AndroidViewModel(application) {
                // JSON file reference for hot reload
                val jsonFileName = "#{json_reference}"

                // Data model
                private val _data = MutableStateFlow(#{view_name}Data())
                val data: StateFlow<#{view_name}Data> = _data.asStateFlow()

                // >>> GENERATED_CODE_START
                // Auto-generated updateData function - updated by 'kjui build'
                //
                // The `when` starts EMPTY on purpose. `kjui build` rewrites this
                // block from the layout's data section, and it rewrites the Data
                // class from the same source — so a property named here that the
                // data section does not declare survives in the ViewModel after
                // the build has already removed it from `#{view_name}Data`, and
                // `updated.copy(x = ...)` stops compiling. A `"title"` branch was
                // seeded here and did exactly that to 238 conformance fixtures.
                // The shape below is byte-identical to what
                // ComposeBuilder#generate_update_data_function emits for a view
                // with no declared properties.
                private var _lastUpdateData: Map<String, Any>? = null
                fun updateData(updates: Map<String, Any>) {
                    if (updates == _lastUpdateData) return
                    _lastUpdateData = updates
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

                // Add your custom action handlers below
                fun onGetStarted() {
                    // Handle button tap
                }
            }
          KOTLIN

          File.write(file_path, template)
          puts "Created ViewModel template: #{file_path}"
        end
        
        def update_main_activity(view_name, package_name)
          source_dir = @config['source_directory'] || 'src/main'

          # Find MainActivity file
          activity_files = Dir.glob(File.join(source_dir, '**/MainActivity.kt'))
          if activity_files.empty?
            puts "Warning: Could not find MainActivity.kt file to update"
            return
          end

          activity_file = activity_files.first
          content = File.read(activity_file)

          # Add required imports for DynamicModeManager and view
          view_folder_name = to_snake_case(view_name)
          required_imports = [
            "import com.kotlinjsonui.core.DynamicModeManager",
            "import #{package_name}.views.#{view_folder_name}.#{view_name}View"
          ]

          required_imports.each do |import_line|
            unless content.include?(import_line)
              # Find the last import line and add after it
              if content =~ /(^import .+$)/m
                last_import_match = content.scan(/^import .+$/).last
                if last_import_match
                  content.sub!(last_import_match, "#{last_import_match}\n#{import_line}")
                end
              end
            end
          end

          # Add DynamicModeManager.setDynamicModeEnabled after super.onCreate if not present
          unless content.include?("DynamicModeManager.setDynamicModeEnabled")
            if content =~ /(super\.onCreate\(savedInstanceState\))/
              content.sub!($1, "#{$1}\n\n        // Enable Dynamic Mode for HotLoader (debug builds only)\n        DynamicModeManager.setDynamicModeEnabled(this, true)")
            end
          end

          # Update setContent block with DynamicModeManager integration
          updated = false

          # Find and replace the entire setContent block
          if content =~ /setContent\s*\{[\s\S]*?\n\s{8}\}/m
            content.gsub!(/setContent\s*\{[\s\S]*?\n\s{8}\}/m) do
              <<~KOTLIN.chomp
                setContent {
                            val isDynamicModeEnabled by DynamicModeManager.isDynamicModeEnabled.collectAsState()

                            KotlinJsonUITheme {
                                Surface(
                                    modifier = Modifier.fillMaxSize(),
                                    color = MaterialTheme.colorScheme.background
                                ) {
                                    key(isDynamicModeEnabled) {
                                        #{view_name}View()
                                    }
                                }
                            }
                        }
              KOTLIN
            end
            updated = true
          elsif content =~ /setContent\s*\{[^}]*\}/m
            content.gsub!(/setContent\s*\{[^}]*\}/m) do
              <<~KOTLIN.chomp
                setContent {
                            val isDynamicModeEnabled by DynamicModeManager.isDynamicModeEnabled.collectAsState()

                            key(isDynamicModeEnabled) {
                                #{view_name}View()
                            }
                        }
              KOTLIN
            end
            updated = true
          end

          if updated
            File.write(activity_file, content)
            puts "Updated MainActivity to use #{view_name}View as root with DynamicModeManager"
          else
            puts "Warning: Could not update MainActivity automatically"
            puts "Please manually update your MainActivity to use #{view_name}View()"
          end
        end
      end
    end
  end
end